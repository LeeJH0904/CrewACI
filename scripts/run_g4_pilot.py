"""Run and report the predeclared 30-run Sequential G4 pilot."""

from argparse import ArgumentParser, Namespace
import json
from pathlib import Path

from dotenv import load_dotenv

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import build_manifest_plan
from aciarena.evaluation.pilot import (
    build_g4_report,
    pilot_groups,
    pilot_manifest,
    write_g4_report,
)
from aciarena.evaluation.recorded_executor import load_task_manifest
from aciarena.evaluation.recorded_suite import RecordedEvaluationSuite
from aciarena.evaluation.run_writer import RunWriter


def suite_args(cli, group):
    return Namespace(
        attack_ids=group['attack_ids'],
        experiment_id=cli.experiment_id,
        experiment_config=cli.experiment_config,
        phase='pilot',
        repetition=1,
        resume=cli.resume,
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


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-id', default='g4-sequential-pilot-v1')
    parser.add_argument('--experiment-config', default='configs/experiments/core.yaml')
    parser.add_argument('--output-dir', default='outputs/g4')
    parser.add_argument('--max-workers', type=int, default=4)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--retry-errors', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args(argv)
    if args.dry_run and args.report_only:
        parser.error('--dry-run and --report-only cannot be combined')
    if args.max_workers < 1:
        parser.error('--max-workers must be positive')

    load_dotenv()
    _, tasks = load_task_manifest()
    catalog = AttackCatalog()
    manifest = pilot_manifest()
    groups = pilot_groups(tasks, catalog, manifest)
    plan = build_manifest_plan(
        'pilot', experiment_id=args.experiment_id, tasks=tasks, catalog=catalog)
    directory = Path(args.output_dir) / args.experiment_id

    if args.dry_run:
        payload = {
            'experiment_id': args.experiment_id,
            'model_assignment': 'bionic-local-development',
            'paid_api_budget_usd': 0,
            'planned_runs': len(plan.expected),
            'groups': groups,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    group_results = []
    if not args.report_only:
        for group in groups:
            result = RecordedEvaluationSuite(suite_args(args, group)).eval()
            group_results.append({**group, 'result': result})

    writer = RunWriter(directory)
    report = build_g4_report(
        writer, experiment_id=args.experiment_id, tasks=tasks, catalog=catalog)
    paths = write_g4_report(directory, report)
    output = {
        'gate_pass': report['gate_pass'],
        'experiment_id': args.experiment_id,
        'planned_runs': report['counts']['planned_logical_runs'],
        'completed_runs': report['counts']['completed_runs'],
        'reports': [str(path) for path in paths],
        'group_results': group_results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if report['gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
