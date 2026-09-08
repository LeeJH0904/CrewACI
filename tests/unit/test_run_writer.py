from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aciarena.evaluation.records import MessageRecord, RunRecord
from aciarena.evaluation.run_writer import RunWriter, RecordConflictError, RecoveryRequiredError
from test_records import benign_row


def run_record(**changes):
    return RunRecord(**benign_row(**changes))


def message(record, **changes):
    values = dict(run_id=record.run_id, attempt_no=record.attempt_no, seq=1,
                  sender='finalizer', receiver='user', phase='final', content=record.raw_response or '',
                  original_content=None, is_attacked=False, attack_id=record.attack_id,
                  created_at='2026-09-08T00:00:00Z')
    values.update(changes)
    return MessageRecord(**values)


def failure(**changes):
    values = dict(status='model_error', error_type='ProviderError', error_message='mock failure',
                  utility_status='unknown', utility_success=None, raw_response=None,
                  response=None, response_agent=None)
    values.update(changes)
    return run_record(**values)


def process_writes(directory, start):
    writer = RunWriter(directory)
    for index in range(start, start + 5):
        writer.append_run(failure(task_id=f'process_{index}'))


class RunWriterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.writer = RunWriter(self.path)

    def save(self, record):
        self.writer.append_message(message(record))
        self.writer.append_run(record)

    def test_false_result_is_complete_after_reopening(self):
        record = run_record()
        self.save(record)
        reopened = RunWriter(self.path)
        self.assertEqual(reopened.completed_run_ids(), {record.run_id})
        self.assertTrue(reopened.audit()['ok'])
        self.assertEqual(reopened.audit()['message_rows'], 1)
        with self.assertRaises(RecordConflictError):
            reopened.next_attempt_no(record.run_id)

    def test_judge_evaluation_after_final_preserves_output_evidence(self):
        record = run_record()
        self.writer.append_message(message(record))
        self.writer.append_message(message(record, seq=2, sender='attack_judge',
                                           receiver='executor', phase='evaluation', content='judge output'))
        self.writer.append_run(record)
        self.assertTrue(self.writer.audit()['ok'])

    def test_failure_and_retry_keep_both_rows(self):
        first = failure()
        self.assertEqual(self.writer.next_attempt_no(first.run_id), 1)
        self.writer.append_run(first)
        self.assertEqual(self.writer.completed_run_ids(), set())
        self.assertEqual(self.writer.next_attempt_no(first.run_id), 2)
        second = run_record(attempt_no=2)
        self.save(second)
        rows = [json.loads(line) for line in (self.path / 'runs.jsonl').read_text().splitlines()]
        self.assertEqual([r['attempt_no'] for r in rows], [1, 2])
        self.assertEqual([r['status'] for r in rows], ['model_error', 'success'])
        self.assertEqual(self.writer.completed_run_ids(), {first.run_id})

    def test_partial_trace_survives_model_failure(self):
        record = failure()
        trace = message(record, sender='user', receiver='solver', phase='task', content='task before failure')
        self.writer.append_message(trace)
        self.assertFalse(self.writer.audit()['ok'])
        with self.assertRaises(RecoveryRequiredError):
            RunWriter(self.path).next_attempt_no(record.run_id)
        RunWriter(self.path).append_run(record)
        self.assertTrue(self.writer.audit()['ok'])
        self.assertIn('task before failure', (self.path / 'messages.jsonl').read_text())

    def test_success_requires_final_raw_trace(self):
        record = run_record(raw_response='raw', response='normalized')
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(record)
        self.writer.append_message(message(record, content='normalized'))
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(record)
        self.writer.append_message(message(record, seq=2))
        self.writer.append_run(record)
        self.assertTrue(self.writer.audit()['ok'])

    def test_duplicate_or_extended_finalized_attempt_is_rejected(self):
        record = run_record()
        self.save(record)
        original = (self.path / 'runs.jsonl').read_bytes()
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(record)
        with self.assertRaises(RecordConflictError):
            self.writer.append_message(message(record, seq=2))
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(run_record(attempt_no=2))
        self.assertEqual((self.path / 'runs.jsonl').read_bytes(), original)

    def test_seq_gaps_duplicates_and_attempt_gaps_are_rejected(self):
        record = failure()
        with self.assertRaises(RecordConflictError):
            self.writer.append_message(message(record, seq=2))
        self.writer.append_message(message(record))
        for seq in (1, 3):
            with self.subTest(seq=seq), self.assertRaises(RecordConflictError):
                self.writer.append_message(message(record, seq=seq))
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(failure(attempt_no=2))
        self.writer.append_run(record)
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(failure(attempt_no=3))

    def test_attack_and_time_mismatch_do_not_finalize(self):
        record = failure()
        self.writer.append_message(message(record, attack_id='disruption_ddos.message.v1'))
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(record)
        other = failure(task_id='other')
        self.writer.append_message(message(other, created_at='2026-09-09T00:00:00Z'))
        with self.assertRaises(RecordConflictError):
            self.writer.append_run(other)
        self.assertFalse((self.path / 'runs.jsonl').exists())

    def test_hundred_concurrent_attempts_using_separate_writers(self):
        def write(index):
            writer = RunWriter(self.path)
            record = run_record(task_id=f'parallel_{index}')
            writer.append_message(message(record, content='input', phase='task', sender='user', receiver='solver'))
            writer.append_message(message(record, seq=2))
            writer.append_run(record)
            return record.run_id

        with ThreadPoolExecutor(max_workers=12) as pool:
            ids = list(pool.map(write, range(100)))
        report = self.writer.audit()
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['run_rows'], 100)
        self.assertEqual(report['message_rows'], 200)
        self.assertEqual(self.writer.completed_run_ids(), set(ids))

    def test_processes_share_the_same_file_lock(self):
        context = multiprocessing.get_context('fork')
        processes = [context.Process(target=process_writes, args=(str(self.path), index * 5)) for index in range(4)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
        self.assertEqual(self.writer.audit()['run_rows'], 20)
        self.assertTrue(self.writer.audit()['ok'])

    def test_racing_duplicate_run_has_one_winner(self):
        record = failure()

        def write(_):
            try:
                RunWriter(self.path).append_run(record)
                return True
            except RecordConflictError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(write, range(20)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.writer.audit()['run_rows'], 1)

    def test_failed_append_blocks_all_writer_instances(self):
        with patch.object(self.writer, '_append_line', side_effect=OSError('disk full')):
            with self.assertRaises(RecoveryRequiredError):
                self.writer.append_run(failure())
        self.assertTrue((self.path / '.write_pending.json').exists())
        self.assertFalse(self.writer.audit()['ok'])
        reopened = RunWriter(self.path)
        with self.assertRaises(RecoveryRequiredError):
            reopened.append_run(failure())
        with self.assertRaises(RecoveryRequiredError):
            reopened.completed_run_ids()

    def test_partial_json_is_preserved_after_write_failure(self):
        def broken_write(path, data):
            path.write_bytes(data[:17])
            raise OSError('interrupted write')

        with patch.object(self.writer, '_append_line', side_effect=broken_write):
            with self.assertRaises(RecoveryRequiredError):
                self.writer.append_run(failure())
        damaged = (self.path / 'runs.jsonl').read_bytes()
        self.assertEqual(len(damaged), 17)
        self.assertFalse(RunWriter(self.path).audit()['ok'])
        self.assertEqual((self.path / 'runs.jsonl').read_bytes(), damaged)

    def test_fsync_failure_never_reports_completion(self):
        record = run_record()
        self.writer.append_message(message(record))
        # Pending-file fsync, directory fsync, then run-file fsync fails.
        with patch('aciarena.evaluation.run_writer.os.fsync', side_effect=[None, None, OSError('fsync failed')]):
            with self.assertRaises(RecoveryRequiredError):
                self.writer.append_run(record)
        with self.assertRaises(RecoveryRequiredError):
            RunWriter(self.path).completed_run_ids()
        self.assertFalse(self.writer.audit()['ok'])

    def test_malformed_duplicate_or_unterminated_rows_are_not_skipped(self):
        path = self.path / 'runs.jsonl'
        record = failure()
        line = record.model_dump_json() + '\n'
        for data in ('{broken}\n', line + line, line.rstrip('\n'), '\n'):
            with self.subTest(data=data[:20]):
                path.write_text(data)
                self.assertFalse(self.writer.audit()['ok'])
                with self.assertRaises((RecoveryRequiredError, RecordConflictError)):
                    self.writer.completed_run_ids()
                self.assertEqual(path.read_text(), data)

    def test_final_directory_sync_failure_restores_recovery_marker(self):
        original_fsync = os.fsync
        calls = 0

        def fail_fifth(descriptor):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise OSError('directory sync failed after marker removal')
            return original_fsync(descriptor)

        with patch('aciarena.evaluation.run_writer.os.fsync', side_effect=fail_fifth):
            with self.assertRaises(RecoveryRequiredError):
                self.writer.append_run(failure())
        self.assertTrue((self.path / '.write_pending.json').exists())
        with self.assertRaises(RecoveryRequiredError):
            RunWriter(self.path).next_attempt_no(failure().run_id)

    def test_audit_detects_persisted_message_sequence_corruption(self):
        self.save(run_record())
        path = self.path / 'messages.jsonl'
        data = json.loads(path.read_text())
        data['seq'] = 2
        path.write_text(json.dumps(data) + '\n')
        self.assertFalse(self.writer.audit()['ok'])
        with self.assertRaises(RecordConflictError):
            self.writer.completed_run_ids()


if __name__ == '__main__':
    unittest.main()
