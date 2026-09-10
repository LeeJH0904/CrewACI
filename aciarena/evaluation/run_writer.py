"""Append-only JSONL storage for a local POSIX filesystem.

Messages are persisted as they occur; a run row finalizes an attempt. A durable
pending marker makes interrupted/failed writes visible instead of repairing or
silently truncating evidence. All readers and writers cooperate on one flock.
"""

from contextlib import contextmanager
import fcntl
import json
import os
import re
from pathlib import Path

from .records import MessageRecord, RunRecord, timestamp, canonical_hash


class StorageError(RuntimeError):
    pass


class RecordConflictError(StorageError):
    pass


class RecoveryRequiredError(StorageError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class RunWriter:
    def __init__(self, output_dir):
        self.directory = Path(output_dir).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._pending = self.directory / '.write_pending.json'
        self._failed = False

    @contextmanager
    def _locked(self):
        # A distinct descriptor per operation also serializes separate threads
        # and separate writer objects, not just separate processes.
        with (self.directory / '.writer.lock').open('a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _healthy(self):
        if self._failed or self._pending.exists():
            raise RecoveryRequiredError('A write failed or was interrupted; preserve files and audit before recovery')

    def _read(self, filename, model):
        path = self.directory / filename
        if not path.exists():
            return []
        records = []
        with path.open('rb') as stream:
            for number, line in enumerate(stream, 1):
                try:
                    if not line.endswith(b'\n'):
                        raise ValueError('Unterminated JSONL line')
                    data = json.loads(line, object_pairs_hook=_unique_object)
                    records.append(model.model_validate(data))
                except (ValueError, TypeError) as exc:
                    raise RecoveryRequiredError(f'{filename}:{number}: invalid record; no automatic truncation') from exc
        return records

    @staticmethod
    def _check_final(record, messages):
        for message in messages:
            if message.attack_id != record.attack_id:
                raise RecordConflictError('Run and message attack IDs disagree')
            if not timestamp(record.started_at) <= timestamp(message.created_at) <= timestamp(record.finished_at):
                raise RecordConflictError('Message timestamp lies outside its attempt')
        if record.status == 'success':
            pipeline = [message for message in messages if message.phase != 'evaluation']
            if not pipeline or (pipeline[-1].phase, pipeline[-1].sender, pipeline[-1].content) != (
                    'final', record.response_agent, record.raw_response):
                raise RecordConflictError('Successful execution requires its final raw output message')

    def _state(self):
        runs, messages = {}, {}
        for record in self._read('runs.jsonl', RunRecord):
            key = (record.run_id, record.attempt_no)
            if key in runs:
                raise RecordConflictError('Duplicate (run_id, attempt_no) in runs.jsonl')
            previous = [r for (rid, _), r in runs.items() if rid == record.run_id]
            if record.attempt_no != len(previous) + 1 or any(r.is_complete for r in previous):
                raise RecordConflictError('Attempt gap, out-of-order attempt, or retry after completion')
            runs[key] = record
        for message in self._read('messages.jsonl', MessageRecord):
            key = (message.run_id, message.attempt_no)
            trace = messages.setdefault(key, [])
            if message.seq != len(trace) + 1:
                raise RecordConflictError('Message seq must start at 1 and be contiguous per attempt')
            if trace and message.attack_id != trace[0].attack_id:
                raise RecordConflictError('Attack ID changed within an attempt')
            trace.append(message)
        for key, record in runs.items():
            self._check_final(record, messages.get(key, []))
        for key in messages.keys() - runs.keys():
            self._check_open_attempt(key, runs)
        return runs, messages

    @staticmethod
    def _check_open_attempt(key, runs):
        if key in runs:
            raise RecordConflictError('Attempt already finalized; rows cannot be overwritten or extended')
        run_id, attempt_no = key
        previous = [record for (rid, _), record in runs.items() if rid == run_id]
        if any(record.is_complete for record in previous):
            raise RecordConflictError('Run already complete, including valid false evaluations')
        if attempt_no != len(previous) + 1:
            raise RecordConflictError('Finalize preceding attempts before starting the next one')

    def _sync_directory(self):
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _append_line(self, path, data):
        with path.open('ab') as stream:
            written = stream.write(data)
            if written != len(data):
                raise OSError('Short JSONL write')
            stream.flush()
            os.fsync(stream.fileno())

    def _commit(self, filename, record):
        # Serialization completes before touching any storage evidence.
        data = (record.model_dump_json() + '\n').encode('utf-8')
        self._persist(filename, data, {'run_id': record.run_id, 'attempt_no': record.attempt_no,
                                       'seq': getattr(record, 'seq', None)})

    def _persist(self, filename, data, identity):
        marker = json.dumps({'file': filename, **identity}).encode('utf-8')
        try:
            with self._pending.open('xb') as stream:
                stream.write(marker)
                stream.flush()
                os.fsync(stream.fileno())
            self._sync_directory()
            self._append_line(self.directory / filename, data)
            self._sync_directory()
            self._pending.unlink()
            self._sync_directory()
        except OSError as exc:
            self._failed = True
            # If final directory fsync failed after unlink, restore an explicit
            # recovery marker when storage permits. Never report success.
            if not self._pending.exists():
                try:
                    with self._pending.open('xb') as stream:
                        stream.write(marker)
                        stream.flush()
                        os.fsync(stream.fileno())
                    self._sync_directory()
                except OSError:
                    pass  # The caller must stop on the original storage error.
            raise RecoveryRequiredError('JSONL persistence failed; automatic retry/repair is disabled') from exc

    def store_config(self, config_hash, config):
        """Keep the credential-free inputs behind a RunRecord's config hash."""
        if canonical_hash(config) != config_hash:
            raise ValueError('Config hash mismatch')
        with self._locked():
            self._healthy()
            directory = self.directory / 'configs'
            directory.mkdir(exist_ok=True)
            path = directory / f'{config_hash}.json'
            if path.exists():
                try:
                    actual = json.loads(path.read_bytes(), object_pairs_hook=_unique_object)
                except ValueError as exc:
                    raise RecoveryRequiredError('Invalid stored config snapshot') from exc
                if actual != config:
                    raise RecoveryRequiredError('Stored config snapshot differs')
                return
            data = (json.dumps(config, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
            self._persist(f'configs/{config_hash}.json', data, {'config_hash': config_hash})

    def append_message(self, message: MessageRecord):
        message = MessageRecord.model_validate(message.model_dump())
        with self._locked():
            self._healthy()
            runs, messages = self._state()
            key = (message.run_id, message.attempt_no)
            self._check_open_attempt(key, runs)
            trace = messages.get(key, [])
            if message.seq != len(trace) + 1:
                raise RecordConflictError('Message seq must be the next contiguous value')
            if trace and message.attack_id != trace[0].attack_id:
                raise RecordConflictError('Attack ID changed within an attempt')
            self._commit('messages.jsonl', message)

    def append_run(self, record: RunRecord):
        record = RunRecord.model_validate(record.model_dump())
        with self._locked():
            self._healthy()
            runs, messages = self._state()
            key = (record.run_id, record.attempt_no)
            self._check_open_attempt(key, runs)
            self._check_final(record, messages.get(key, []))
            self._commit('runs.jsonl', record)

    def completed_run_ids(self):
        with self._locked():
            self._healthy()
            runs, _ = self._state()
            return frozenset(record.run_id for record in runs.values() if record.is_complete)

    def read_runs(self):
        with self._locked():
            self._healthy()
            runs, _ = self._state()
            return tuple(runs.values())

    def read_messages(self):
        with self._locked():
            self._healthy()
            _, messages = self._state()
            return tuple(message for trace in messages.values() for message in trace)

    @contextmanager
    def claim_run(self, run_id):
        """Prevent duplicate model execution, including across suite processes."""
        if not re.fullmatch(r'run_[0-9a-f]{64}', run_id):
            raise ValueError('Invalid run ID')
        directory = self.directory / '.run_locks'
        directory.mkdir(exist_ok=True)
        with (directory / f'{run_id}.lock').open('a+b') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RecordConflictError('Run is already executing') from exc
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def next_attempt_no(self, run_id):
        """Advisory number only; retry eligibility and scheduling are external."""
        with self._locked():
            self._healthy()
            runs, messages = self._state()
            if any(r.run_id == run_id and r.is_complete for r in runs.values()):
                raise RecordConflictError('Run already complete')
            if any(key[0] == run_id for key in messages.keys() - runs.keys()):
                raise RecoveryRequiredError('Unfinalized partial trace exists; preserve and reconcile it first')
            return 1 + sum(key[0] == run_id for key in runs)

    def audit(self):
        """Storage-only audit after workers stop; does not certify the matrix."""
        errors = []
        with self._locked():
            if self._failed or self._pending.exists():
                errors.append('Pending/failed write requires explicit recovery')
            try:
                runs, messages = self._state()
            except (StorageError, OSError) as exc:
                errors.append(str(exc))
                return {'ok': False, 'errors': errors}
            orphans = sorted(messages.keys() - runs.keys())
            if orphans:
                errors.append('Unfinalized attempts have partial traces')
            return {'ok': not errors, 'errors': errors, 'run_rows': len(runs),
                    'message_rows': sum(map(len, messages.values())),
                    'unfinalized_attempts': orphans,
                    'completed_runs': len({r.run_id for r in runs.values() if r.is_complete})}
