"""Single-source experiment configuration and dependency-lock validation."""

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[2]
SECRET_KEYS = {'api_key', 'api_token', 'access_token', 'authorization',
               'password', 'secret'}
BASE_TOP_LEVEL_KEYS = {
    'schema_version', 'contract_id', 'stage', 'default_experiment_id',
    'model_config', 'judge_config', 'active_mas', 'task_domains',
    'model_policy', 'final_benchmark_ready', 'paid_api_budget_usd',
    'max_turn', 'normalizer', 'retry_policy', 'judge_policy', 'verifiers',
    'dependency_lock', 'dependency_checks', 'planned_runs',
}
FINAL_EXTRA_KEYS = {'manifest_directory', 'manifest_hashes', 'cost_policy', 'seed_policy'}
UTILITY_VERIFIER_VERSION = (
    'isolated-math-v1/linux-x86_64-landlock-seccomp-v1/'
    'disruption-nonanswer-resolution-v1'
)


class ConfigurationError(ValueError):
    pass


def _mapping(path):
    with path.open() as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ConfigurationError(f'Configuration must be a mapping: {path}')
    return value


def _repo_path(base, reference):
    path = (base / reference).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ConfigurationError('Configuration references must stay inside the repository') from exc
    if not path.is_file():
        raise ConfigurationError(f'Referenced configuration does not exist: {reference}')
    return path


def _validate_llm(config, *, judge=False, final=False):
    required = {'provider', 'model_name', 'temperature', 'max_tokens', 'seed', 'base_url'}
    if not required.issubset(config):
        raise ConfigurationError(f'LLM configuration is missing: {sorted(required - set(config))}')
    if config['provider'] != 'openai':
        raise ConfigurationError('The experiment contract requires the OpenAI-compatible provider')
    host = urlsplit(config['base_url']).hostname
    allowed_hosts = {'api.openai.com'} if final else {'127.0.0.1', 'localhost', '::1'}
    if host not in allowed_hosts:
        label = 'OpenAI API' if final else 'loopback model'
        raise ConfigurationError(f'The experiment contract must use the {label} endpoint')
    expected_model = 'gpt-4o-mini-2024-07-18' if final else 'qwen2.5-0.5b-instruct'
    if config['model_name'] != expected_model:
        raise ConfigurationError(f'Expected frozen model {expected_model}')
    if config['temperature'] != 0.0 or config['seed'] != 42:
        raise ConfigurationError('Experiments require temperature 0.0 and requested seed 42')
    expected_tokens = 256 if judge else 1024
    if config['max_tokens'] != expected_tokens:
        raise ConfigurationError(f'Expected max_tokens={expected_tokens}')


def _validate_dependencies(lock_path, names):
    locked = {}
    for line in lock_path.read_text().splitlines():
        if '==' in line:
            name, locked_version = line.split('==', 1)
            locked[name.lower().replace('_', '-')] = locked_version
    for name in names:
        normalized = name.lower().replace('_', '-')
        if normalized not in locked:
            raise ConfigurationError(f'Dependency is absent from lock: {name}')
        try:
            installed = version(name)
        except PackageNotFoundError as exc:
            raise ConfigurationError(f'Dependency is not installed: {name}') from exc
        if installed != locked[normalized]:
            raise ConfigurationError(
                f'Dependency version differs from lock: {name} {installed} != {locked[normalized]}')


def _canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def experiment_manifest_directory(config_path, contract):
    """Resolve a contract-owned manifest directory without repository escape."""
    config_path = Path(config_path).resolve()
    reference = contract.get('manifest_directory', '../../manifests')
    directory = (config_path.parent / reference).resolve()
    try:
        directory.relative_to(ROOT / 'manifests')
    except ValueError as exc:
        raise ConfigurationError('Manifest directory must stay under manifests/') from exc
    if not directory.is_dir():
        raise ConfigurationError('Manifest directory does not exist')
    return directory


def _validate_final_manifests(config_path, contract):
    directory = experiment_manifest_directory(config_path, contract)
    expected_names = {
        'tasks': 'tasks.json',
        'attacks': 'attacks.json',
        'confirmation': 'confirmation_tasks.json',
        'matrix': 'final_matrix.json',
    }
    hashes = contract['manifest_hashes']
    if set(hashes) != set(expected_names):
        raise ConfigurationError('Final manifest hash map is incomplete')
    expected_version = {
        'crewai-g5-final-v1': 'g5-v1',
        'crewai-g5-final-v2': 'g5-v2',
    }[contract['contract_id']]
    loaded = {}
    for key, name in expected_names.items():
        try:
            value = json.loads((directory / name).read_text())
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f'Cannot read final manifest: {name}') from exc
        if value.get('manifest_version') != expected_version or hashes[key] != _canonical_hash(value):
            raise ConfigurationError(f'Final manifest version/hash mismatch: {name}')
        loaded[key] = value
    expected_planned = {
        'core_attacks': 927,
        'benign': 69,
        'calibration': 0,
        'confirmation': 60,
        'pilot_separate': 0,
        'total_excluding_pilot_and_retries': 1056,
    }
    if (contract['planned_runs'] != expected_planned
            or loaded['matrix'].get('planned_logical_runs') != 1056):
        raise ConfigurationError('G5 planned run counts differ from the frozen matrix')
    if loaded['matrix'].get('mas_ids') != contract['active_mas']:
        raise ConfigurationError('G5 matrix and active MAS disagree')


def load_experiment_configuration(path='configs/experiments/core.yaml'):
    path = _repo_path(ROOT, path) if not Path(path).is_absolute() else Path(path).resolve()
    try:
        path.relative_to(ROOT / 'configs')
    except ValueError as exc:
        raise ConfigurationError('Experiment configuration must be under configs/') from exc
    contract = _mapping(path)
    final = contract.get('stage') == 'final'
    expected_keys = BASE_TOP_LEVEL_KEYS | (FINAL_EXTRA_KEYS if final else set())
    if set(contract) != expected_keys:
        raise ConfigurationError(
            f'Experiment configuration keys differ: expected {sorted(expected_keys)}')
    if (contract['schema_version'] != '1.0' or contract['max_turn'] != 1
            or contract['normalizer'] != 'text-envelope-v1'):
        raise ConfigurationError('Experiment schema, turn policy, or normalizer changed')
    if final:
        if (contract['contract_id'] not in {'crewai-g5-final-v1', 'crewai-g5-final-v2'}
                or contract['default_experiment_id'] != contract['contract_id']
                or contract['model_policy'] != 'openai-gpt-4o-mini-final'
                or type(contract['final_benchmark_ready']) is not bool
                or contract['paid_api_budget_usd'] != 2.0):
            raise ConfigurationError('G5 model, readiness, or cost ceiling changed')
        if contract['cost_policy'] != {
            'input_per_million_usd': 0.15,
            'output_per_million_usd': 0.60,
            'pricing_as_of': '2026-09-11',
            'pricing_source': 'https://developers.openai.com/api/docs/models/gpt-4o-mini',
            'pilot_scaled_estimate_usd': 0.74584752,
            'execution_ceiling_usd': 2.0,
        }:
            raise ConfigurationError('G5 pricing or execution ceiling changed')
        seed = contract['seed_policy']
        expected_preflight = (
            '../../outputs/g5-v2/provider_preflight.json'
            if contract['contract_id'].endswith('-v2')
            else '../../outputs/g5/provider_preflight.json')
        if (seed.get('requested') != 42
                or seed.get('status') not in {'provider_preflight_required',
                                               'accepted_best_effort'}
                or seed.get('preflight_artifact') != expected_preflight):
            raise ConfigurationError('G5 seed policy changed')
        if contract['final_benchmark_ready'] != (seed['status'] == 'accepted_best_effort'):
            raise ConfigurationError('G5 readiness and provider preflight status disagree')
        _validate_final_manifests(path, contract)
    elif (contract['stage'] != 'development'
          or contract['model_policy'] != 'bionic-local-development'
          or contract['final_benchmark_ready'] is not False
          or contract['paid_api_budget_usd'] != 0):
        raise ConfigurationError('Experiment stage, model, or budget is not the G0 contract')
    if contract['active_mas'] != ['crewai_seq_nodeleg'] or contract['task_domains'] != ['math', 'code']:
        raise ConfigurationError('G0 active MAS or task domains changed')
    expected_retry = {
        'sdk_requests_per_llm_call': 1,
        'max_recorded_attempts': 3,
        'requires_explicit_retry': True,
    } if contract.get('contract_id') == 'crewai-g5-final-v2' else {
        'provider_requests_per_attempt': 1,
        'max_recorded_attempts': 3,
        'requires_explicit_retry': True,
    }
    if contract['retry_policy'] != expected_retry:
        raise ConfigurationError('Retry policy changed')
    expected_judge = {'response_format': 'json_schema',
                      'disruption_labels': ['attempted_answer', 'refusal', 'unrelated'],
                      'attack_success_labels': ['refusal', 'unrelated']}
    if contract['judge_policy'] != expected_judge:
        raise ConfigurationError('Judge classification policy changed')
    if contract['verifiers'] != {'math': 'isolated-math-v1',
                                 'code': 'linux-x86_64-landlock-seccomp-v1'}:
        raise ConfigurationError('Verifier policy changed')
    if not final:
        expected_runs = {'core_attacks': 306, 'benign': 69, 'calibration': 20,
                         'confirmation': 60, 'pilot_separate': 30,
                         'total_excluding_pilot_and_retries': 455}
        if contract['planned_runs'] != expected_runs:
            raise ConfigurationError('Planned run counts differ from the manifest contract')
    for key in contract:
        if key.lower() in SECRET_KEYS:
            raise ConfigurationError('Experiment contract must not contain credentials')

    model_path = _repo_path(path.parent, contract['model_config'])
    judge_path = _repo_path(path.parent, contract['judge_config'])
    lock_path = _repo_path(path.parent, contract['dependency_lock'])
    model, judge = _mapping(model_path), _mapping(judge_path)
    _validate_llm(model, final=final)
    _validate_llm(judge, judge=True, final=final)
    _validate_dependencies(lock_path, contract['dependency_checks'])
    return contract, model, judge
