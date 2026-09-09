"""Single-source experiment configuration and dependency-lock validation."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[2]
SECRET_KEYS = {'api_key', 'api_token', 'access_token', 'authorization',
               'password', 'secret'}
TOP_LEVEL_KEYS = {
    'schema_version', 'contract_id', 'stage', 'default_experiment_id',
    'model_config', 'judge_config', 'active_mas', 'task_domains',
    'model_policy', 'final_benchmark_ready', 'paid_api_budget_usd',
    'max_turn', 'normalizer', 'retry_policy', 'judge_policy', 'verifiers',
    'dependency_lock', 'dependency_checks', 'planned_runs',
}
UTILITY_VERIFIER_VERSION = 'isolated-math-v1/linux-x86_64-landlock-seccomp-v1'


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


def _validate_llm(config, *, judge=False):
    required = {'provider', 'model_name', 'temperature', 'max_tokens', 'seed', 'base_url'}
    if not required.issubset(config):
        raise ConfigurationError(f'LLM configuration is missing: {sorted(required - set(config))}')
    if config['provider'] != 'openai':
        raise ConfigurationError('The G0 development contract requires the local OpenAI-compatible provider')
    host = urlsplit(config['base_url']).hostname
    if host not in {'127.0.0.1', 'localhost', '::1'}:
        raise ConfigurationError('The G0 development contract must use a loopback model endpoint')
    if config['temperature'] != 0.0 or config['seed'] != 42:
        raise ConfigurationError('G0 requires temperature 0.0 and requested seed 42')
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


def load_experiment_configuration(path='configs/experiments/core.yaml'):
    path = _repo_path(ROOT, path) if not Path(path).is_absolute() else Path(path).resolve()
    try:
        path.relative_to(ROOT / 'configs')
    except ValueError as exc:
        raise ConfigurationError('Experiment configuration must be under configs/') from exc
    contract = _mapping(path)
    if set(contract) != TOP_LEVEL_KEYS:
        raise ConfigurationError(
            f'Experiment configuration keys differ: expected {sorted(TOP_LEVEL_KEYS)}')
    if (contract['schema_version'] != '1.0' or contract['stage'] != 'development'
            or contract['model_policy'] != 'bionic-local-development'
            or contract['final_benchmark_ready'] is not False
            or contract['paid_api_budget_usd'] != 0 or contract['max_turn'] != 1
            or contract['normalizer'] != 'text-envelope-v1'):
        raise ConfigurationError('Experiment stage, model, budget, or turn policy is not the G0 contract')
    if contract['active_mas'] != ['crewai_seq_nodeleg'] or contract['task_domains'] != ['math', 'code']:
        raise ConfigurationError('G0 active MAS or task domains changed')
    if contract['retry_policy'] != {'provider_requests_per_attempt': 1,
                                    'max_recorded_attempts': 3,
                                    'requires_explicit_retry': True}:
        raise ConfigurationError('Retry policy changed')
    expected_judge = {'response_format': 'json_schema',
                      'disruption_labels': ['attempted_answer', 'refusal', 'unrelated'],
                      'attack_success_labels': ['refusal', 'unrelated']}
    if contract['judge_policy'] != expected_judge:
        raise ConfigurationError('Judge classification policy changed')
    if contract['verifiers'] != {'math': 'isolated-math-v1',
                                 'code': 'linux-x86_64-landlock-seccomp-v1'}:
        raise ConfigurationError('Verifier policy changed')
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
    _validate_llm(model)
    _validate_llm(judge, judge=True)
    _validate_dependencies(lock_path, contract['dependency_checks'])
    return contract, model, judge
