import unittest

from pydantic import ValidationError

from aciarena.evaluation.records import MessageRecord, RunIdentity, RunRecord, canonical_hash


def benign_row(**overrides):
    row = dict(
        experiment_id='development-v1', task_id='math_0001', mas_id='crewai_seq_nodeleg',
        implementation='reconstructed', attack_id='none', repetition=1, phase='core',
        config_hash=canonical_hash({'model': 'mock'}), attempt_no=1, task_domain='math',
        topology='sequential', model='mock', temperature=0.0, max_tokens=1024, seed=42,
        prompt_version='v1', verifier_version='v1', attack_category=None,
        attack_goal=None, attack_surface=None, malicious_agent=None, payload_hash=None,
        target_invoked=None, payload_injected=None, raw_response='wrong', response='wrong',
        response_agent='finalizer', ground_truth='320', utility_success=False,
        utility_status='valid', attack_success=None, attack_status='not_applicable',
        status='success', error_type=None, error_message=None, llm_call_count=3,
        prompt_tokens=None, completion_tokens=None, latency_ms=10.0,
        started_at='2026-09-08T00:00:00Z', finished_at='2026-09-08T00:00:01Z',
    )
    row.update(overrides)
    row['run_id'] = RunIdentity(**{key: row[key] for key in RunIdentity.model_fields}).deterministic_id()
    return row


def attacked_row(**overrides):
    attack = dict(
        attack_id='disruption_ddos.message.v1', attack_category='disruption_ddos',
        attack_goal='disruption', attack_surface='message', malicious_agent='solver',
        payload_hash=canonical_hash('payload'), target_invoked=True, payload_injected=True,
        attack_success=False, attack_status='valid',
    )
    attack.update(overrides)
    return benign_row(**attack)


class RecordTests(unittest.TestCase):
    def test_false_outcomes_are_complete_and_round_trip(self):
        for row in (benign_row(), attacked_row()):
            with self.subTest(attack=row['attack_id']):
                record = RunRecord(**row)
                self.assertTrue(record.is_complete)
                self.assertEqual(RunRecord.model_validate_json(record.model_dump_json()), record)
                self.assertIsNone(record.prompt_tokens)

    def test_execution_failure_preserves_partial_output(self):
        row = benign_row(status='model_error', error_type='ProviderError', error_message='failed',
                         raw_response=None, response=None, response_agent=None,
                         utility_success=None, utility_status='unknown', llm_call_count=2)
        record = RunRecord(**row)
        self.assertFalse(record.is_complete)
        self.assertIsNone(record.raw_response)

    def test_verifier_failure_is_not_execution_failure_or_false(self):
        row = attacked_row(attack_success=None, attack_status='error',
                           attack_error_type='JudgeParseError', attack_error_message='missing response_type')
        record = RunRecord(**row)
        self.assertEqual(record.status, 'success')
        self.assertFalse(record.is_complete)
        self.assertIsNone(record.attack_success)

    def test_invalid_status_outcome_combinations_are_rejected(self):
        for changes in (
            dict(utility_status='unknown'), dict(utility_success=None),
            dict(utility_success='false'), dict(utility_success=0),
            dict(attack_success=False), dict(target_invoked=False),
            dict(status='timeout'), dict(status='success', error_type='Error'),
            dict(response=None), dict(utility_status='error', utility_success=None),
            dict(attempt_no=0), dict(prompt_tokens=-1), dict(latency_ms=float('nan')),
            dict(finished_at='2026-09-07T00:00:00Z'), dict(started_at='2026-09-08T00:00:00'),
            dict(extra_field='typo'),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RunRecord(**benign_row(**changes))

    def test_attack_requires_metadata(self):
        for changes in (dict(payload_hash=None), dict(attack_surface=None),
                        dict(target_invoked=None), dict(attack_goal='hijacking')):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                RunRecord(**attacked_row(**changes))

    def test_inapplicable_attack_is_complete_and_has_no_outcome(self):
        record = RunRecord(**attacked_row(
            attack_category='hijacking_answer_mapping',
            attack_goal='hijacking',
            attack_status='not_applicable',
            attack_success=None,
        ))
        self.assertTrue(record.is_complete)
        with self.assertRaises(ValidationError):
            RunRecord(**attacked_row(
                attack_category='hijacking_answer_mapping',
                attack_goal='hijacking',
                attack_status='not_applicable',
                attack_success=False,
            ))
        with self.assertRaises(ValidationError):
            RunRecord(**attacked_row(attack_status='not_applicable', attack_success=None))

    def test_attempt_number_is_not_part_of_logical_run_id(self):
        first, retry = RunRecord(**benign_row()), RunRecord(**benign_row(attempt_no=2))
        self.assertEqual(first.run_id, retry.run_id)
        for key, value in {'experiment_id': 'v2', 'task_id': 'math_0002', 'mas_id': 'other',
                           'implementation': 'native', 'attack_id': 'attack', 'repetition': 2,
                           'phase': 'pilot', 'config_hash': canonical_hash({'model': 'other'})}.items():
            identity = {field: getattr(first, field) for field in RunIdentity.model_fields}
            identity[key] = value
            with self.subTest(key=key):
                self.assertNotEqual(first.run_id, RunIdentity(**identity).deterministic_id())

    def test_tampered_id_is_rejected(self):
        row = benign_row()
        row['run_id'] = 'run_' + '0' * 64
        with self.assertRaises(ValidationError):
            RunRecord(**row)

    def test_canonical_hash_order_and_nonfinite(self):
        self.assertEqual(canonical_hash({'a': 1, 'b': '한글'}), canonical_hash({'b': '한글', 'a': 1}))
        with self.assertRaises(ValueError):
            canonical_hash({'bad': float('nan')})

    def test_message_direct_injection_and_partial_trace(self):
        row = dict(run_id=benign_row()['run_id'], attempt_no=1, seq=1, sender='solver',
                   receiver='reviewer', phase='context', content='injected payload',
                   original_content=None, is_attacked=True,
                   attack_id='disruption_ddos.message.v1', created_at='2026-09-08T00:00:00Z')
        record = MessageRecord(**row)
        self.assertEqual(MessageRecord.model_validate_json(record.model_dump_json()), record)
        for changes in (dict(seq=0), dict(attempt_no=0), dict(is_attacked='true'),
                        dict(attack_id='none'), dict(phase='manager_assignment')):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                MessageRecord(**{**row, **changes})


if __name__ == '__main__':
    unittest.main()
