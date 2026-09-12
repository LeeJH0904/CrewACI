"""G2 experiment matrix, retry, activation, and evidence audit."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .records import RETRYABLE_ERROR_TYPES, MessageRecord, RunRecord, canonical_hash


@dataclass(frozen=True, order=True)
class MatrixKey:
    experiment_id: str
    task_id: str
    mas_id: str
    implementation: str
    attack_id: str
    repetition: int
    phase: str
    config_hash: str


@dataclass(frozen=True)
class MatrixPlan:
    expected: frozenset[MatrixKey]

    def __post_init__(self):
        if not self.expected:
            raise ValueError('A matrix plan must contain at least one run')


def record_key(record: RunRecord):
    return MatrixKey(
        experiment_id=record.experiment_id,
        task_id=record.task_id,
        mas_id=record.mas_id,
        implementation=record.implementation,
        attack_id=record.attack_id,
        repetition=record.repetition,
        phase=record.phase,
        config_hash=record.config_hash,
    )


def build_matrix_plan(*, experiment_id, selections, tasks, catalog,
                      mas_id='crewai_seq_nodeleg', implementation='reconstructed',
                      repetition=1, phase='pilot', config_hash):
    expected = set()
    for task_id, attack_id in selections:
        try:
            entry = tasks[task_id]
        except KeyError as exc:
            raise ValueError(f'Unknown planned task: {task_id}') from exc
        catalog.get(attack_id, task_domain=entry['task_domain'])
        key = MatrixKey(experiment_id, task_id, mas_id, implementation,
                        attack_id, repetition, phase, config_hash)
        if key in expected:
            raise ValueError(f'Duplicate planned run: {task_id}/{attack_id}')
        expected.add(key)
    return MatrixPlan(frozenset(expected))


def build_manifest_plan(name, *, experiment_id, tasks, catalog, config_hash,
                        manifest_directory=None):
    """Build one predeclared development matrix from checked-in manifests."""
    directory = Path(manifest_directory) if manifest_directory is not None else (
        Path(__file__).resolve().parents[2] / 'manifests')
    if name == 'benign':
        selections = [(task_id, 'none') for task_id in tasks]
        repetitions, phase = (1,), 'core'
    elif name == 'core-attacks':
        selections = [
            (task_id, spec.attack_id)
            for task_id, entry in tasks.items()
            for spec in catalog.specs.values()
            if entry['task_domain'] in spec.domains
        ]
        repetitions, phase = (1,), 'core'
    elif name in {'pilot', 'confirmation'}:
        manifest = json.loads((directory / 'confirmation_tasks.json').read_text())
        task_manifest = json.loads((directory / 'tasks.json').read_text())
        attack_manifest = json.loads((directory / 'attacks.json').read_text())
        if (manifest.get('task_manifest_hash') != canonical_hash(task_manifest)
                or manifest.get('attack_manifest_hash') != canonical_hash(attack_manifest)):
            raise ValueError('Confirmation manifest hash references do not match')
        by_task = {
            task_id: manifest['attack_ids_by_domain'][tasks[task_id]['task_domain']]
            for task_id in manifest['task_ids']
        }
        selections = [(task_id, attack_id) for task_id, attack_ids in by_task.items()
                      for attack_id in attack_ids]
        repetitions = ((1,) if name == 'pilot'
                       else tuple(manifest['additional_repetitions']))
        phase = name
    else:
        raise ValueError(f'Unknown manifest matrix: {name}')
    expected = set()
    for repetition in repetitions:
        plan = build_matrix_plan(
            experiment_id=experiment_id,
            selections=selections,
            tasks=tasks,
            catalog=catalog,
            repetition=repetition,
            phase=phase,
            config_hash=config_hash,
        )
        expected.update(plan.expected)
    return MatrixPlan(frozenset(expected))


def _format_keys(keys):
    return [f'{key.task_id}/{key.attack_id}/r{key.repetition}/{key.phase}/cfg-{key.config_hash[:12]}'
            for key in sorted(keys)]


def _config_snapshot_errors(config_hash, config_directory, catalog):
    path = config_directory / f'{config_hash}.json'
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        return [f'config_snapshot_missing_or_invalid:{config_hash}']
    if canonical_hash(config) != config_hash:
        return [f'config_snapshot_hash_mismatch:{config_hash}']

    errors = []
    root = Path(__file__).resolve().parents[2]
    # A versioned experiment keeps its task and attack manifests together.
    # Do not compare a G5 snapshot against the default G0 development manifest.
    current_tasks = json.loads((catalog.manifest_path.parent / 'tasks.json').read_text())
    if config.get('task_manifest_hash') != canonical_hash(current_tasks):
        errors.append(f'config_task_manifest_drift:{config_hash}')
    if config.get('attack_manifest_hash') != catalog.manifest_hash:
        errors.append(f'config_attack_manifest_drift:{config_hash}')
    if config.get('dependency_lock_hash') != hashlib.sha256(
            (root / 'requirements.lock').read_bytes()).hexdigest():
        errors.append(f'config_dependency_lock_drift:{config_hash}')
    sources = config.get('sources')
    if not isinstance(sources, dict) or 'aciarena/evaluation/audit.py' not in sources:
        errors.append(f'config_source_missing:audit.py:{config_hash}')
    if isinstance(sources, dict):
        for source, expected_hash in sources.items():
            candidate = (root / source).resolve()
            try:
                candidate.relative_to(root)
                actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except (OSError, ValueError):
                errors.append(f'config_source_missing_or_unsafe:{source}:{config_hash}')
                continue
            if actual_hash != expected_hash:
                errors.append(f'config_source_drift:{source}:{config_hash}')
    return errors


def _activation_errors(record: RunRecord, messages: list[MessageRecord], spec):
    if record.attack_id == 'none' or record.status != 'success':
        return []
    errors = []
    label = f'{record.task_id}/{record.attack_id}'
    if record.target_invoked is not True:
        errors.append(f'target_not_invoked:{label}')
    if record.payload_injected is not True:
        errors.append(f'payload_not_injected:{label}')
    direct = [message for message in messages if message.is_attacked]
    expected = {
        'instruction': {('solver', 'llm', 'llm_input')},
        'agent': {('solver', 'solver', 'profile'), ('solver', 'llm', 'llm_input')},
        'message': {('solver', 'reviewer', 'context')},
    }[record.attack_surface]
    observed = {(message.sender, message.receiver, message.phase) for message in direct}
    if not expected <= observed:
        errors.append(f'attack_surface_evidence_missing:{label}:{record.attack_surface}')

    def contains_payload(message):
        if message.phase != 'llm_input':
            return spec.payload in message.content
        try:
            llm_messages = json.loads(message.content)
        except (TypeError, ValueError):
            return False
        return any(spec.payload in item.get('content', '') for item in llm_messages
                   if isinstance(item, dict))

    if direct and not all(contains_payload(message) for message in direct):
        errors.append(f'attack_payload_evidence_mismatch:{label}')
    if any(message.attack_id != record.attack_id for message in direct):
        errors.append(f'attack_evidence_id_mismatch:{label}')
    if any(message.sender not in {'solver'} for message in direct):
        errors.append(f'non_target_direct_attack_evidence:{label}')
    return errors


def audit_matrix_records(plan, records, messages, tasks, catalog, *,
                         config_directory=None, allow_additional=False,
                         require_injection=True):
    """Audit validated objects without altering source evidence."""
    errors = []
    expected = plan.expected
    expected_experiments = {key.experiment_id for key in expected}
    expected_scopes = {
        (key.experiment_id, key.mas_id, key.implementation, key.repetition, key.phase)
        for key in expected
    }
    scoped = [record for record in records if (
        record.experiment_id, record.mas_id, record.implementation,
        record.repetition, record.phase) in expected_scopes]

    by_attempt = defaultdict(list)
    by_key = defaultdict(list)
    by_run = defaultdict(list)
    for record in scoped:
        by_attempt[(record.run_id, record.attempt_no)].append(record)
        by_key[record_key(record)].append(record)
        by_run[record.run_id].append(record)

    duplicate_attempts = [key for key, group in by_attempt.items() if len(group) > 1]
    if duplicate_attempts:
        errors.append('duplicate_attempts:' + ','.join(
            f'{run_id}/a{attempt}' for run_id, attempt in sorted(duplicate_attempts)))

    actual = set(by_key)
    missing = expected - actual
    additional = actual - expected
    if missing:
        errors.append('missing_planned_runs:' + ','.join(_format_keys(missing)))
    if additional and not allow_additional:
        errors.append('unexpected_runs:' + ','.join(_format_keys(additional)))

    for key, group in by_key.items():
        run_ids = {record.run_id for record in group}
        if len(run_ids) > 1:
            errors.append(f'config_or_identity_drift:{key.task_id}/{key.attack_id}')

    for run_id, attempts in by_run.items():
        attempts.sort(key=lambda record: record.attempt_no)
        numbers = [record.attempt_no for record in attempts]
        if numbers != list(range(1, len(numbers) + 1)):
            errors.append(f'attempt_sequence:{run_id}')
        if len(attempts) > 3:
            errors.append(f'retry_limit_exceeded:{run_id}')
        for previous in attempts[:-1]:
            if previous.is_complete:
                errors.append(f'retry_after_complete:{run_id}')
            if previous.error_type not in RETRYABLE_ERROR_TYPES:
                errors.append(f'non_retryable_attempt_retried:{run_id}/a{previous.attempt_no}')

    adopted = {}
    for key in expected:
        candidates = sorted(by_key.get(key, ()), key=lambda record: record.attempt_no)
        if not candidates:
            continue
        complete = next((record for record in candidates if record.is_complete), None)
        adopted[key] = complete or candidates[-1]

    if config_directory is not None:
        for config_hash in sorted({record.config_hash for record in adopted.values()}):
            errors.extend(_config_snapshot_errors(config_hash, config_directory, catalog))

    message_groups = defaultdict(list)
    for message in messages:
        message_groups[(message.run_id, message.attempt_no)].append(message)
    for group in message_groups.values():
        group.sort(key=lambda message: message.seq)
        if [message.seq for message in group] != list(range(1, len(group) + 1)):
            first = group[0]
            errors.append(f'message_sequence:{first.run_id}/a{first.attempt_no}')

    for key, record in adopted.items():
        entry = tasks.get(record.task_id)
        if entry is None or entry['task_domain'] != record.task_domain:
            errors.append(f'task_manifest_mismatch:{record.task_id}')
            continue
        if canonical_hash(record.ground_truth) != entry['ground_truth_hash']:
            errors.append(f'ground_truth_manifest_mismatch:{record.task_id}')
        try:
            spec = catalog.get(record.attack_id, task_domain=record.task_domain)
        except Exception:
            errors.append(f'attack_manifest_mismatch:{record.task_id}/{record.attack_id}')
            continue
        if spec is None:
            if any(value is not None for value in (
                    record.attack_category, record.attack_goal, record.attack_surface,
                    record.malicious_agent, record.payload_hash)):
                errors.append(f'benign_metadata_mismatch:{record.task_id}')
        else:
            actual_metadata = (
                record.attack_category, record.attack_goal, record.attack_surface,
                record.malicious_agent, record.payload_hash,
            )
            expected_metadata = (
                spec.attack_category, spec.goal, spec.surface, spec.target, spec.payload_hash,
            )
            if actual_metadata != expected_metadata:
                errors.append(f'attack_metadata_mismatch:{record.task_id}/{record.attack_id}')
            if not record.verifier_version.endswith('/' + spec.verifier_source_hash):
                errors.append(f'attack_verifier_version_mismatch:{record.task_id}/{record.attack_id}')
            if spec.attack_category == 'hijacking_answer_mapping' and record.status == 'success':
                applicable = (record.task_id not in spec.not_applicable_task_ids
                              if spec.not_applicable_task_ids else
                              any(character.isascii() and character.isdigit()
                                  for character in str(record.ground_truth)))
                if applicable != (record.attack_status != 'not_applicable'):
                    errors.append(f'attack_applicability_mismatch:{record.task_id}/{record.attack_id}')
            if spec.attack_category == 'hijacking_math_invert' and record.status == 'success':
                applicable = record.task_id not in spec.not_applicable_task_ids
                if applicable != (record.attack_status != 'not_applicable'):
                    errors.append(f'attack_applicability_mismatch:{record.task_id}/{record.attack_id}')
            if require_injection:
                errors.extend(_activation_errors(
                    record, message_groups.get((record.run_id, record.attempt_no), ()), spec))
    target_not_invoked = sum(
        record.attack_id != 'none' and record.target_invoked is False
        for record in adopted.values())
    payload_not_injected = sum(
        record.attack_id != 'none' and record.payload_injected is False
        for record in adopted.values())
    return {
        'ok': not errors,
        'errors': errors,
        'planned_runs': len(expected),
        'observed_logical_runs': len(actual & expected),
        'adopted_runs': len(adopted),
        'completed_runs': sum(record.is_complete for record in adopted.values()),
        'missing_runs': len(missing),
        'unexpected_runs': len(additional),
        'target_not_invoked': target_not_invoked,
        'payload_not_injected': payload_not_injected,
        'execution_errors': sum(record.status != 'success' for record in adopted.values()),
        'utility_unknown': sum(record.utility_status == 'unknown' for record in adopted.values()),
        'utility_errors': sum(record.utility_status == 'error' for record in adopted.values()),
        'attack_unknown': sum(record.attack_status == 'unknown' for record in adopted.values()),
        'attack_errors': sum(record.attack_status == 'error' for record in adopted.values()),
        'attack_valid': sum(record.attack_status == 'valid' for record in adopted.values()),
        'attack_not_applicable': sum(
            record.attack_id != 'none' and record.attack_status == 'not_applicable'
            for record in adopted.values()),
        'experiment_ids': sorted(expected_experiments),
    }


def audit_matrix(writer, plan, tasks, catalog, *, allow_additional=False,
                 require_injection=True):
    storage = writer.audit()
    if not storage['ok']:
        return {
            'ok': False,
            'errors': ['storage:' + error for error in storage['errors']],
            'planned_runs': len(plan.expected),
            'storage': storage,
        }
    report = audit_matrix_records(
        plan,
        writer.read_runs(),
        writer.read_messages(),
        tasks,
        catalog,
        config_directory=writer.directory / 'configs',
        allow_additional=allow_additional,
        require_injection=require_injection,
    )
    report['storage'] = storage
    return report
