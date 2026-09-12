"""Run the frozen Sequential G5 matrix with progress and paid-cost safeguards."""

from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
import json
from pathlib import Path

from dotenv import load_dotenv

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import MatrixPlan, audit_matrix, build_matrix_plan, record_key
from aciarena.evaluation.configuration import (
    experiment_manifest_directory,
    load_experiment_configuration,
)
from aciarena.evaluation.recorded_executor import load_task_manifest
from aciarena.evaluation.recorded_executor import recorded_configuration
from aciarena.evaluation.records import canonical_hash
from aciarena.evaluation.recorded_suite import RecordedEvaluationSuite
from aciarena.evaluation.run_writer import RunWriter


ROOT = Path(__file__).resolve().parents[2]
PROGRESS_VERSION = 'g5-progress-v1'
STAGES = ('smoke', 'benign', 'math-core', 'code-core', 'confirmation', 'all')
SMOKE_ATTACK_IDS = {
    'math': {
        'disclosure': 'disclosure_math_location.instruction.v1',
        'disruption': 'disruption_ddos.message.v1',
        'hijacking': 'hijacking_answer_mapping.agent.v1',
    },
    'code': {
        'disclosure': 'disclosure_code_apikey.instruction.v1',
        'disruption': 'disruption_ddos.message.v1',
        'hijacking': 'hijacking_malicious_report.agent.v1',
    },
}


def g5_groups(contract, manifest_directory):
    _, tasks = load_task_manifest(manifest_directory / 'tasks.json')
    catalog = AttackCatalog(manifest_directory / 'attacks.json')
    confirmation = json.loads((manifest_directory / 'confirmation_tasks.json').read_text())
    groups = []
    for domain in ('math', 'code'):
        task_ids = [task_id for task_id, row in tasks.items() if row['task_domain'] == domain]
        groups.append({
            'phase': 'core', 'repetition': 1, 'task_domain': domain,
            'suite': 'benign', 'task_ids': task_ids, 'attack_ids': ['none'],
        })
        for suite in ('disclosure', 'disruption', 'hijacking'):
            attack_ids = [
                spec.attack_id for spec in catalog.specs.values()
                if domain in spec.domains and spec.goal == suite
            ]
            groups.append({
                'phase': 'core', 'repetition': 1, 'task_domain': domain,
                'suite': suite, 'task_ids': task_ids, 'attack_ids': attack_ids,
            })
    selected = confirmation['task_ids']
    for repetition in confirmation['additional_repetitions']:
        for domain in ('math', 'code'):
            task_ids = [task_id for task_id in selected if tasks[task_id]['task_domain'] == domain]
            for suite in ('disclosure', 'disruption', 'hijacking'):
                attack_ids = [
                    attack_id for attack_id in confirmation['attack_ids_by_domain'][domain]
                    if catalog.get(attack_id, task_domain=domain).goal == suite
                ]
                groups.append({
                    'phase': 'confirmation', 'repetition': repetition,
                    'task_domain': domain, 'suite': suite,
                    'task_ids': task_ids, 'attack_ids': attack_ids,
                })
    planned = sum(
        len(group['task_ids']) * len(group['attack_ids']) for group in groups
    )
    if planned != contract['planned_runs']['total_excluding_pilot_and_retries']:
        raise ValueError(f'G5 group plan mismatch: {planned}')
    return groups, tasks, catalog


def matrix_plan(experiment_id, groups, tasks, catalog, config_hash):
    expected = set()
    for group in groups:
        plan = build_matrix_plan(
            experiment_id=experiment_id,
            selections=[
                (task_id, attack_id)
                for task_id in group['task_ids'] for attack_id in group['attack_ids']
            ],
            tasks=tasks,
            catalog=catalog,
            repetition=group['repetition'],
            phase=group['phase'],
            config_hash=config_hash,
        )
        overlap = expected & set(plan.expected)
        if overlap:
            raise ValueError('G5 groups contain duplicate logical runs')
        expected.update(plan.expected)
    return MatrixPlan(frozenset(expected))


def stage_groups(groups, stage):
    """Select a deterministic, possibly overlapping view of the frozen matrix."""
    if stage not in STAGES:
        raise ValueError(f'Unknown G5 stage: {stage}')
    if stage == 'all':
        return list(groups)
    if stage == 'benign':
        return [group for group in groups if group['phase'] == 'core'
                and group['suite'] == 'benign']
    if stage == 'math-core':
        return [group for group in groups if group['phase'] == 'core'
                and group['task_domain'] == 'math' and group['suite'] != 'benign']
    if stage == 'code-core':
        return [group for group in groups if group['phase'] == 'core'
                and group['task_domain'] == 'code' and group['suite'] != 'benign']
    if stage == 'confirmation':
        return [group for group in groups if group['phase'] == 'confirmation']

    smoke = []
    for group in groups:
        if group['phase'] != 'core':
            continue
        attack_ids = ['none'] if group['suite'] == 'benign' else [
            SMOKE_ATTACK_IDS[group['task_domain']][group['suite']]
        ]
        if attack_ids[0] not in group['attack_ids']:
            raise ValueError('Frozen smoke attack is absent from the G5 core plan')
        smoke.append({**group, 'task_ids': group['task_ids'][:1],
                      'attack_ids': attack_ids})
    if len(smoke) != 8:
        raise ValueError('G5 smoke stage requires eight fixed logical runs')
    return smoke


def execution_groups(groups, batch_size=20):
    """Split a stage into bounded batches without changing logical run identities."""
    if batch_size < 1:
        raise ValueError('G5 execution batch size must be positive')
    result = []
    for group in groups:
        for attack_id in group['attack_ids']:
            for offset in range(0, len(group['task_ids']), batch_size):
                result.append({
                    **group,
                    'task_ids': group['task_ids'][offset:offset + batch_size],
                    'attack_ids': [attack_id],
                })
    return result


def pending_execution_groups(batches, experiment_id, tasks, catalog, config_hash,
                             complete_keys):
    """Drop fully completed batches so repeated capped sessions move forward."""
    return [
        batch for batch in batches
        if not set(matrix_plan(
            experiment_id, [batch], tasks, catalog, config_hash).expected) <= complete_keys
    ]


def usage_cost(records, cost_policy):
    prompt = [row.prompt_tokens for row in records if row.prompt_tokens is not None]
    completion = [row.completion_tokens for row in records if row.completion_tokens is not None]
    cost = (sum(prompt) / 1_000_000 * cost_policy['input_per_million_usd']
            + sum(completion) / 1_000_000 * cost_policy['output_per_million_usd'])
    missing_calls = sum(row.usage_missing_calls for row in records)
    complete_rows = sum(
        row.usage_missing_calls == 0
        and row.prompt_tokens is not None
        and row.completion_tokens is not None
        for row in records
    )
    return {
        'attempt_rows': len(records),
        'prompt_tokens': sum(prompt),
        'completion_tokens': sum(completion),
        'usage_known_rows': complete_rows,
        'usage_incomplete_rows': len(records) - complete_rows,
        'usage_missing_calls': missing_calls,
        'usage_complete': complete_rows == len(records),
        'cost_is_lower_bound': missing_calls > 0 or complete_rows != len(records),
        'cost_usd': cost,
    }


def progress_report(writer, plan, tasks, catalog, contract, experiment_id):
    audit = audit_matrix(
        writer, plan, tasks, catalog,
        allow_additional=False, require_injection=True,
    )
    usage = usage_cost(writer.read_runs(), contract['cost_policy'])
    return {
        'progress_version': PROGRESS_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'experiment_id': experiment_id,
        'planned_logical_runs': len(plan.expected),
        'observed_logical_runs': audit.get('observed_logical_runs', 0),
        'completed_runs': audit.get('completed_runs', 0),
        'execution_errors': audit.get('execution_errors', 0),
        'missing_runs': audit.get('missing_runs', len(plan.expected)),
        'matrix_complete': audit.get('ok') is True and audit.get('completed_runs') == len(plan.expected),
        'audit': audit,
        'usage': usage,
        'cost_ceiling_usd': contract['cost_policy']['execution_ceiling_usd'],
        'within_cost_ceiling': (
            usage['usage_complete']
            and usage['cost_usd'] <= contract['cost_policy']['execution_ceiling_usd']),
    }


def write_progress(directory, report):
    path = directory / 'g5_progress.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)
    return path


def suite_args(cli, group):
    return Namespace(
        attack_ids=group['attack_ids'],
        experiment_id=cli.experiment_id,
        experiment_config=cli.experiment_config,
        phase=group['phase'],
        repetition=group['repetition'],
        # The G5 orchestrator is append-only and always reuses complete logical
        # runs; explicit retries remain separately gated by --retry-errors.
        resume=True,
        retry_errors=cli.retry_errors,
        model_config=None,
        judge_config=None,
        mas='crewai_seq_nodeleg',
        suite=group['suite'],
        attack_mode='continuous',
        defense='none',
        task_domain=group['task_domain'],
        max_workers=cli.max_workers,
        limit=None,
        task_ids=group['task_ids'],
        output_dir=cli.output_dir,
        malicious_agents=[],
    )


def preflight_passed(contract, model):
    path = (ROOT / 'configs/experiments' / contract['seed_policy']['preflight_artifact']).resolve()
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    required_checks = {
        'snapshot_accessible', 'seed_parameter_accepted',
        'repeated_outputs_identical', 'strict_json_schema_supported',
    }
    checks = report.get('checks')
    return (
        report.get('preflight_version') == 'g5-provider-preflight-v1'
        and report.get('pass') is True
        and report.get('requested_model') == model['model_name']
        and report.get('temperature') == model['temperature']
        and report.get('seed_requested') == model['seed']
        and isinstance(checks, dict)
        and set(checks) == required_checks
        and all(checks.values())
    )


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id')
    parser.add_argument('--experiment-config', default='configs/experiments/g5_v2.yaml')
    parser.add_argument('--output-dir', default='outputs/g5-v2')
    parser.add_argument('--max-workers', type=int, default=4)
    parser.add_argument('--stage', choices=STAGES, default='all')
    parser.add_argument('--batch-size', type=int, default=1,
                        help='Maximum logical runs sent per execution batch')
    parser.add_argument('--max-batches', type=int,
                        help='Stop cleanly after this many new execution batches')
    parser.add_argument('--session-cost-limit-usd', type=float, default=1.00,
                        help='Stop between batches after this invocation reaches the limit')
    parser.add_argument('--allow-full-matrix', action='store_true',
                        help='Required with --execute --stage all')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--execute', action='store_true', help='Allow paid API calls; default is dry-run')
    args = parser.parse_args(argv)
    if args.max_workers < 1:
        parser.error('--max-workers must be positive')
    if args.batch_size < 1 or args.batch_size > 20:
        parser.error('--batch-size must be between 1 and 20')
    if args.max_batches is not None and args.max_batches < 1:
        parser.error('--max-batches must be positive')
    if args.session_cost_limit_usd <= 0:
        parser.error('--session-cost-limit-usd must be positive')
    if args.execute and args.stage == 'all' and not args.allow_full_matrix:
        parser.error('--execute --stage all requires --allow-full-matrix')
    if args.execute and args.batch_size != 1:
        parser.error('paid execution requires --batch-size 1 for per-run cost checks')

    contract, model, judge = load_experiment_configuration(args.experiment_config)
    if args.experiment_id is None:
        args.experiment_id = contract['default_experiment_id']
    elif args.experiment_id != contract['default_experiment_id']:
        parser.error('--experiment-id must match the selected final experiment contract')
    manifest_directory = experiment_manifest_directory(args.experiment_config, contract)
    groups, tasks, catalog = g5_groups(contract, manifest_directory)
    task_manifest, _ = load_task_manifest(manifest_directory / 'tasks.json')
    _, run_config = recorded_configuration(
        model, judge, contract, task_manifest, catalog)
    config_hash = canonical_hash(run_config)
    plan = matrix_plan(args.experiment_id, groups, tasks, catalog, config_hash)
    selected_groups = stage_groups(groups, args.stage)
    selected_plan = matrix_plan(
        args.experiment_id, selected_groups, tasks, catalog, config_hash)
    batches = execution_groups(selected_groups, args.batch_size)
    directory = Path(args.output_dir) / args.experiment_id
    writer = RunWriter(directory)
    complete_keys = {record_key(row) for row in writer.read_runs() if row.is_complete}
    pending_batches = pending_execution_groups(
        batches, args.experiment_id, tasks, catalog, config_hash, complete_keys)
    if not args.execute:
        payload = {
            'mode': 'dry-run',
            'experiment_id': args.experiment_id,
            'stage': args.stage,
            'final_benchmark_ready': contract['final_benchmark_ready'],
            'provider_preflight_passed': preflight_passed(contract, model),
            'config_hash': config_hash,
            'full_matrix_logical_runs': len(plan.expected),
            'stage_logical_runs': len(selected_plan.expected),
            'execution_batches': len(batches),
            'pending_execution_batches': len(pending_batches),
            'batch_size': args.batch_size,
            'max_batches': args.max_batches,
            'session_cost_limit_usd': args.session_cost_limit_usd,
            'pilot_scaled_estimate_usd': contract['cost_policy']['pilot_scaled_estimate_usd'],
            'stage_scaled_estimate_usd': (
                contract['cost_policy']['pilot_scaled_estimate_usd']
                * len(selected_plan.expected) / len(plan.expected)
            ),
            'cost_ceiling_usd': contract['cost_policy']['execution_ceiling_usd'],
            'paid_api_calls_made': 0,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not contract['final_benchmark_ready'] or not preflight_passed(contract, model):
        raise RuntimeError('G5 paid execution is locked until the provider preflight passes')

    load_dotenv(ROOT / '.env')
    group_results = []
    baseline_usage = usage_cost(writer.read_runs(), contract['cost_policy'])
    if not baseline_usage['usage_complete']:
        raise RuntimeError('G5 paid execution stopped because prior usage is incomplete')
    baseline_cost = baseline_usage['cost_usd']
    stop_reason = None
    for index, group in enumerate(pending_batches, 1):
        if args.max_batches is not None and len(group_results) >= args.max_batches:
            stop_reason = 'max_batches_reached'
            break
        current = usage_cost(writer.read_runs(), contract['cost_policy'])
        if not current['usage_complete']:
            raise RuntimeError('G5 paid execution stopped because provider usage is incomplete')
        if current['cost_usd'] >= contract['cost_policy']['execution_ceiling_usd']:
            report = progress_report(writer, plan, tasks, catalog, contract, args.experiment_id)
            write_progress(directory, report)
            raise RuntimeError('G5 paid execution stopped at the configured cost ceiling')
        if current['cost_usd'] - baseline_cost >= args.session_cost_limit_usd:
            stop_reason = 'session_cost_limit_reached'
            break
        result = RecordedEvaluationSuite(suite_args(args, group)).eval()
        group_results.append({'group_index': index, **group, 'result': result})
        report = progress_report(writer, plan, tasks, catalog, contract, args.experiment_id)
        write_progress(directory, report)
        print(json.dumps({
            'group': index,
            'groups_total': len(pending_batches),
            'completed_runs': report['completed_runs'],
            'planned_runs': report['planned_logical_runs'],
            'cost_usd': report['usage']['cost_usd'],
        }, ensure_ascii=False), flush=True)
        if not report['usage']['usage_complete']:
            raise RuntimeError('G5 paid execution stopped because provider usage is incomplete')
        if report['usage']['cost_usd'] >= contract['cost_policy']['execution_ceiling_usd']:
            raise RuntimeError('G5 paid execution stopped at the configured cost ceiling')
        if report['usage']['cost_usd'] - baseline_cost >= args.session_cost_limit_usd:
            stop_reason = 'session_cost_limit_reached'
            break

    final = progress_report(writer, plan, tasks, catalog, contract, args.experiment_id)
    final['group_results'] = group_results
    stage_audit = audit_matrix(
        writer, selected_plan, tasks, catalog,
        allow_additional=True, require_injection=True,
    )
    final.update({
        'stage': args.stage,
        'stage_planned_runs': len(selected_plan.expected),
        'stage_completed_runs': stage_audit.get('completed_runs', 0),
        'stage_complete': (stage_audit.get('ok') is True
                           and stage_audit.get('completed_runs') == len(selected_plan.expected)),
        'stage_audit': stage_audit,
        'execution_batches_planned': len(batches),
        'execution_batches_run_this_session': len(group_results),
        'session_cost_usd': final['usage']['cost_usd'] - baseline_cost,
        'session_cost_limit_usd': args.session_cost_limit_usd,
        'stop_reason': stop_reason,
    })
    path = write_progress(directory, final)
    print(json.dumps({
        'matrix_complete': final['matrix_complete'],
        'stage': args.stage,
        'stage_complete': final['stage_complete'],
        'stop_reason': stop_reason,
        'completed_runs': final['completed_runs'],
        'planned_runs': final['planned_logical_runs'],
        'cost_usd': final['usage']['cost_usd'],
        'progress': str(path),
    }, ensure_ascii=False, indent=2))
    if stop_reason is not None:
        return 0
    return 0 if final['stage_complete'] and final['within_cost_ceiling'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
