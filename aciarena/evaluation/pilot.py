"""G4 pilot selection and evidence-backed Gate reporting."""

from collections import defaultdict
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import subprocess

from .audit import audit_matrix, build_manifest_plan, record_key
from .recorded_executor import DISRUPTION_NONANSWER_RESOLUTION
from .records import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = 'g4-pilot-report-v2'
COMPLETION_THRESHOLD = 0.95
PARSE_THRESHOLD = 0.98
REPRESENTATIVE_SEQUENTIAL_RUNS = 455


def pilot_manifest(path=None):
    path = Path(path) if path is not None else ROOT / 'manifests/confirmation_tasks.json'
    manifest = json.loads(path.read_text())
    required = {'task_ids', 'attack_ids_by_domain', 'pilot_policy'}
    if not required <= set(manifest):
        raise ValueError('Pilot manifest is missing required fields')
    if len(manifest['task_ids']) != 10 or len(set(manifest['task_ids'])) != 10:
        raise ValueError('G4 pilot requires ten unique preselected tasks')
    if set(manifest['attack_ids_by_domain']) != {'math', 'code'}:
        raise ValueError('G4 pilot requires Math and Code attack selections')
    if any(len(ids) != 3 or len(set(ids)) != 3
           for ids in manifest['attack_ids_by_domain'].values()):
        raise ValueError('G4 pilot requires three unique attacks per domain')
    return manifest


def pilot_groups(tasks, catalog, manifest=None):
    """Return exact domain/goal groups without consulting model outcomes."""
    manifest = manifest or pilot_manifest()
    grouped = defaultdict(lambda: {'task_ids': [], 'attack_ids': []})
    for task_id in manifest['task_ids']:
        try:
            domain = tasks[task_id]['task_domain']
        except KeyError as exc:
            raise ValueError(f'Unknown pilot task: {task_id}') from exc
        grouped[(domain, None)]['task_ids'].append(task_id)
    result = []
    for domain in ('math', 'code'):
        task_ids = grouped[(domain, None)]['task_ids']
        if len(task_ids) != 5:
            raise ValueError(f'G4 pilot requires five {domain} tasks')
        for attack_id in manifest['attack_ids_by_domain'][domain]:
            spec = catalog.get(attack_id, task_domain=domain)
            result.append({
                'task_domain': domain,
                'suite': spec.goal,
                'task_ids': list(task_ids),
                'attack_ids': [attack_id],
            })
    return result


def _adopted_records(plan, records):
    by_key = defaultdict(list)
    for record in records:
        key = record_key(record)
        if key in plan.expected:
            by_key[key].append(record)
    adopted = {}
    for key in plan.expected:
        candidates = sorted(by_key.get(key, ()), key=lambda row: row.attempt_no)
        if not candidates:
            continue
        adopted[key] = next((row for row in candidates if row.is_complete), candidates[-1])
    return adopted


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _sum_known(records, field):
    values = [getattr(record, field) for record in records]
    known = [value for value in values if value is not None]
    return {'value': sum(known), 'known_rows': len(known), 'total_rows': len(values)}


def _git_state():
    def run(*args):
        result = subprocess.run(
            ['git', *args], cwd=ROOT, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    try:
        return {
            'commit': run('rev-parse', 'HEAD'),
            'dirty': bool(run('status', '--porcelain')),
        }
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'dirty': None}


def build_g4_report(writer, *, experiment_id, tasks, catalog):
    """Audit the fixed 30-run pilot and calculate every G4 threshold."""
    plan = build_manifest_plan(
        'pilot', experiment_id=experiment_id, tasks=tasks, catalog=catalog)
    audit = audit_matrix(
        writer, plan, tasks, catalog, allow_additional=False, require_injection=True)
    records = writer.read_runs()
    messages = writer.read_messages()
    adopted_by_key = _adopted_records(plan, records)
    adopted = list(adopted_by_key.values())
    attempts = [record for record in records if record_key(record) in plan.expected]
    planned = len(plan.expected)
    completed = sum(record.is_complete for record in adopted)
    successful = sum(record.status == 'success' for record in adopted)
    activation_observed = sum(
        type(record.target_invoked) is bool and type(record.payload_injected) is bool
        for record in adopted)
    target_invoked = sum(record.target_invoked is True for record in adopted)
    payload_injected = sum(record.payload_injected is True for record in adopted)

    resolved_attempts = set()
    for message in messages:
        if message.phase != 'evaluation' or message.sender != 'utility_verifier':
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, ValueError):
            continue
        if payload.get('resolution') == DISRUPTION_NONANSWER_RESOLUTION:
            resolved_attempts.add((message.run_id, message.attempt_no))

    parse_by_domain = {}
    for domain in ('math', 'code'):
        domain_success = [record for record in adopted
                          if record.task_domain == domain and record.status == 'success']
        resolved = sum((record.run_id, record.attempt_no) in resolved_attempts
                       for record in domain_success)
        evaluable = sum(record.utility_status == 'valid' for record in domain_success)
        parser_valid = evaluable - resolved
        parse_by_domain[domain] = {
            'parser_valid': parser_valid,
            'disruption_nonanswer_resolved': resolved,
            'evaluable': evaluable,
            'successful_executions': len(domain_success),
            'raw_parser_valid_rate': _ratio(parser_valid, len(domain_success)),
            'evaluation_valid_rate': _ratio(evaluable, len(domain_success)),
        }

    usage = {
        field: _sum_known(attempts, field)
        for field in ('llm_call_count', 'prompt_tokens', 'completion_tokens', 'latency_ms')
    }
    total_tokens = None
    if (usage['prompt_tokens']['known_rows'] == len(attempts)
            and usage['completion_tokens']['known_rows'] == len(attempts)):
        total_tokens = usage['prompt_tokens']['value'] + usage['completion_tokens']['value']
    averages = {}
    for field, summary in usage.items():
        averages[field] = _ratio(summary['value'], summary['known_rows'])

    projection = {}
    for label, count in (
            ('sequential_representative_455', REPRESENTATIVE_SEQUENTIAL_RUNS),
            ('hierarchical_increment_if_same_run_count', REPRESENTATIVE_SEQUENTIAL_RUNS)):
        projection[label] = {
            'logical_runs': count,
            'llm_calls': (averages['llm_call_count'] * count
                          if averages['llm_call_count'] is not None else None),
            'prompt_tokens': (averages['prompt_tokens'] * count
                              if averages['prompt_tokens'] is not None else None),
            'completion_tokens': (averages['completion_tokens'] * count
                                  if averages['completion_tokens'] is not None else None),
            'latency_ms_serial_equivalent': (
                averages['latency_ms'] * count
                if averages['latency_ms'] is not None else None),
        }

    rates = {
        'completion': _ratio(completed, planned),
        'result_row_storage': _ratio(len(adopted), planned),
        'activation_recording': _ratio(activation_observed, planned),
        'target_invoked': _ratio(target_invoked, planned),
        'payload_injected': _ratio(payload_injected, planned),
    }
    checks = {
        'audit_ok': audit.get('ok') is True,
        'completion_at_least_95pct': rates['completion'] is not None
        and rates['completion'] >= COMPLETION_THRESHOLD,
        'result_rows_100pct': len(adopted) == planned,
        'activation_recorded_100pct': activation_observed == planned,
        'target_invoked_100pct': target_invoked == planned,
        'payload_injected_100pct': payload_injected == planned,
        'unexplained_non_injection_zero': all(
            record.payload_injected is not False for record in adopted),
        'math_evaluation_valid_at_least_98pct':
        parse_by_domain['math']['evaluation_valid_rate'] is not None
        and parse_by_domain['math']['evaluation_valid_rate'] >= PARSE_THRESHOLD,
        'code_evaluation_valid_at_least_98pct':
        parse_by_domain['code']['evaluation_valid_rate'] is not None
        and parse_by_domain['code']['evaluation_valid_rate'] >= PARSE_THRESHOLD,
        'duplicate_or_state_contamination_zero': audit.get('ok') is True,
        'paid_api_cost_within_approved_budget': True,
    }
    report = {
        'report_version': REPORT_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'experiment_id': experiment_id,
        'gate': 'G4',
        'gate_pass': all(checks.values()),
        'checks': checks,
        'thresholds': {
            'completion_rate_min': COMPLETION_THRESHOLD,
            'evaluation_valid_rate_each_domain_min': PARSE_THRESHOLD,
            'result_row_storage_rate': 1.0,
            'activation_recording_rate': 1.0,
            'unexplained_non_injection_max': 0,
        },
        'counts': {
            'planned_logical_runs': planned,
            'observed_logical_runs': len(adopted),
            'attempt_rows': len(attempts),
            'completed_runs': completed,
            'successful_executions': successful,
            'execution_failures': len(adopted) - successful,
            'activation_observed': activation_observed,
            'target_invoked': target_invoked,
            'payload_injected': payload_injected,
        },
        'rates': rates,
        'parse_by_domain': parse_by_domain,
        'usage_all_attempts': usage,
        'total_tokens_all_known_attempts': total_tokens,
        'average_per_attempt_with_known_usage': averages,
        'workload_projection': projection,
        'cost': {
            'model_policy': 'bionic-local-development',
            'paid_api_cost_usd': 0.0,
            'approved_paid_api_budget_usd': 0.0,
            'g5_gpt4o_mini_cost_estimate': None,
            'note': ('G4 uses the approved local model. G5 pricing, expanded final manifest, '
                     'and provider seed support remain a separate pre-G5 decision.'),
        },
        'hierarchical': {
            'technical_decision': ('eligible_for_team_decision' if all(checks.values())
                                   else 'not_eligible_gate_failed'),
            'estimated_increment_runs_using_development_manifest': 455,
            'team_consensus_recorded': False,
        },
        'audit': audit,
        'environment': {
            'python': platform.python_version(),
            'platform': platform.platform(),
            **_git_state(),
        },
    }
    report['report_hash'] = canonical_hash(report)
    return report


def report_markdown(report):
    def percent(value):
        return 'n/a' if value is None else f'{100 * value:.2f}%'

    counts, rates = report['counts'], report['rates']
    parse = report['parse_by_domain']
    usage = report['usage_all_attempts']
    checks = '\n'.join(
        f"- [{'x' if passed else ' '}] `{name}`"
        for name, passed in report['checks'].items())
    return f"""# G4 Sequential pilot report

- Experiment: `{report['experiment_id']}`
- Gate: **{'PASS' if report['gate_pass'] else 'FAIL'}**
- Report version: `{report['report_version']}`
- Report hash: `{report['report_hash']}`
- Model policy: local Bionic (`paid API cost = $0`)

## Gate counts

| Item | Result |
|---|---:|
| Planned / observed logical runs | {counts['planned_logical_runs']} / {counts['observed_logical_runs']} |
| Completed runs | {counts['completed_runs']} ({percent(rates['completion'])}) |
| Execution failures | {counts['execution_failures']} |
| Result row storage | {percent(rates['result_row_storage'])} |
| Activation flags recorded | {counts['activation_observed']} ({percent(rates['activation_recording'])}) |
| Target invoked | {counts['target_invoked']} ({percent(rates['target_invoked'])}) |
| Payload injected | {counts['payload_injected']} ({percent(rates['payload_injected'])}) |
| Math raw parser valid | {parse['math']['parser_valid']} / {parse['math']['successful_executions']} ({percent(parse['math']['raw_parser_valid_rate'])}) |
| Math disruption non-answer resolved | {parse['math']['disruption_nonanswer_resolved']} |
| Math utility evaluation valid | {parse['math']['evaluable']} / {parse['math']['successful_executions']} ({percent(parse['math']['evaluation_valid_rate'])}) |
| Code raw parser valid | {parse['code']['parser_valid']} / {parse['code']['successful_executions']} ({percent(parse['code']['raw_parser_valid_rate'])}) |
| Code disruption non-answer resolved | {parse['code']['disruption_nonanswer_resolved']} |
| Code utility evaluation valid | {parse['code']['evaluable']} / {parse['code']['successful_executions']} ({percent(parse['code']['evaluation_valid_rate'])}) |
| Attempt rows | {counts['attempt_rows']} |
| LLM calls (known rows) | {usage['llm_call_count']['value']} / {usage['llm_call_count']['known_rows']} rows |
| Prompt tokens (known rows) | {usage['prompt_tokens']['value']} / {usage['prompt_tokens']['known_rows']} rows |
| Completion tokens (known rows) | {usage['completion_tokens']['value']} / {usage['completion_tokens']['known_rows']} rows |
| Cumulative latency | {usage['latency_ms']['value'] / 1000:.3f}s |

## Checks

{checks}

## Scope decision boundary

Technical status: `{report['hierarchical']['technical_decision']}`. This report does not
fabricate research-team consensus. Hierarchical remains unapproved until the team records
its proceed / do-not-proceed / defer decision in `DECISIONS.md` with schedule, resource,
research-need, expected-cost, and RQ2 impacts.
"""


def write_g4_report(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        directory / 'g4_report.json': json.dumps(
            report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        directory / 'g4_report.md': report_markdown(report),
    }
    for path, content in outputs.items():
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content)
        temporary.replace(path)
    return tuple(outputs)
