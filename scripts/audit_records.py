"""Audit a recorded CrewAI experiment against a predeclared manifest matrix."""

import argparse
import json
from pathlib import Path

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import audit_matrix, build_manifest_plan
from aciarena.evaluation.recorded_executor import load_task_manifest
from aciarena.evaluation.run_writer import RunWriter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment_id', required=True)
    parser.add_argument('--output_dir', default='logs')
    parser.add_argument('--matrix', required=True,
                        choices=['benign', 'core-attacks', 'pilot', 'confirmation'])
    parser.add_argument('--allow_additional', action='store_true')
    args = parser.parse_args()

    directory = Path(args.output_dir) / args.experiment_id
    if not directory.is_dir():
        parser.error(f'Recorded experiment directory does not exist: {directory}')
    _, tasks = load_task_manifest()
    catalog = AttackCatalog()
    plan = build_manifest_plan(
        args.matrix,
        experiment_id=args.experiment_id,
        tasks=tasks,
        catalog=catalog,
    )
    report = audit_matrix(
        RunWriter(directory),
        plan,
        tasks,
        catalog,
        allow_additional=args.allow_additional,
        require_injection=args.matrix != 'benign',
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
