"""Run one side of the G3 calibration in its isolated Python environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .calibration_contract import (
    CalibrationStore,
    load_calibration_tasks,
    load_model_config,
    validate_experiment_id,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementation", choices=("reconstructed", "native"), required=True)
    parser.add_argument("--experiment_id", default="g3-sequential-calibration-v3")
    parser.add_argument("--output_dir", default="outputs/g3")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    experiment_id = validate_experiment_id(args.experiment_id)
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be positive")
    load_dotenv()
    tasks = load_calibration_tasks()
    if args.limit is not None:
        tasks = tasks[:args.limit]
    model_config = load_model_config()
    directory = Path(args.output_dir) / experiment_id
    store = CalibrationStore(directory, args.implementation)
    completed = {row["task_id"] for row in store.read()
                 if row["experiment_id"] == experiment_id}
    pending = [task for task in tasks if task["task_id"] not in completed]
    if completed and not args.resume and pending:
        raise ValueError("Existing calibration rows require --resume")
    if args.dry_run:
        print(json.dumps({
            "experiment_id": experiment_id,
            "implementation": args.implementation,
            "selected": [task["task_id"] for task in tasks],
            "completed": sorted(completed),
            "pending": [task["task_id"] for task in pending],
            "records": str(store.path),
        }, ensure_ascii=False, indent=2))
        return

    if args.implementation == "reconstructed":
        from .reconstructed_adapter import run_reconstructed as runner
    else:
        from .crew_factory import run_native as runner

    successes = 0
    for index, task in enumerate(pending, 1):
        print(f"[{index}/{len(pending)}] {args.implementation}: {task['task_id']}", flush=True)
        record = runner(experiment_id=experiment_id, task=task, model_config=model_config)
        store.append(record)
        successes += record["status"] == "success"
    rows = [row for row in store.read() if row["experiment_id"] == experiment_id]
    print(json.dumps({
        "experiment_id": experiment_id,
        "implementation": args.implementation,
        "selected_runs": len(tasks),
        "new_runs": len(pending),
        "new_successes": successes,
        "recorded_runs": len(rows),
        "recorded_successes": sum(row["status"] == "success" for row in rows),
        "records": str(store.path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
