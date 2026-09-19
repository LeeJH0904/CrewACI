from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aciarena.evaluation.legacy_recording import LegacyRecordedExecutor
from aciarena.evaluation.g7_audit import audit_g7, build_g7_plan
from aciarena.evaluation.records import canonical_hash
from aciarena.evaluation.run_writer import RecoveryRequiredError, RunWriter
from aciarena.evaluation.task.base_task import BaseTask


ROOT = Path(__file__).resolve().parents[2]


class StaticTask(BaseTask):
    def __init__(self, query, ground_truth, verdict=1):
        super().__init__(query, ground_truth)
        self.verdict = verdict

    def verify(self):
        return self.verdict


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, *args, **kwargs):
        self.input_tokens += 2
        self.output_tokens += 1
        return self.response


class FakeAgent:
    def __init__(self, name, response):
        self.name = name
        self.profile = f'profile:{name}'
        self.user_information = None
        self.llm = FakeLLM(response)

    def step(self, query, *args, **kwargs):
        return self.llm.call_llm(query)

    def run_step(self, query, *args, **kwargs):
        query = query
        response = self.step(query, *args, **kwargs)
        return response


def fake_mas_builder_factory(manifest, response, behavior='success'):
    def builder(args, llm_config, logger):
        system = manifest.systems[args.mas]

        class FakeMAS:
            def __init__(self):
                self.max_turn = system['max_turn']
                self.agents = {
                    name: FakeAgent(name, response) for name in system['agents']
                }
                self.malicious_agents = list(args.malicious_agents)

            def get_agent(self, name):
                return self.agents[name]

            def run(self, query):
                if behavior == 'model_error':
                    raise RuntimeError('model failed')
                if behavior == 'timeout':
                    raise TimeoutError('model timed out')
                if behavior == 'protocol_error':
                    return {}
                source = system['response_agent']
                if self.malicious_agents:
                    target = self.malicious_agents[0]
                    intermediate = self.agents[target].run_step(query)
                    logger.log_message(target, source, intermediate)
                else:
                    intermediate = query
                final = self.agents[source].run_step(intermediate)
                logger.log_message(source, 'user', final)
                return {'response': final}

        return FakeMAS()

    return builder


class LegacyRecordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.math_row = json.loads(
            (ROOT / 'aciarena/evaluation/datasets/aciarena_math.json').read_text())[0]
        cls.code_row = json.loads(
            (ROOT / 'aciarena/evaluation/datasets/aciarena_code.json').read_text())[0]

    def args(self, directory, *, mas='camel', domain='math', suite='benign', target=None):
        return Namespace(
            mas=mas, task_domain=domain, suite=suite, defense='none',
            attack_mode='continuous', malicious_agents=[] if target is None else [target],
            experiment_id=f'g7-test-{mas}-{domain}-{suite}', output_dir=directory,
        )

    @staticmethod
    def configs():
        model = dict(provider='openai', model_name='mock', temperature=0.0,
                     max_tokens=1024, seed=42, api_key='not-recorded')
        judge = dict(provider='openai', model_name='mock-judge', temperature=0.0,
                     max_tokens=256, seed=42, api_key='not-recorded')
        return model, judge

    def executor(self, directory, *, mas='camel', domain='math', suite='benign',
                 target=None, response='answer', behavior='success'):
        args = self.args(directory, mas=mas, domain=domain, suite=suite, target=target)
        model, judge = self.configs()
        probe = LegacyRecordedExecutor(args, model, judge)
        probe.mas_builder = fake_mas_builder_factory(probe.manifest, response, behavior)
        return probe

    def task(self, domain='math', verdict=1, index=0):
        if index:
            row = json.loads((
                ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json'
            ).read_text())[index]
        else:
            row = self.math_row if domain == 'math' else self.code_row
        return StaticTask(row['problem'], row['answer'], verdict=verdict)

    def test_all_six_legacy_systems_record_configured_final_source(self):
        systems = ('metagpt', 'autogen', 'camel', 'sc', 'llm_debate', 'agentverse')
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            for mas in systems:
                with self.subTest(mas=mas), tempfile.TemporaryDirectory() as directory:
                    domain = 'code' if mas == 'metagpt' else 'math'
                    executor = self.executor(
                        directory, mas=mas, domain=domain, response='final-answer')
                    row = executor.execute(self.task(domain), attack_id='none')
                    self.assertEqual(
                        row.response_agent, executor.manifest.systems[mas]['response_agent'])
                    self.assertEqual(row.status, 'success')
                    self.assertEqual(row.implementation, 'legacy')
                    self.assertTrue(row.is_complete)

    def test_three_attack_surfaces_leave_target_and_payload_evidence(self):
        attacks = (
            'disclosure_math_location.instruction.v1',
            'disclosure_math_location.agent.v1',
            'disclosure_generic_apikey.message.v1',
        )
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            for attack_id in attacks:
                with self.subTest(attack_id=attack_id), tempfile.TemporaryDirectory() as directory:
                    executor = self.executor(
                        directory, suite='disclosure', target='user_proxy',
                        response='final-answer')
                    row = executor.execute(self.task(), attack_id=attack_id)
                    self.assertTrue(row.target_invoked)
                    self.assertTrue(row.payload_injected)
                    messages = executor.writer.read_messages()
                    self.assertTrue(any(message.is_attacked for message in messages))

    def test_disruption_judge_request_and_raw_response_are_recorded(self):
        judge = FakeLLM('{"response_type":"attempted_answer"}')
        with (patch('aciarena.attacks.base_attack.get_llm', return_value=judge),
              tempfile.TemporaryDirectory() as directory):
            executor = self.executor(
                directory, suite='disruption', target='user_proxy',
                response='final-answer')
            row = executor.execute(
                self.task(), attack_id='disruption_ddos.agent.v1')
            self.assertEqual(row.attack_status, 'valid')
            self.assertFalse(row.attack_success)
            messages = executor.writer.read_messages()
            self.assertTrue(any(
                message.phase == 'evaluation'
                and (message.sender, message.receiver)
                == ('attack_verifier', 'judge')
                and 'json_schema' in message.content
                for message in messages))
            self.assertTrue(any(
                message.phase == 'evaluation'
                and (message.sender, message.receiver)
                == ('judge', 'attack_verifier')
                and 'attempted_answer' in message.content
                for message in messages))

    def test_empty_model_timeout_protocol_and_judge_errors_are_distinct(self):
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            with tempfile.TemporaryDirectory() as directory:
                empty = self.executor(directory, response='')
                row = empty.execute(self.task(verdict=0), attack_id='none')
                self.assertEqual((row.status, row.raw_response, row.utility_status),
                                 ('success', '', 'valid'))

            for behavior, expected in (
                    ('model_error', 'model_error'), ('timeout', 'timeout'),
                    ('protocol_error', 'protocol_error')):
                with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as directory:
                    executor = self.executor(directory, behavior=behavior)
                    row = executor.execute(self.task(), attack_id='none')
                    self.assertEqual(row.status, expected)
                    self.assertIsNotNone(row.error_type)

            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(
                    directory, suite='disclosure', target='user_proxy',
                    response='final-answer')
                original = executor._build_attack

                def judge_failure(attack_id, target, *, spec=None):
                    spec, attack = original(attack_id, target, spec=spec)

                    def fail():
                        raise ValueError('judge failed')

                    attack.verify = fail
                    return spec, attack

                executor._build_attack = judge_failure
                row = executor.execute(
                    self.task(), attack_id='disclosure_math_location.agent.v1')
                self.assertEqual(row.status, 'success')
                self.assertEqual(row.utility_status, 'valid')
                self.assertEqual(row.attack_status, 'error')
                self.assertEqual(row.attack_error_type, 'ValueError')

            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(
                    directory, suite='disclosure', target='user_proxy',
                    response='final-answer')
                with patch(
                        'aciarena.attacks.base_attack.get_llm',
                        side_effect=RuntimeError('judge initialization failed')):
                    row = executor.execute(
                        self.task(),
                        attack_id='disclosure_math_location.agent.v1')
                self.assertEqual(row.status, 'model_error')
                self.assertEqual(row.error_type, 'RuntimeError')
                self.assertEqual(row.attack_goal, 'disclosure')
                self.assertEqual(row.attack_surface, 'agent')
                self.assertEqual(row.malicious_agent, 'user_proxy')

    def test_g7_writer_rejects_frozen_paths_and_unsafe_experiment_ids(self):
        model, judge = self.configs()
        frozen = self.args(ROOT / 'outputs/g6')
        with self.assertRaisesRegex(ValueError, 'frozen'):
            LegacyRecordedExecutor(frozen, model, judge)
        unsafe = self.args('/tmp')
        unsafe.experiment_id = '../g6'
        with self.assertRaisesRegex(ValueError, 'directory-safe'):
            LegacyRecordedExecutor(unsafe, model, judge)

    def test_storage_failure_stops_executor_instead_of_becoming_success(self):
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(directory, response='final-answer')
                original = executor.writer.append_run

                def fail(record):
                    raise RecoveryRequiredError('storage failed')

                executor.writer.append_run = fail
                with self.assertRaises(RecoveryRequiredError):
                    executor.execute(self.task(), attack_id='none')
                self.assertTrue(executor.stop)
                executor.writer.append_run = original

    def test_valid_false_resume_and_transient_retry_preserve_attempts(self):
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(directory, response='wrong')
                task = self.task(verdict=0)
                first = executor.execute(task, attack_id='none')
                resumed = executor.execute(task, attack_id='none', resume=True)
                self.assertFalse(first.utility_success)
                self.assertEqual(resumed, first)
                self.assertEqual(len(executor.writer.read_runs()), 1)

            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(directory, response='final-answer')
                calls = {'count': 0}

                def flaky(args, llm_config, logger):
                    behavior = 'timeout' if calls['count'] == 0 else 'success'
                    calls['count'] += 1
                    return fake_mas_builder_factory(
                        executor.manifest, 'final-answer', behavior)(args, llm_config, logger)

                executor.mas_builder = flaky
                first = executor.execute(self.task(), attack_id='none')
                second = executor.execute(self.task(), attack_id='none', retry=True)
                self.assertEqual((first.status, first.attempt_no), ('timeout', 1))
                self.assertEqual((second.status, second.attempt_no), ('success', 2))
                self.assertEqual(len(executor.writer.read_runs()), 2)

    def test_frozen_attack_inapplicability_is_shared_across_systems(self):
        with (patch('aciarena.attacks.base_attack.get_llm',
                    return_value=FakeLLM('judge')),
              tempfile.TemporaryDirectory() as directory):
            executor = self.executor(
                directory, suite='hijacking', target='user_proxy',
                response='answer')
            row = executor.execute(
                self.task(index=16),
                attack_id='hijacking_answer_mapping.agent.v1')
            self.assertEqual(row.status, 'success')
            self.assertEqual(row.attack_status, 'not_applicable')
            self.assertIsNone(row.attack_success)
            self.assertTrue(row.is_complete)

    def test_g7_audit_detects_gap_and_config_drift(self):
        with patch('aciarena.attacks.base_attack.get_llm', return_value=FakeLLM('judge')):
            with tempfile.TemporaryDirectory() as directory:
                executor = self.executor(directory, response='final-answer')
                row = executor.execute(self.task(), attack_id='none')
                plan = build_g7_plan(
                    experiment_id=row.experiment_id,
                    mas_id=row.mas_id,
                    task_ids=[row.task_id],
                    attack_ids=['none'],
                    repetition=row.repetition,
                    phase=row.phase,
                    config_hash=row.config_hash,
                )
                self.assertTrue(audit_g7(
                    executor.writer, plan, executor.manifest,
                    require_injection=False)['ok'])

                wrong_plan = build_g7_plan(
                    experiment_id=row.experiment_id,
                    mas_id=row.mas_id,
                    task_ids=[row.task_id],
                    attack_ids=['none'],
                    repetition=row.repetition,
                    phase=row.phase,
                    config_hash='0' * 64,
                )
                report = audit_g7(
                    executor.writer, wrong_plan, executor.manifest,
                    require_injection=False)
                self.assertFalse(report['ok'])
                self.assertEqual(report['missing_runs'], 1)
                self.assertTrue(any('config_or_identity_drift' in error
                                    for error in report['errors']))

                snapshot = executor.writer.directory / 'configs' / f'{row.config_hash}.json'
                data = json.loads(snapshot.read_text())
                data['sources']['aciarena/evaluation/legacy_recording.py'] = '0' * 64
                snapshot.write_text(json.dumps(data))
                report = audit_g7(
                    executor.writer, plan, executor.manifest,
                    require_injection=False)
                self.assertFalse(report['ok'])
                self.assertTrue(any('config_snapshot_hash_mismatch' in error
                                    for error in report['errors']))


if __name__ == '__main__':
    unittest.main()
