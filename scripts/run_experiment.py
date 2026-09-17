"""Unified manifest-driven CrewAI experiment orchestrator (dry-run by default).

This entry point unifies deterministic matrix expansion, config-hash-aware
resume, execution, and terminal audit.  It intentionally contains no provider
preflight or monetary stop loop; ``--execute`` is the sole execution opt-in.
Historical G4/G5 drivers remain available only to reproduce their frozen
artifacts.
"""

from argparse import ArgumentParser, Namespace
import json
from pathlib import Path

from dotenv import load_dotenv

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import MatrixPlan, audit_matrix, build_matrix_plan
from aciarena.evaluation.configuration import (
    experiment_manifest_directory,
    load_experiment_configuration,
)
from aciarena.evaluation.pilot import (
    build_g4_report,
    pilot_groups,
    pilot_manifest,
    write_g4_report,
)
from aciarena.evaluation.recorded_executor import load_task_manifest, recorded_configuration
from aciarena.evaluation.recorded_suite import RecordedEvaluationSuite
from aciarena.evaluation.records import canonical_hash
from aciarena.evaluation.run_writer import RunWriter
from scripts.g5.run_g5_matrix import g5_groups, stage_groups, usage_cost


ROOT = Path(__file__).resolve().parents[1]
STAGES = ('all', 'core', 'confirmation', 'pilot')
MATRICES = ('all', 'benign', 'attacks', 'smoke')
SUITES = ('all', 'benign', 'disclosure', 'disruption', 'hijacking')


def _development_groups(tasks, catalog):
    return [
        {**group, 'phase': 'pilot', 'repetition': 1}
        for group in pilot_groups(tasks, catalog, pilot_manifest())
    ]


def _plan(experiment_id, groups, tasks, catalog, config_hash):
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
            raise ValueError('Selected groups contain duplicate logical runs')
        expected.update(plan.expected)
    if not expected:
        raise ValueError('Experiment selection contains no logical runs')
    return MatrixPlan(frozenset(expected))


def select_groups(groups, *, stage, matrix, domain, suite, attack_ids,
                  final_contract):
    selected = list(groups)
    if matrix == 'smoke':
        if not final_contract:
            raise ValueError('The smoke view is defined only for a final matrix')
        selected = stage_groups(groups, 'smoke')
    elif matrix == 'benign':
        selected = [group for group in selected if group['suite'] == 'benign']
    elif matrix == 'attacks':
        selected = [group for group in selected if group['suite'] != 'benign']

    if stage != 'all':
        selected = [group for group in selected if group['phase'] == stage]
    if domain != 'all':
        selected = [group for group in selected if group['task_domain'] == domain]
    if attack_ids is None:
        if suite != 'all':
            selected = [group for group in selected if group['suite'] == suite]
    else:
        requested = set(attack_ids)
        filtered = []
        observed = set()
        for group in selected:
            attacks = [attack_id for attack_id in group['attack_ids']
                       if attack_id in requested]
            if attacks:
                observed.update(attacks)
                filtered.append({**group, 'attack_ids': attacks})
        missing = requested - observed
        if missing:
            raise ValueError(
                'Requested attack IDs are outside the selected manifest view: '
                + ', '.join(sorted(missing)))
        selected = filtered
    return selected


def suite_args(cli, group):
    return Namespace(
        attack_ids=group['attack_ids'],
        experiment_id=cli.experiment_id,
        experiment_config=cli.experiment_config,
        phase=group['phase'],
        repetition=group['repetition'],
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


def _summarize_groups(groups):
    return [{
        'phase': group['phase'],
        'repetition': group['repetition'],
        'task_domain': group['task_domain'],
        'suite': group['suite'],
        'tasks': len(group['task_ids']),
        'attack_ids': group['attack_ids'],
        'logical_runs': len(group['task_ids']) * len(group['attack_ids']),
    } for group in groups]


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--config', '--experiment-config', dest='experiment_config',
                        default='configs/experiments/g5_v2.yaml')
    parser.add_argument('--experiment-id')
    parser.add_argument('--output-dir', default='outputs/experiments')
    parser.add_argument('--stage', choices=STAGES, default='all')
    parser.add_argument('--matrix', choices=MATRICES, default='all')
    parser.add_argument('--domain', choices=('all', 'math', 'code'), default='all')
    parser.add_argument('--suite', choices=SUITES, default='all')
    parser.add_argument('--attack-ids', nargs='+')
    parser.add_argument('--report', choices=('gate', 'progress'))
    parser.add_argument('--max-workers', type=int, default=4)
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--execute', action='store_true',
                        help='Permit model calls; omitted means a zero-call dry-run')
    args = parser.parse_args(argv)
    if args.max_workers < 1:
        parser.error('--max-workers must be positive')
    if args.attack_ids and args.suite != 'all':
        parser.error('--attack-ids and a non-all --suite cannot be combined')

    contract, model, judge = load_experiment_configuration(args.experiment_config)
    final_contract = contract['stage'] == 'final'
    report_mode = args.report or ('progress' if final_contract else 'gate')
    if report_mode == 'gate' and final_contract:
        parser.error('--report gate requires a development/pilot contract')
    if report_mode == 'progress' and not final_contract:
        parser.error('--report progress requires a final matrix contract')
    if args.stage == 'pilot' and final_contract:
        parser.error('--stage pilot is absent from the final matrix')
    if args.stage in {'core', 'confirmation'} and not final_contract:
        parser.error('development gate runs use --stage pilot or all')

    args.experiment_id = args.experiment_id or contract['default_experiment_id']
    manifest_directory = experiment_manifest_directory(args.experiment_config, contract)
    if final_contract:
        groups, tasks, catalog = g5_groups(contract, manifest_directory)
    else:
        _, tasks = load_task_manifest(manifest_directory / 'tasks.json')
        catalog = AttackCatalog(manifest_directory / 'attacks.json')
        groups = _development_groups(tasks, catalog)
    selected = select_groups(
        groups,
        stage=args.stage,
        matrix=args.matrix,
        domain=args.domain,
        suite=args.suite,
        attack_ids=args.attack_ids,
        final_contract=final_contract,
    )
    task_manifest, _ = load_task_manifest(manifest_directory / 'tasks.json')
    _, run_config = recorded_configuration(model, judge, contract, task_manifest, catalog)
    config_hash = canonical_hash(run_config)
    plan = _plan(args.experiment_id, selected, tasks, catalog, config_hash)
    directory = Path(args.output_dir) / args.experiment_id

    if not args.execute:
        print(json.dumps({
            'mode': 'dry-run',
            'paid_api_calls_made': 0,
            'experiment_id': args.experiment_id,
            'contract_id': contract['contract_id'],
            'config_hash': config_hash,
            'report': report_mode,
            'stage': args.stage,
            'matrix': args.matrix,
            'domain': args.domain,
            'suite': args.suite,
            'logical_runs': len(plan.expected),
            'groups': _summarize_groups(selected),
            'execution_note': (
                '--execute enables calls; this unified runner has no provider-preflight, '
                'cost-ceiling, session-stop, or full-matrix opt-in gate.'),
        }, ensure_ascii=False, indent=2))
        return 0

    load_dotenv(ROOT / '.env')
    results = []
    for group in selected:
        result = RecordedEvaluationSuite(suite_args(args, group)).eval()
        results.append({**group, 'result': result})

    writer = RunWriter(directory)
    if report_mode == 'gate':
        if (args.stage not in {'all', 'pilot'} or args.matrix != 'all'
                or args.domain != 'all' or args.suite != 'all'
                or args.attack_ids is not None):
            parser.error('A gate report requires the complete predeclared pilot')
        report = build_g4_report(
            writer, experiment_id=args.experiment_id, tasks=tasks, catalog=catalog)
        paths = write_g4_report(directory, report)
        output = {
            'mode': 'execute', 'report': report_mode,
            'gate_pass': report['gate_pass'],
            'logical_runs': len(plan.expected),
            'reports': [str(path) for path in paths],
            'group_results': results,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if report['gate_pass'] else 1

    audit = audit_matrix(
        writer, plan, tasks, catalog, allow_additional=True, require_injection=True)
    usage = usage_cost(writer.read_runs(), contract['cost_policy'])
    output = {
        'mode': 'execute',
        'report': report_mode,
        'experiment_id': args.experiment_id,
        'logical_runs': len(plan.expected),
        'audit': audit,
        'usage_observed_without_cost_gate': usage,
        'group_results': results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if audit['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
