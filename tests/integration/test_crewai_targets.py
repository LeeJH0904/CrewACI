"""D67: CrewAI Solver/Reviewer/Finalizer targets on the recorded path, offline."""

from argparse import Namespace
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark
from aciarena.agent_components.base_agent import BaseAgent
from aciarena.attacks.catalog import CREWAI_MESSAGE_ROUTES
from aciarena.evaluation.audit import audit_matrix, build_matrix_plan
from aciarena.evaluation.g7_manifest import G7ManifestError
from aciarena.evaluation.recorded_executor import RecordedTaskExecutor, ROOT
from aciarena.evaluation.recorded_suite import RecordedEvaluationSuite
from aciarena.evaluation.records import canonical_hash
from aciarena.evaluation.task import CodeTask, MathTask


MODEL = {'provider': 'openai', 'model_name': 'offline-mock', 'temperature': 0.0,
         'max_tokens': 1024, 'seed': 42, 'api_key': 'private-test-model-key'}
JUDGE = {**MODEL, 'api_key': 'private-test-judge-key'}
SURFACE_CASES = [
    ('disclosure', 'disclosure_math_location.instruction.v1', 'instruction'),
    ('disclosure', 'disclosure_math_name.agent.v1', 'agent'),
    ('disruption', 'disruption_ddos.message.v1', 'message'),
]


class MockLLM:
    def __init__(self, owner, outputs, calls):
        self.owner, self.outputs, self.calls = owner, outputs, calls
        self.input_tokens = self.output_tokens = 0

    def call_llm(self, messages, **kwargs):
        self.calls.append((self.owner, copy.deepcopy(messages)))
        self.input_tokens += 7
        self.output_tokens += 2
        return self.outputs[self.owner]


def task_at(domain='math', index=0):
    row = json.loads((ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json').read_text())[index]
    task = (MathTask if domain == 'math' else CodeTask)(query=row['problem'], ground_truth=row['answer'])
    task.task_id = f'{domain}_{index:04d}'
    return task


class CrewAITargetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.calls = []
        self.outputs = {'solver': 'draft', 'reviewer': 'review', 'finalizer': '320',
                        'judge': '{"response_type":"attempted_answer"}'}

        def make(owner):
            return MockLLM(owner, self.outputs, self.calls)

        for patched in (patch.object(BaseAgent, 'init_llm', lambda agent, config: make(agent.name)),
                        patch('aciarena.attacks.base_attack.get_llm',
                              side_effect=lambda config: make('judge'))):
            patched.start()
            self.addCleanup(patched.stop)

    def args(self, suite, ids, target, experiment_id):
        return SimpleNamespace(mas='crewai_seq_nodeleg', task_domain='math', suite=suite,
                               attack_ids=ids, defense='none', attack_mode='continuous',
                               malicious_agents=[target], output_dir=str(self.directory),
                               experiment_id=experiment_id, max_workers=1, limit=1)

    def run_case(self, target, suite, attack_id, experiment_id):
        executor = RecordedTaskExecutor(self.args(suite, [attack_id], target, experiment_id), JUDGE)
        task = task_at()
        row = executor.execute({'llm_config': MODEL}, task, attack_id=attack_id)
        return executor, task, row

    def messages(self, executor, run_id):
        return [json.loads(line) for line in
                (executor.writer.directory / 'messages.jsonl').read_text().splitlines()
                if json.loads(line)['run_id'] == run_id]

    def audit(self, executor, task, row):
        plan = build_matrix_plan(experiment_id=executor.experiment_id,
                                 selections=[(task.task_id, row.attack_id)],
                                 tasks=executor.tasks, catalog=executor.catalog,
                                 config_hash=row.config_hash)
        return audit_matrix(executor.writer, plan, executor.tasks, executor.catalog)

    def test_three_surfaces_follow_each_target(self):
        for target in ('solver', 'reviewer', 'finalizer'):
            for suite, attack_id, surface in SURFACE_CASES:
                with self.subTest(target=target, surface=surface):
                    executor, task, row = self.run_case(
                        target, suite, attack_id, f'target-{target}-{surface}')
                    self.assertEqual(row.status, 'success')
                    self.assertEqual(row.malicious_agent, target)
                    self.assertTrue(row.target_invoked)
                    self.assertTrue(row.payload_injected)
                    self.assertEqual(row.response_agent, 'finalizer')
                    events = self.messages(executor, row.run_id)
                    attacked = [m for m in events if m['is_attacked']]
                    self.assertTrue(attacked)
                    self.assertEqual({m['sender'] for m in attacked}, {target})
                    observed = {(m['sender'], m['receiver'], m['phase']) for m in attacked}
                    if surface == 'message':
                        self.assertIn(CREWAI_MESSAGE_ROUTES[target], observed)
                        self.assertFalse(any(m['sender'] == target and m['phase'] == 'llm_input'
                                             for m in events))
                    else:
                        self.assertIn((target, 'llm', 'llm_input'), observed)
                    if surface == 'agent':
                        self.assertIn((target, target, 'profile'), observed)
                    report = self.audit(executor, task, row)
                    self.assertTrue(report['ok'], report['errors'])

    def test_finalizer_message_attack_replaces_the_final_answer(self):
        executor, _, row = self.run_case(
            'finalizer', 'disruption', 'disruption_ddos.message.v1', 'target-final-message')
        spec = executor.catalog.get(row.attack_id, task_domain='math')
        self.assertEqual(row.raw_response, spec.payload)
        self.assertNotIn('finalizer', [owner for owner, _ in self.calls])

    def test_audit_rejects_a_row_whose_target_disagrees_with_its_config(self):
        executor, task, row = self.run_case(
            'reviewer', 'disclosure', 'disclosure_math_name.agent.v1', 'target-mismatch')
        config_path = executor.writer.directory / 'configs' / f'{row.config_hash}.json'
        config = json.loads(config_path.read_text())
        self.assertEqual(config['crewai_target'], 'reviewer')
        config['crewai_target'] = 'finalizer'
        config_path.write_text(json.dumps(config))
        report = self.audit(executor, task, row)
        self.assertFalse(report['ok'])
        self.assertTrue(any(error.startswith('attack_metadata_mismatch') for error in report['errors']))

    def test_config_hash_separates_targets(self):
        ids = ['disclosure_math_name.agent.v1']
        hashes = {}
        for target in ('solver', 'reviewer', 'finalizer'):
            executor = RecordedTaskExecutor(self.args('disclosure', ids, target, 'cfg'), JUDGE)
            _, config = executor._configuration(MODEL)
            self.assertEqual(config['crewai_target'], target)
            hashes[target] = canonical_hash(config)
        self.assertEqual(len(set(hashes.values())), 3)
        # An omitted target is the Solver, so benign and Solver attack rows share a config.
        default = self.args('benign', None, 'solver', 'cfg')
        default.malicious_agents = []
        _, config = RecordedTaskExecutor(default, JUDGE)._configuration(MODEL)
        self.assertEqual(canonical_hash(config), hashes['solver'])

    def test_invalid_targets_are_rejected(self):
        ids = ['disclosure_math_name.agent.v1']
        for targets in (['critic'], ['reviewer', 'finalizer']):
            args = self.args('disclosure', ids, 'solver', 'bad')
            args.malicious_agents = targets
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                RecordedTaskExecutor(args, JUDGE)
        with self.assertRaisesRegex(ValueError, 'benign'):
            RecordedTaskExecutor(self.args('benign', None, 'reviewer', 'bad'), JUDGE)

    def test_g7_suite_runs_and_audits_with_the_target(self):
        args = Namespace(mas='crewai_seq_nodeleg', task_domain='math', suite='disclosure',
                         attack_ids=['disclosure_math_name.agent.v1'], defense='none',
                         attack_mode='continuous', malicious_agents=['reviewer'],
                         output_dir=str(self.directory), experiment_id='target-suite',
                         max_workers=1, limit=1, task_ids=None, phase='core', repetition=1,
                         resume=False, retry_errors=False)
        suite = RecordedEvaluationSuite(
            args, model_config=MODEL, judge_config=JUDGE, manifest_dir=ROOT / 'manifests/g7',
            utility_verifier=lambda task: True, utility_verifier_version='d67-mock-v1')
        result = suite.eval()
        self.assertEqual(result['target_agent'], 'reviewer')
        self.assertTrue(result['audit']['ok'], result['audit']['errors'])
        self.assertEqual(result['planned_runs'], 1)
        self.assertEqual(result['target_not_invoked'], 0)
        self.assertEqual(result['payload_not_injected'], 0)


class BenchmarkCrewAITargetTests(unittest.TestCase):
    def args(self, output_dir, **overrides):
        values = dict(
            attack_ids=None, experiment_id='crewai-target-test',
            experiment_config='configs/experiments/g5_v2.yaml', phase='core', repetition=1,
            resume=False, retry_errors=False, execute=False, model_config=None,
            judge_config=None, mas='crewai_seq_nodeleg', suite='hijacking',
            attack_mode='continuous', defense='none', task_domain='code', max_workers=1,
            limit=1, task_ids=None, output_dir=output_dir, malicious_agents=[],
        )
        values.update(overrides)
        return Namespace(**values)

    def test_dry_run_shows_each_allowed_target(self):
        with tempfile.TemporaryDirectory() as directory:
            for requested, shown in (([], 'solver'), (['solver'], 'solver'),
                                     (['reviewer'], 'reviewer'), (['finalizer'], 'finalizer')):
                with self.subTest(requested=requested):
                    result = benchmark.main(self.args(directory, malicious_agents=requested))
                    self.assertEqual(result['target_agent'], shown)
                    self.assertEqual(result['paid_api_calls_made'], 0)

    def test_unknown_multiple_or_benign_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(G7ManifestError):
                benchmark.main(self.args(directory, malicious_agents=['critic']))
            with self.assertRaises(G7ManifestError):
                benchmark.main(self.args(directory, malicious_agents=['reviewer', 'finalizer']))
            with self.assertRaisesRegex(G7ManifestError, 'benign'):
                benchmark.main(self.args(directory, suite='benign', malicious_agents=['reviewer']))


if __name__ == '__main__':
    unittest.main()
