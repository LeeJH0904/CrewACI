import tempfile
from pathlib import Path
import unittest

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import (
    audit_matrix,
    audit_matrix_records,
    build_manifest_plan,
    build_matrix_plan,
)
from aciarena.evaluation.recorded_executor import load_task_manifest
from aciarena.evaluation.records import MessageRecord, RunIdentity, RunRecord, canonical_hash
from aciarena.evaluation.run_writer import RunWriter
from tests.unit.test_records import attacked_row


ATTACK_ID = 'disruption_ddos.message.v1'


class MatrixAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.tasks = load_task_manifest()
        cls.catalog = AttackCatalog()
        cls.spec = cls.catalog.get(ATTACK_ID, task_domain='math')

    def plan(self, selections=None):
        return build_matrix_plan(
            experiment_id='development-v1',
            selections=selections or [('math_0001', ATTACK_ID)],
            tasks=self.tasks,
            catalog=self.catalog,
            phase='core',
        )

    def record(self, **changes):
        metadata = dict(
            task_id='math_0001',
            ground_truth='220',
            attack_id=ATTACK_ID,
            attack_category=self.spec.attack_category,
            attack_goal=self.spec.goal,
            attack_surface=self.spec.surface,
            malicious_agent=self.spec.target,
            payload_hash=self.spec.payload_hash,
            verifier_version='test-utility/' + self.spec.verifier_source_hash,
            target_invoked=True,
            payload_injected=True,
            attack_success=False,
            attack_status='valid',
        )
        metadata.update(changes)
        return RunRecord(**attacked_row(**metadata))

    def evidence(self, record, **changes):
        values = dict(
            run_id=record.run_id,
            attempt_no=record.attempt_no,
            seq=1,
            sender='solver',
            receiver='reviewer',
            phase='context',
            content=self.spec.payload,
            original_content=None,
            is_attacked=True,
            attack_id=record.attack_id,
            created_at=record.started_at,
        )
        values.update(changes)
        return MessageRecord(**values)

    def test_complete_matrix_and_message_surface_evidence_pass(self):
        record = self.record()
        report = audit_matrix_records(
            self.plan(), [record], [self.evidence(record)], self.tasks, self.catalog)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['completed_runs'], 1)
        self.assertEqual(report['target_not_invoked'], 0)
        self.assertEqual(report['payload_not_injected'], 0)

    def test_missing_duplicate_drift_and_additional_runs_are_detected(self):
        record = self.record()
        missing_plan = self.plan([
            ('math_0001', ATTACK_ID),
            ('math_0002', ATTACK_ID),
        ])
        missing = audit_matrix_records(
            missing_plan, [record], [self.evidence(record)], self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('missing_planned_runs:') for error in missing['errors']))

        duplicate = audit_matrix_records(
            self.plan(), [record, record], [self.evidence(record)], self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('duplicate_attempts:') for error in duplicate['errors']))

        drift = self.record(config_hash=canonical_hash({'different': True}))
        config_drift = audit_matrix_records(
            self.plan(), [record, drift], [self.evidence(record), self.evidence(drift)],
            self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('config_or_identity_drift:')
                            for error in config_drift['errors']))

        additional = self.record(task_id='math_0002')
        unexpected = audit_matrix_records(
            self.plan(), [record, additional], [self.evidence(record), self.evidence(additional)],
            self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('unexpected_runs:') for error in unexpected['errors']))

    def test_activation_metadata_and_message_sequence_fail_closed(self):
        inactive = self.record(target_invoked=False, payload_injected=False,
                               payload_hash=canonical_hash('wrong payload'))
        bad_message = self.evidence(inactive, seq=2, is_attacked=False)
        report = audit_matrix_records(
            self.plan(), [inactive], [bad_message], self.tasks, self.catalog)
        prefixes = {error.split(':', 1)[0] for error in report['errors']}
        self.assertTrue({
            'target_not_invoked', 'payload_not_injected',
            'attack_surface_evidence_missing', 'attack_metadata_mismatch',
            'message_sequence',
        } <= prefixes)

        wrong_payload = self.evidence(self.record(), content='not the selected payload')
        payload_report = audit_matrix_records(
            self.plan(), [self.record()], [wrong_payload], self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('attack_payload_evidence_mismatch:')
                            for error in payload_report['errors']))

        stale_verifier = self.record(verifier_version='test-utility/' + '0' * 64)
        verifier_report = audit_matrix_records(
            self.plan(), [stale_verifier], [self.evidence(stale_verifier)],
            self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('attack_verifier_version_mismatch:')
                            for error in verifier_report['errors']))

    def test_ground_truth_and_answer_mapping_applicability_are_audited(self):
        mapping = self.catalog.get(
            'hijacking_answer_mapping.agent.v1', task_domain='math')
        values = attacked_row(
            task_id='math_0016',
            attack_id=mapping.attack_id,
            attack_category=mapping.attack_category,
            attack_goal=mapping.goal,
            attack_surface=mapping.surface,
            malicious_agent=mapping.target,
            payload_hash=mapping.payload_hash,
            verifier_version='test-utility/' + mapping.verifier_source_hash,
            ground_truth='\\text{even}',
            attack_status='valid',
            attack_success=False,
        )
        record = RunRecord(**values)
        plan = build_matrix_plan(
            experiment_id='development-v1',
            selections=[('math_0016', mapping.attack_id)],
            tasks=self.tasks,
            catalog=self.catalog,
            phase='core',
        )
        evidence = MessageRecord(
            run_id=record.run_id,
            attempt_no=1,
            seq=1,
            sender='solver',
            receiver='solver',
            phase='profile',
            content=mapping.payload,
            original_content='original profile',
            is_attacked=True,
            attack_id=mapping.attack_id,
            created_at=record.started_at,
        )
        report = audit_matrix_records(
            plan, [record], [evidence], self.tasks, self.catalog,
            require_injection=False)
        self.assertTrue(any(error.startswith('attack_applicability_mismatch:')
                            for error in report['errors']))

        tampered = self.record(ground_truth='tampered')
        tampered_report = audit_matrix_records(
            self.plan(), [tampered], [self.evidence(tampered)], self.tasks, self.catalog)
        self.assertTrue(any(error.startswith('ground_truth_manifest_mismatch:')
                            for error in tampered_report['errors']))

    def test_non_retryable_retry_and_retry_limit_are_detected(self):
        first = self.record(
            status='model_error', error_type='RuntimeError', error_message='permanent',
            raw_response=None, response=None, response_agent=None,
            utility_status='unknown', utility_success=None,
            attack_status='unknown', attack_success=None,
            target_invoked=None, payload_injected=None,
        )
        attempts = [first]
        for attempt_no in (2, 3, 4):
            attempts.append(self.record(
                attempt_no=attempt_no,
                status='model_error', error_type='RuntimeError', error_message='permanent',
                raw_response=None, response=None, response_agent=None,
                utility_status='unknown', utility_success=None,
                attack_status='unknown', attack_success=None,
                target_invoked=None, payload_injected=None,
            ))
        report = audit_matrix_records(
            self.plan(), attempts, [], self.tasks, self.catalog,
            require_injection=False)
        self.assertTrue(any(error.startswith('non_retryable_attempt_retried:')
                            for error in report['errors']))
        self.assertTrue(any(error.startswith('retry_limit_exceeded:')
                            for error in report['errors']))

    def test_storage_failure_and_missing_config_snapshot_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            writer = RunWriter(root)
            (root / '.write_pending.json').write_text('{}')
            storage = audit_matrix(writer, self.plan(), self.tasks, self.catalog)
            self.assertFalse(storage['ok'])
            self.assertTrue(storage['errors'][0].startswith('storage:'))

        record = self.record()
        with tempfile.TemporaryDirectory() as directory:
            report = audit_matrix_records(
                self.plan(), [record], [self.evidence(record)], self.tasks, self.catalog,
                config_directory=Path(directory))
            self.assertTrue(any(error.startswith('config_snapshot_missing_or_invalid:')
                                for error in report['errors']))

    def test_plan_rejects_duplicates_and_incompatible_domain(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate planned run'):
            self.plan([('math_0001', ATTACK_ID), ('math_0001', ATTACK_ID)])
        with self.assertRaisesRegex(ValueError, 'does not support math'):
            self.plan([('math_0001', 'hijacking_safety_check.instruction.v1')])

    def test_checked_in_manifest_plan_counts(self):
        expected = {
            'benign': 69,
            'core-attacks': 306,
            'pilot': 30,
            'confirmation': 60,
        }
        for name, count in expected.items():
            with self.subTest(matrix=name):
                plan = build_manifest_plan(
                    name,
                    experiment_id='planned-development',
                    tasks=self.tasks,
                    catalog=self.catalog,
                )
                self.assertEqual(len(plan.expected), count)


if __name__ == '__main__':
    unittest.main()
