"""G7 legacy acceptance checks with the real six MAS and an offline LLM."""

from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark

from aciarena.agent_components.base_agent import BaseAgent
from aciarena.evaluation.g7_audit import audit_g7, build_g7_plan
from aciarena.evaluation.legacy_recording import LegacyRecordedExecutor
from aciarena.evaluation.task.base_task import BaseTask


ROOT = Path(__file__).resolve().parents[2]
MODEL = {
    'provider': 'openai',
    'model_name': 'offline-acceptance',
    'temperature': 0.0,
    'max_tokens': 256,
    'seed': 42,
    'api_key': 'must-not-be-used',
}
SYSTEMS = ('metagpt', 'autogen', 'camel', 'sc', 'llm_debate', 'agentverse')


class StaticTask(BaseTask):
    """Keep acceptance focused on the MAS/recording path, not verifier quality."""

    def verify(self):
        return 1


class OfflineLLM:
    """Protocol-aware deterministic stand-in for all legacy Agent LLMs."""

    def __init__(self, agent, calls):
        self.agent = agent
        self.calls = calls
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, messages, **kwargs):
        self.calls.append((type(self.agent).__name__, messages, dict(kwargs)))
        self.input_tokens += 5
        self.output_tokens += 2
        name = type(self.agent).__name__
        module = type(self.agent).__module__
        if getattr(self.agent, 'name', None) == 'finalizer':
            return '320'
        if name == 'RoleAssignerAgent':
            return '1. a mathematical solver.\n2. an independent reviewer.'
        if name == 'EvaluatorAgent':
            return 'Correctness: 1\nResponse: The offline solution is accepted.'
        if name == 'CriticAgent' and '.agentverse.' in module:
            return 'The proposed solution is consistent. [Agree]'
        if name == 'QAEngineerAgent':
            return (
                '<answer>\n## Test Results\n- offline: Pass\n\n'
                '## Bugs Found\n- None\n\n## Improvement Suggestions\n- None\n\n'
                '## Validated Code\n```python\ndef solve():\n    return 1\n```\n</answer>'
            )
        return 'offline final answer'


class OfflineJudge:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, messages, **kwargs):
        self.input_tokens += 3
        self.output_tokens += 1
        return '{"response_type":"attempted_answer"}'


class G7LegacyAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {
            domain: json.loads((
                ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json'
            ).read_text())[0]
            for domain in ('math', 'code')
        }

    @staticmethod
    def args(directory, mas, domain):
        return Namespace(
            mas=mas,
            task_domain=domain,
            suite='benign',
            defense='none',
            attack_mode='continuous',
            malicious_agents=[],
            experiment_id=f'g7-acceptance-{mas}-{domain}',
            output_dir=directory,
        )

    def test_real_six_legacy_mas_complete_one_recorded_mock_run(self):
        calls = []

        def init_llm(agent, config):
            self.assertEqual(config['model_name'], 'offline-acceptance')
            return OfflineLLM(agent, calls)

        with patch.object(BaseAgent, 'init_llm', init_llm):
            for mas in SYSTEMS:
                with self.subTest(mas=mas), tempfile.TemporaryDirectory() as directory:
                    domain = 'code' if mas == 'metagpt' else 'math'
                    row = self.rows[domain]
                    task = StaticTask(row['problem'], row['answer'])
                    executor = LegacyRecordedExecutor(
                        self.args(directory, mas, domain), MODEL, MODEL)
                    record = executor.execute(task, attack_id='none')

                    expected = executor.manifest.systems[mas]
                    self.assertEqual(record.status, 'success')
                    self.assertEqual(record.utility_status, 'valid')
                    self.assertTrue(record.utility_success)
                    self.assertEqual(record.implementation, 'legacy')
                    self.assertEqual(record.response_agent, expected['response_agent'])
                    self.assertEqual(record.topology, expected['topology'])
                    self.assertGreater(record.llm_call_count, 0)
                    self.assertEqual(record.usage_missing_calls, 0)
                    self.assertTrue(any(
                        message.phase == 'final'
                        and message.sender == expected['response_agent']
                        and message.content == record.raw_response
                        for message in executor.writer.read_messages()
                    ))

        self.assertGreater(len(calls), len(SYSTEMS))

    def test_crewai_g7_execute_path_uses_recorded_contract_offline(self):
        calls = []

        def init_llm(agent, config):
            return OfflineLLM(agent, calls)

        with (patch.object(BaseAgent, 'init_llm', init_llm),
              tempfile.TemporaryDirectory() as directory):
            args = Namespace(
                attack_ids=None,
                experiment_id='g7-crewai-acceptance',
                experiment_config='configs/experiments/g5_v2.yaml',
                phase='core',
                repetition=1,
                resume=False,
                retry_errors=False,
                execute=True,
                model_config=None,
                judge_config=None,
                mas='crewai_seq_nodeleg',
                suite='benign',
                attack_mode='continuous',
                defense='none',
                task_domain='math',
                max_workers=1,
                limit=None,
                task_ids=['math_0000'],
                output_dir=directory,
                malicious_agents=[],
            )
            result = benchmark.main(args)
            self.assertEqual(result['planned_runs'], 1)
            self.assertEqual(result['completed_runs'], 1)
            self.assertEqual(result['execution_errors'], 0)
            self.assertTrue(result['audit']['ok'])
            self.assertTrue((
                Path(directory) / 'g7-crewai-acceptance/runs.jsonl'
            ).is_file())
            self.assertGreater(len(calls), 0)

    def test_real_camel_records_all_three_attack_surface_evidence(self):
        calls = []
        attacks = {
            'instruction': 'disclosure_math_location.instruction.v1',
            'agent': 'disclosure_math_location.agent.v1',
            'message': 'disclosure_generic_apikey.message.v1',
        }

        def init_llm(agent, config):
            return OfflineLLM(agent, calls)

        with (patch.object(BaseAgent, 'init_llm', init_llm),
              patch('aciarena.attacks.base_attack.get_llm',
                    side_effect=lambda config: OfflineJudge())):
            for surface, attack_id in attacks.items():
                with (self.subTest(surface=surface),
                      tempfile.TemporaryDirectory() as directory):
                    args = self.args(directory, 'camel', 'math')
                    args.suite = 'disclosure'
                    args.malicious_agents = ['user_proxy']
                    source = self.rows['math']
                    task = StaticTask(source['problem'], source['answer'])
                    executor = LegacyRecordedExecutor(args, MODEL, MODEL)
                    record = executor.execute(task, attack_id=attack_id)
                    self.assertEqual(record.status, 'success')
                    self.assertTrue(record.target_invoked)
                    self.assertTrue(record.payload_injected)
                    self.assertEqual(record.attack_surface, surface)
                    expected_phase = {
                        'instruction': 'llm_input',
                        'agent': 'profile',
                        'message': 'turn',
                    }[surface]
                    self.assertTrue(any(
                        message.is_attacked and message.phase == expected_phase
                        and message.sender == 'user_proxy'
                        for message in executor.writer.read_messages()
                    ))

    def test_fixed_but_dormant_target_is_preserved_as_headline_zero(self):
        calls = []

        def init_llm(agent, config):
            return OfflineLLM(agent, calls)

        with (patch.object(BaseAgent, 'init_llm', init_llm),
              patch('aciarena.attacks.base_attack.get_llm',
                    side_effect=lambda config: OfflineJudge()),
              tempfile.TemporaryDirectory() as directory):
            args = self.args(directory, 'camel', 'math')
            args.suite = 'hijacking'
            source = self.rows['math']
            task = StaticTask(source['problem'], source['answer'])
            executor = LegacyRecordedExecutor(args, MODEL, MODEL)
            record = executor.execute(
                task, attack_id='hijacking_answer_mapping.agent.v1')
            self.assertEqual(record.malicious_agent, 'critic')
            self.assertFalse(record.target_invoked)
            self.assertTrue(record.payload_injected)

            plan = build_g7_plan(
                experiment_id=record.experiment_id,
                mas_id=record.mas_id,
                task_ids=[record.task_id],
                attack_ids=[record.attack_id],
                repetition=record.repetition,
                phase=record.phase,
                config_hash=record.config_hash,
            )
            report = audit_g7(
                executor.writer, plan, executor.manifest,
                require_injection=False)
            self.assertTrue(report['ok'], report['errors'])
            self.assertEqual(report['target_not_invoked'], 1)


if __name__ == '__main__':
    unittest.main()
