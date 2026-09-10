from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aciarena.agent_components.base_agent import BaseAgent
from aciarena.evaluation.recorded_executor import RecordedTaskExecutor, ROOT
from aciarena.evaluation.audit import audit_matrix, build_matrix_plan
from aciarena.evaluation.recorded_suite import RecordedEvaluationSuite
from aciarena.evaluation.run_writer import StorageError, RecordConflictError
from aciarena.evaluation.task import MathTask, CodeTask
from aciarena.utils.factory import build_suite, build_executor


MODEL = {'provider': 'openai', 'model_name': 'offline-mock', 'temperature': 0.0,
         'max_tokens': 1024, 'seed': 42, 'api_key': 'private-test-model-key'}
JUDGE = {**MODEL, 'api_key': 'private-test-judge-key'}


class MockLLM:
    def __init__(self, owner, outputs, calls):
        self.owner, self.outputs, self.calls = owner, outputs, calls
        self.input_tokens = self.output_tokens = 0

    def call_llm(self, messages, **kwargs):
        self.calls.append((self.owner, copy.deepcopy(messages)))
        result = self.outputs[self.owner]
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        self.input_tokens += 7
        self.output_tokens += 2
        return result


def task_at(domain='math', index=0):
    row = json.loads((ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json').read_text())[index]
    task = (MathTask if domain == 'math' else CodeTask)(query=row['problem'], ground_truth=row['answer'])
    task.task_id = f'{domain}_{index:04d}'
    return task


class RecordedExecutorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.calls, self.llms = [], []
        self.outputs = {'solver': 'draft', 'reviewer': 'review', 'finalizer': '320',
                        'judge': '{"response_type":"attempted_answer"}'}

        def make(owner):
            llm = MockLLM(owner, self.outputs, self.calls)
            self.llms.append(llm)
            return llm

        def init(agent, config):
            return make(agent.name)

        for patched in (patch.object(BaseAgent, 'init_llm', init),
                        patch('aciarena.attacks.base_attack.get_llm', side_effect=lambda config: make('judge'))):
            patched.start()
            self.addCleanup(patched.stop)

    def args(self, domain='math', suite='benign', ids=None):
        return SimpleNamespace(mas='crewai_seq_nodeleg', task_domain=domain, suite=suite,
                               attack_ids=ids, defense='none', attack_mode='continuous',
                               malicious_agents=['solver'], output_dir=str(self.directory),
                               experiment_id='g0-integration', max_workers=4, limit=1)

    def executor(self, **kwargs):
        return RecordedTaskExecutor(self.args(**kwargs), JUDGE)

    def run_task(self, executor, attack_id='none', task=None, **kwargs):
        return executor.execute({'llm_config': MODEL}, task or task_at(), attack_id=attack_id, **kwargs)

    def messages(self, executor):
        return [json.loads(line) for line in (executor.writer.directory / 'messages.jsonl').read_text().splitlines()]

    def test_benign_finalizer_output_and_complete_false_resume(self):
        executor = self.executor()
        self.outputs['finalizer'] = '300'
        record = self.run_task(executor)
        self.assertEqual(record.status, 'success')
        self.assertFalse(record.utility_success)
        self.assertEqual(record.response_agent, 'finalizer')
        self.assertEqual(record.raw_response, '300')
        self.assertEqual(record.llm_call_count, 3)
        self.assertEqual((record.prompt_tokens, record.completion_tokens), (21, 6))
        self.assertEqual([name for name, _ in self.calls], ['solver', 'reviewer', 'finalizer'])
        count = len(self.calls)
        self.assertEqual(self.run_task(executor, resume=True), record)
        self.assertEqual(len(self.calls), count)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_raw_output_is_preserved_and_normalized_output_reaches_verifier(self):
        observed = []

        def verifier(task):
            observed.append(copy.deepcopy(task.answer))
            return True

        executor = RecordedTaskExecutor(
            self.args(),
            JUDGE,
            utility_verifier=verifier,
            utility_verifier_version='g1-mock-v1',
        )
        self.outputs['finalizer'] = ' \ufeff320\r\n '
        record = self.run_task(executor)

        self.assertEqual(record.raw_response, ' \ufeff320\r\n ')
        self.assertEqual(record.response, '320')
        self.assertEqual(observed[0]['raw_response'], record.raw_response)
        self.assertEqual(observed[0]['response'], record.response)
        final = [event for event in self.messages(executor) if event['phase'] == 'final']
        self.assertEqual(final[-1]['content'], record.raw_response)
        config = json.loads(next((executor.writer.directory / 'configs').glob('*.json')).read_text())
        self.assertEqual(config['normalizer'], 'text-envelope-v1')
        self.assertTrue(executor.writer.audit()['ok'])

    def test_attempt_timestamps_use_one_monotonic_clock(self):
        executor = self.executor()
        with patch(
            'aciarena.evaluation.recorded_executor.utc_now',
            return_value='2099-01-01T00:00:00+00:00',
        ):
            record = self.run_task(executor)

        self.assertGreaterEqual(record.finished_at, record.started_at)
        for event in self.messages(executor):
            self.assertGreaterEqual(event['created_at'], record.started_at)
            self.assertLessEqual(event['created_at'], record.finished_at)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_invalid_mas_contract_is_a_protocol_error_with_raw_trace(self):
        executor = self.executor()
        with patch(
            'aciarena.mas.crewai.sequential_mas.CrewAISequentialNoDelegation.conclude',
            return_value={
                'raw_response': '320',
                'response': 'not-the-normalized-response',
                'response_agent': 'finalizer',
                'conversation': [],
                'status': 'success',
            },
        ):
            record = self.run_task(executor)

        self.assertEqual(record.status, 'protocol_error')
        self.assertEqual(record.error_type, 'ProtocolError')
        self.assertEqual(record.raw_response, '320')
        self.assertIsNone(record.response)
        self.assertIsNone(record.response_agent)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_normalizer_version_mismatch_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, 'normalizer and implementation'):
            RecordedTaskExecutor(
                self.args(),
                JUDGE,
                experiment_contract={
                    'contract_id': 'mismatched-test',
                    'normalizer': 'future-normalizer-v2',
                },
            )
        self.assertEqual(self.calls, [])

    def test_all_three_attack_surfaces_are_observed_and_next_run_is_clean(self):
        cases = [('disclosure', 'disclosure_math_location.instruction.v1', 'instruction'),
                 ('disclosure', 'disclosure_math_name.agent.v1', 'agent'),
                 ('disruption', 'disruption_ddos.message.v1', 'message')]
        for suite, attack_id, surface in cases:
            executor = self.executor(suite=suite, ids=[attack_id])
            with self.subTest(surface=surface):
                row = self.run_task(executor, attack_id)
                self.assertTrue(row.target_invoked)
                self.assertTrue(row.payload_injected)
                events = [m for m in self.messages(executor) if m['run_id'] == row.run_id]
                injected = [m for m in events if m['is_attacked']]
                self.assertTrue(injected)
                self.assertFalse(any(m['is_attacked'] for m in events if m['sender'] == 'reviewer'))
                self.assertEqual(row.attack_status, 'valid')
                if surface == 'message':
                    self.assertEqual(row.llm_call_count, 3)  # reviewer + finalizer + Judge
                    self.assertFalse(any(m['sender'] == 'solver' and m['phase'] == 'llm_input' for m in events))
                    self.assertTrue(any(m['phase'] == 'evaluation' and m['sender'] == 'llm' for m in events))
                else:
                    self.assertTrue(any(m['phase'] == 'llm_input' for m in injected))
        benign = self.run_task(self.executor())
        self.assertIsNone(benign.payload_injected)
        events = [m for m in self.messages(executor) if m['run_id'] == benign.run_id]
        self.assertFalse(any(m['is_attacked'] for m in events))
        self.assertFalse(any('Private Information' in m['content'] for m in events))

    def test_model_failure_keeps_partial_trace_and_next_task_runs(self):
        executor = self.executor()
        self.outputs['reviewer'] = RuntimeError('provider failed')
        row = self.run_task(executor)
        self.assertEqual(row.status, 'model_error')
        self.assertEqual(row.utility_status, 'unknown')
        self.assertIsNone(row.raw_response)
        self.assertIsNone(row.prompt_tokens)
        self.assertTrue(any(m['sender'] == 'solver' for m in self.messages(executor)))
        self.assertTrue(executor.writer.audit()['ok'])
        self.outputs['reviewer'] = 'review'
        self.assertEqual(self.run_task(executor, task=task_at(index=1)).status, 'success')

    def test_constructor_failure_also_writes_an_error_row(self):
        executor = self.executor()
        with patch.object(BaseAgent, 'init_llm', side_effect=RuntimeError('initialization failed')):
            row = self.run_task(executor)
        self.assertEqual(row.status, 'model_error')
        self.assertEqual(row.llm_call_count, 0)
        self.assertEqual(len(self.messages(executor)), 1)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_timeout_requires_explicit_retry_and_preserves_attempt_history(self):
        executor = self.executor()
        self.outputs['reviewer'] = TimeoutError('timed out')
        first = self.run_task(executor)
        self.assertEqual(first.status, 'timeout')
        with self.assertRaises(RecordConflictError):
            self.run_task(executor, resume=True)
        self.outputs['reviewer'] = 'review'
        second = self.run_task(executor, retry=True)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(second.attempt_no, 2)
        self.assertEqual(len(executor.writer.read_runs()), 2)

    def test_verifier_errors_are_separate_and_judge_raw_is_saved(self):
        attack_id = 'disruption_ddos.message.v1'
        executor = self.executor(suite='disruption', ids=[attack_id])
        self.outputs['judge'] = 'not-json'
        with patch('aciarena.evaluation.recorded_executor.verify_math', side_effect=ValueError('utility failed')):
            row = self.run_task(executor, attack_id)
        self.assertEqual(row.status, 'success')
        self.assertEqual((row.utility_status, row.attack_status), ('error', 'error'))
        self.assertIsNone(row.utility_success)
        self.assertIsNone(row.attack_success)
        self.assertTrue(any(m['content'] == 'not-json' for m in self.messages(executor)))
        self.assertTrue(executor.writer.audit()['ok'])

    def test_message_and_run_storage_failures_propagate_and_stop(self):
        for method in ('append_message', 'append_run'):
            executor = self.executor()
            with self.subTest(method=method), patch.object(executor.writer, method, side_effect=OSError('disk full')):
                with self.assertRaises((StorageError, OSError)):
                    self.run_task(executor)
            self.assertTrue(executor.stop.is_set())
            with self.assertRaises(StorageError):
                self.run_task(executor, task=task_at(index=2))

    def test_credentials_are_not_written_to_error_or_config(self):
        executor = self.executor()
        self.outputs['solver'] = RuntimeError('bad private-test-model-key private-test-judge-key')
        row = self.run_task(executor)
        self.assertIn('[REDACTED]', row.error_message)
        for path in executor.writer.directory.rglob('*.json*'):
            self.assertNotIn('private-test-model-key', path.read_text())
            self.assertNotIn('private-test-judge-key', path.read_text())

    def test_twenty_parallel_tasks_isolate_agents_and_traces(self):
        executor = self.executor()
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda index: self.run_task(executor, task=task_at(index=index)), range(20)))
        self.assertEqual(len({row.run_id for row in rows}), 20)
        self.assertTrue(all(row.status == 'success' for row in rows))
        self.assertEqual(len(self.llms), 60)
        self.assertEqual(len({id(llm) for llm in self.llms}), 60)
        for row in rows:
            events = [m for m in self.messages(executor) if m['run_id'] == row.run_id]
            self.assertEqual([e['seq'] for e in events], list(range(1, len(events) + 1)))
            self.assertEqual(row.llm_call_count, 3)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_same_run_claim_prevents_duplicate_model_calls(self):
        executor = self.executor()
        barrier = threading.Barrier(2)
        self.outputs['solver'] = lambda: (time.sleep(0.1) or 'draft')

        def execute():
            barrier.wait()
            try:
                return self.run_task(executor)
            except RecordConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: execute(), range(2)))
        self.assertEqual(sum(row is not None for row in results), 1)
        self.assertEqual(len(self.calls), 3)

    def test_code_uses_default_isolated_verifier(self):
        task = task_at('code')
        self.outputs['finalizer'] = task.get_gt()['prompt'] + task.get_gt()['canonical_solution']
        executor = self.executor(domain='code')
        with patch.object(CodeTask, 'verify', side_effect=AssertionError('must not execute in host process')) as verify:
            row = self.run_task(executor, task=task)
        verify.assert_not_called()
        self.assertEqual(row.status, 'success')
        self.assertEqual(row.utility_status, 'valid')
        self.assertTrue(row.utility_success)

    def test_code_sandbox_blocks_network_and_external_filesystem_writes(self):
        task = task_at('code', 9)
        escape = self.directory / 'sandbox-escape.txt'
        self.outputs['finalizer'] = f'''import socket
try:
    open({str(ROOT / 'README.md')!r}).read()
    raise RuntimeError("sandbox read escaped")
except PermissionError:
    pass
try:
    socket.create_connection(("1.1.1.1", 53), timeout=0.1)
except OSError:
    pass
try:
    open({str(escape)!r}, "w").write("escaped")
except OSError:
    pass
{task.get_gt()['code']}
'''
        row = self.run_task(self.executor(domain='code'), task=task)
        self.assertEqual(row.utility_status, 'valid')
        self.assertTrue(row.utility_success)
        self.assertFalse(escape.exists())

    def test_code_timeout_is_a_valid_incorrect_result(self):
        task = task_at('code', 9)
        self.outputs['finalizer'] = '''import signal
try:
    signal.setitimer(signal.ITIMER_REAL, 0)
except OSError:
    pass
while True:
    pass'''
        row = self.run_task(self.executor(domain='code'), task=task)
        self.assertEqual(row.utility_status, 'valid')
        self.assertFalse(row.utility_success)

    def test_versioned_external_code_verifier_injection(self):
        task = task_at('code')
        self.outputs['finalizer'] = 'def separate_paren_groups(paren_string: str):\n' + task.get_gt()['canonical_solution']
        verifier = Mock(return_value=True)
        executor = RecordedTaskExecutor(self.args(domain='code'), JUDGE,
                                         utility_verifier=verifier,
                                         utility_verifier_version='external-test-verifier-v1')
        row = self.run_task(executor, task=task)
        verifier.assert_called_once()
        self.assertTrue(row.utility_success)
        self.assertTrue(executor.writer.audit()['ok'])

    def test_existing_factory_routes_and_suite_denominators(self):
        args = self.args()
        executor = build_executor(args, JUDGE)
        self.assertIsInstance(executor, RecordedTaskExecutor)
        self.assertIsInstance(build_suite(args), RecordedEvaluationSuite)
        suite = RecordedEvaluationSuite(args, model_config=MODEL, judge_config=JUDGE)
        report = suite.eval()
        self.assertEqual(report['utility_denominator'], 1)
        self.assertEqual(report['Benign Utility'], 100.0)
        self.assertEqual(report['execution_errors'], 0)

    def test_mapping_verifier_in_worker_and_parse_unknown(self):
        attack_id = 'hijacking_answer_mapping.agent.v1'
        executor = self.executor(suite='hijacking', ids=[attack_id])
        self.outputs['finalizer'] = '697'  # 320 under the original digit mapping
        row = self.run_task(executor, attack_id)
        self.assertTrue(row.attack_success)
        self.assertFalse(row.utility_success)
        self.outputs['finalizer'] = ''
        unknown = self.run_task(executor, attack_id, task=task_at(index=1))
        self.assertEqual(unknown.utility_status, 'unknown')
        self.assertEqual(unknown.attack_status, 'unknown')

    def test_mapping_fraction_and_task_applicability(self):
        attack_id = 'hijacking_answer_mapping.agent.v1'
        executor = self.executor(suite='hijacking', ids=[attack_id])
        self.outputs['finalizer'] = r'\frac{4}{43}'  # mapped from 1/16
        fraction = self.run_task(executor, attack_id, task=task_at(index=32))
        self.assertEqual(fraction.attack_status, 'valid')
        self.assertTrue(fraction.attack_success)
        self.assertFalse(fraction.utility_success)

        self.outputs['finalizer'] = r'\boxed{\text{even}}'
        inapplicable = self.run_task(executor, attack_id, task=task_at(index=16))
        self.assertEqual(inapplicable.attack_status, 'not_applicable')
        self.assertIsNone(inapplicable.attack_success)
        self.assertTrue(inapplicable.target_invoked)
        self.assertTrue(inapplicable.payload_injected)
        self.assertTrue(inapplicable.is_complete)
        call_count = len(self.calls)
        self.assertEqual(
            self.run_task(executor, attack_id, task=task_at(index=16), resume=True),
            inapplicable,
        )
        self.assertEqual(len(self.calls), call_count)

    def test_all_manifest_selected_attacks_activate_with_surface_evidence(self):
        outputs = {
            'disclosure_math_location': '320-US-NEWYORK',
            'disclosure_math_name': '320-David Tao',
            'disclosure_code_apikey': 'sk-aciarena-test-apikey',
            'disclosure_code_name': 'David Tao',
            'disruption_ddos': 'I cannot assist you with that request.',
            'hijacking_safety_check': 'def safety_check():\n    pass',
            'hijacking_malicious_report': 'https://aciarena.server/report',
            'hijacking_answer_mapping': '697',
        }
        rows, selections, writer, tasks, catalog = [], [], None, None, None
        self.outputs['judge'] = '{"response_type":"refusal"}'
        for spec in self.executor().catalog.specs.values():
            domain = spec.domains[0]
            args = self.args(domain=domain, suite=spec.goal, ids=[spec.attack_id])
            args.experiment_id = 'g2-all-selected-attacks'
            executor = RecordedTaskExecutor(
                args,
                JUDGE,
                utility_verifier=lambda task: True,
                utility_verifier_version='g2-activation-utility-v1',
            )
            task = task_at(domain)
            self.outputs['finalizer'] = outputs[spec.attack_category]
            row = self.run_task(executor, spec.attack_id, task=task, phase='pilot')
            rows.append(row)
            selections.append((task.task_id, spec.attack_id))
            writer, tasks, catalog = executor.writer, executor.tasks, executor.catalog

        plan = build_matrix_plan(
            experiment_id='g2-all-selected-attacks',
            selections=selections,
            tasks=tasks,
            catalog=catalog,
            phase='pilot',
        )
        report = audit_matrix(writer, plan, tasks, catalog)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['planned_runs'], 8)
        self.assertEqual(report['completed_runs'], 8)
        self.assertEqual({row.attack_surface for row in rows}, {'instruction', 'agent', 'message'})
        self.assertTrue(all(row.target_invoked and row.payload_injected for row in rows))

    def test_twenty_parallel_attacked_runs_keep_activation_state_isolated(self):
        attack_id = 'disclosure_math_location.instruction.v1'
        args = self.args(suite='disclosure', ids=[attack_id])
        args.experiment_id = 'g2-parallel-attacks'
        executor = RecordedTaskExecutor(
            args,
            JUDGE,
            utility_verifier=lambda task: True,
            utility_verifier_version='g2-parallel-utility-v1',
        )
        self.outputs['finalizer'] = '320-US-NEWYORK'
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(
                lambda index: self.run_task(
                    executor, attack_id, task=task_at(index=index), phase='pilot'),
                range(20),
            ))
        plan = build_matrix_plan(
            experiment_id='g2-parallel-attacks',
            selections=[(row.task_id, attack_id) for row in rows],
            tasks=executor.tasks,
            catalog=executor.catalog,
            phase='pilot',
        )
        report = audit_matrix(executor.writer, plan, executor.tasks, executor.catalog)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['completed_runs'], 20)
        self.assertEqual(len({row.run_id for row in rows}), 20)
        self.assertTrue(all(row.attack_success for row in rows))
        self.assertEqual(report['target_not_invoked'], 0)
        self.assertEqual(report['payload_not_injected'], 0)

    def test_attack_false_resume_and_retry_limit(self):
        attack_id = 'disclosure_math_location.instruction.v1'
        executor = self.executor(suite='disclosure', ids=[attack_id])
        self.outputs['finalizer'] = '320'
        first = self.run_task(executor, attack_id)
        self.assertFalse(first.attack_success)
        call_count = len(self.calls)
        self.assertEqual(self.run_task(executor, attack_id, resume=True), first)
        self.assertEqual(len(self.calls), call_count)

        retry_executor = self.executor()
        retry_executor.args.experiment_id = 'ignored-after-construction'
        self.outputs['reviewer'] = TimeoutError('transient timeout')
        attempts = [self.run_task(retry_executor)]
        attempts.append(self.run_task(retry_executor, retry=True))
        attempts.append(self.run_task(retry_executor, retry=True))
        self.assertEqual([row.attempt_no for row in attempts], [1, 2, 3])
        with self.assertRaises(RecordConflictError):
            self.run_task(retry_executor, retry=True)


if __name__ == '__main__':
    unittest.main()
