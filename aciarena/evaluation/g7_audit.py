"""G7-specific exact-plan and evidence audit for shared legacy records."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path

from .audit import MatrixKey, MatrixPlan, record_key
from .g7_manifest import G7Manifest
from .records import RETRYABLE_ERROR_TYPES, canonical_hash


ROOT = Path(__file__).resolve().parents[2]


def build_g7_plan(*, experiment_id, mas_id, task_ids, attack_ids,
                  repetition, phase, config_hash):
    expected = {
        MatrixKey(
            experiment_id=experiment_id,
            task_id=task_id,
            mas_id=mas_id,
            implementation='legacy',
            attack_id=attack_id,
            repetition=repetition,
            phase=phase,
            config_hash=config_hash,
        )
        for task_id in task_ids for attack_id in attack_ids
    }
    if len(expected) != len(task_ids) * len(attack_ids):
        raise ValueError('G7 plan contains duplicate task/attack selections')
    return MatrixPlan(frozenset(expected))


def _snapshot_errors(directory, config_hash):
    path = Path(directory) / 'configs' / f'{config_hash}.json'
    try:
        snapshot = json.loads(path.read_text())
    except (OSError, ValueError):
        return [f'config_snapshot_missing_or_invalid:{config_hash}']
    errors = []
    if canonical_hash(snapshot) != config_hash:
        errors.append(f'config_snapshot_hash_mismatch:{config_hash}')
    for group in ('manifests', 'sources'):
        entries = snapshot.get(group)
        if not isinstance(entries, dict) or not entries:
            errors.append(f'config_{group}_missing:{config_hash}')
            continue
        for source, expected in entries.items():
            path = (ROOT / source).resolve()
            try:
                path.relative_to(ROOT)
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError):
                errors.append(f'config_{group}_missing_or_unsafe:{source}:{config_hash}')
                continue
            if actual != expected:
                errors.append(f'config_{group}_drift:{source}:{config_hash}')
    dependency = snapshot.get('dependency_lock_hash')
    if dependency != hashlib.sha256((ROOT / 'requirements.lock').read_bytes()).hexdigest():
        errors.append(f'config_dependency_lock_drift:{config_hash}')
    return errors


def audit_g7(writer, plan, manifest=None, *, allow_additional=True,
             require_injection=True):
    manifest = manifest if manifest is not None else G7Manifest()
    storage = writer.audit()
    errors = list(storage['errors'])
    records = list(writer.read_runs())
    messages = list(writer.read_messages())
    expected = plan.expected
    scopes = {
        (key.experiment_id, key.mas_id, key.implementation, key.repetition, key.phase)
        for key in expected
    }
    scoped = [row for row in records if (
        row.experiment_id, row.mas_id, row.implementation,
        row.repetition, row.phase) in scopes]
    by_key = defaultdict(list)
    by_attempt = defaultdict(list)
    by_run = defaultdict(list)
    for row in scoped:
        by_key[record_key(row)].append(row)
        by_attempt[(row.run_id, row.attempt_no)].append(row)
        by_run[row.run_id].append(row)
    if any(len(rows) > 1 for rows in by_attempt.values()):
        errors.append('duplicate_attempts')
    actual = set(by_key)
    missing = expected - actual
    additional = actual - expected
    if missing:
        errors.append('missing_planned_runs')
    if additional and not allow_additional:
        errors.append('unexpected_runs')
    expected_without_config = {
        (
            key.experiment_id, key.task_id, key.mas_id, key.implementation,
            key.attack_id, key.repetition, key.phase,
        ): key.config_hash
        for key in expected
    }
    for key in additional:
        base = (
            key.experiment_id, key.task_id, key.mas_id, key.implementation,
            key.attack_id, key.repetition, key.phase,
        )
        if base in expected_without_config:
            errors.append(f'config_or_identity_drift:{key.task_id}/{key.attack_id}')
    for key, attempts in by_key.items():
        if len({row.run_id for row in attempts}) != 1:
            errors.append(f'config_or_identity_drift:{key.task_id}/{key.attack_id}')
    for run_id, attempts in by_run.items():
        attempts.sort(key=lambda row: row.attempt_no)
        if [row.attempt_no for row in attempts] != list(range(1, len(attempts) + 1)):
            errors.append(f'attempt_sequence:{run_id}')
        if len(attempts) > 3:
            errors.append(f'retry_limit_exceeded:{run_id}')
        for previous in attempts[:-1]:
            if previous.is_complete:
                errors.append(f'retry_after_complete:{run_id}')
            if previous.error_type not in RETRYABLE_ERROR_TYPES:
                errors.append(f'non_retryable_attempt_retried:{run_id}')
    adopted = {}
    for key in expected:
        attempts = sorted(by_key.get(key, ()), key=lambda row: row.attempt_no)
        if attempts:
            adopted[key] = next((row for row in attempts if row.is_complete), attempts[-1])
    for config_hash in sorted({row.config_hash for row in adopted.values()}):
        errors.extend(_snapshot_errors(writer.directory, config_hash))

    message_groups = defaultdict(list)
    for message in messages:
        message_groups[(message.run_id, message.attempt_no)].append(message)
    for key, row in adopted.items():
        task = manifest.tasks.get(row.task_id)
        if (task is None or task['task_domain'] != row.task_domain
                or canonical_hash(row.ground_truth) != task['ground_truth_hash']):
            errors.append(f'task_manifest_mismatch:{row.task_id}')
        if (row.status == 'success'
                and row.response_agent != manifest.systems[row.mas_id]['response_agent']):
            errors.append(f'response_source_mismatch:{row.task_id}/{row.attack_id}')
        if row.attack_id == 'none':
            continue
        spec = manifest.attacks.get(row.attack_id)
        if spec is None:
            errors.append(f'attack_manifest_mismatch:{row.task_id}/{row.attack_id}')
            continue
        expected_metadata = (
            spec['attack_category'], spec['goal'], spec['surface'], spec['payload_hash'])
        actual_metadata = (
            row.attack_category, row.attack_goal, row.attack_surface, row.payload_hash)
        if actual_metadata != expected_metadata:
            errors.append(f'attack_metadata_mismatch:{row.task_id}/{row.attack_id}')
        if not row.verifier_version.endswith('/' + spec['verifier_source_hash']):
            errors.append(f'attack_verifier_version_mismatch:{row.task_id}/{row.attack_id}')
        if row.malicious_agent not in manifest.systems[row.mas_id]['agents']:
            errors.append(f'target_agent_mismatch:{row.task_id}/{row.attack_id}')
        if row.status != 'success':
            continue
        label = f'{row.task_id}/{row.attack_id}'
        attempt_messages = message_groups[(row.run_id, row.attempt_no)]
        if spec['goal'] == 'disruption':
            judge_edges = {
                (message.sender, message.receiver)
                for message in attempt_messages
                if message.phase == 'evaluation'
            }
            if not {
                    ('attack_verifier', 'judge'),
                    ('judge', 'attack_verifier'),
            } <= judge_edges:
                errors.append(f'judge_io_evidence_missing:{label}')
        if require_injection and row.target_invoked is not True:
            errors.append(f'target_not_invoked:{label}')
        if require_injection and row.payload_injected is not True:
            errors.append(f'payload_not_injected:{label}')
        if row.payload_injected is not True:
            continue
        direct = [message for message in attempt_messages
                  if message.is_attacked]
        phases = {'instruction': 'llm_input', 'agent': 'profile', 'message': 'turn'}
        if not any(
                message.sender == row.malicious_agent
                and message.phase == phases[row.attack_surface]
                and spec['payload'] in message.content
                for message in direct):
            errors.append(f'attack_surface_evidence_missing:{label}:{row.attack_surface}')
    return {
        'ok': not errors,
        'errors': errors,
        'planned_runs': len(expected),
        'observed_logical_runs': len(actual & expected),
        'adopted_runs': len(adopted),
        'completed_runs': sum(row.is_complete for row in adopted.values()),
        'execution_errors': sum(row.status != 'success' for row in adopted.values()),
        'utility_errors': sum(row.utility_status == 'error' for row in adopted.values()),
        'attack_errors': sum(row.attack_status == 'error' for row in adopted.values()),
        'target_not_invoked': sum(
            row.attack_id != 'none' and row.target_invoked is False
            for row in adopted.values()),
        'payload_not_injected': sum(
            row.attack_id != 'none' and row.payload_injected is False
            for row in adopted.values()),
        'missing_runs': len(missing),
        'unexpected_runs': len(additional),
        'storage': storage,
    }
