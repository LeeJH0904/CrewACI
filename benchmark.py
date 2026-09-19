from aciarena.utils import build_suite
from aciarena.evaluation.g7_suite import G7LegacyEvaluationSuite
from aciarena.evaluation.g7_manifest import G7Manifest, G7ManifestError
from dotenv import load_dotenv
import argparse
import copy
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import yaml

load_dotenv()

G7_LEGACY_SYSTEMS = {
    'metagpt', 'autogen', 'camel', 'sc', 'llm_debate', 'agentverse',
}
ROOT = Path(__file__).resolve().parent


def _yaml(path):
    with open(path, 'r') as stream:
        return yaml.safe_load(stream)


def _validate_g7_destination(args):
    experiment_id = args.experiment_id or 'g7-cross-mas-v1'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', experiment_id):
        raise ValueError('experiment_id must be a simple directory-safe identifier')
    output_root = Path(args.output_dir).resolve()
    frozen_roots = (
        (ROOT / 'outputs/g5-v2').resolve(),
        (ROOT / 'outputs/g6').resolve(),
    )
    if any(output_root == frozen or output_root.is_relative_to(frozen)
           for frozen in frozen_roots):
        raise ValueError('G7 output cannot be written under frozen G5-v2/G6 paths')


def _crewai_g7_args(args, manifest):
    prepared = copy.deepcopy(args)
    prepared.experiment_id = args.experiment_id or 'g7-cross-mas-v1'
    requested_targets = list(getattr(args, 'malicious_agents', []))
    expected_target = None if args.suite == 'benign' else manifest.target(
        args.mas, args.task_domain, args.suite)
    if requested_targets and requested_targets != [expected_target]:
        raise G7ManifestError(
            f'CrewAI G7 target is fixed to {expected_target!r}')
    prepared.malicious_agents = [] if expected_target is None else [expected_target]
    available = (('none',) if args.suite == 'benign'
                 else manifest.attack_ids(args.task_domain, args.suite))
    requested_attacks = getattr(args, 'attack_ids', None)
    if requested_attacks:
        if len(requested_attacks) != len(set(requested_attacks)):
            raise ValueError('--attack_ids must be unique')
        unknown = sorted(set(requested_attacks) - set(available))
        if unknown:
            raise G7ManifestError(
                'Attack IDs are outside the selected goal/domain: '
                + ', '.join(unknown))
        available = tuple(requested_attacks)
    prepared.attack_ids = list(available)
    return prepared


def _crewai_g7_dry_run(args, manifest):
    all_task_ids = list(manifest.task_ids(args.task_domain))
    requested = getattr(args, 'task_ids', None)
    limit = getattr(args, 'limit', None)
    if requested and limit is not None:
        raise ValueError('--task_ids and --limit cannot be combined')
    if requested:
        if len(requested) != len(set(requested)):
            raise ValueError('--task_ids must be unique')
        unknown = sorted(set(requested) - set(all_task_ids))
        if unknown:
            raise G7ManifestError(
                'Tasks are absent from the selected domain: ' + ', '.join(unknown))
        task_ids = list(requested)
    else:
        if limit is not None and limit < 1:
            raise ValueError('--limit must be positive')
        task_ids = all_task_ids[:limit]
    return {
        'mode': 'dry-run',
        'paid_api_calls_made': 0,
        'experiment_id': args.experiment_id,
        'mas_id': args.mas,
        'task_domain': args.task_domain,
        'suite': args.suite,
        'target_agent': (args.malicious_agents[0]
                         if args.malicious_agents else None),
        'task_ids': task_ids,
        'attack_ids': list(args.attack_ids),
        'logical_runs': len(task_ids) * len(args.attack_ids),
        'records_dir': str(
            (Path(args.output_dir) / args.experiment_id).resolve()),
    }

def main(args):
    if args.mas.lower() == 'crewai_seq_nodeleg' or args.mas.lower() in G7_LEGACY_SYSTEMS:
        _validate_g7_destination(args)
    if args.mas.lower() == 'crewai_seq_nodeleg':
        manifest = G7Manifest()
        prepared = _crewai_g7_args(args, manifest)
        if not args.execute:
            result = _crewai_g7_dry_run(prepared, manifest)
            print('Evaluation Plan:', json.dumps(result, ensure_ascii=False))
            return result
        suite = build_suite(prepared)
        result = suite.eval()
        print('Evaluation Results:', json.dumps(result, ensure_ascii=False))
        return result
    if args.mas.lower() in G7_LEGACY_SYSTEMS:
        model_path = args.model_config or 'configs/g5_model.yaml'
        judge_path = args.judge_config or 'configs/g5_judge.yaml'
        dry_writer = None
        if not args.execute:
            experiment_id = args.experiment_id or 'g7-cross-mas-v1'
            dry_writer = SimpleNamespace(
                directory=(Path(args.output_dir) / experiment_id).resolve())
        suite = G7LegacyEvaluationSuite(
            args, _yaml(model_path), _yaml(judge_path), writer=dry_writer)
        result = suite.dry_run() if not args.execute else suite.eval()
        print('Evaluation Plan:' if not args.execute else 'Evaluation Results:',
              json.dumps(result, ensure_ascii=False))
        return result

    if not args.execute:
        result = {
            'mode': 'dry-run', 'paid_api_calls_made': 0, 'mas_id': args.mas,
            'note': 'This MAS is outside the G7 paper-six comparison scope.',
        }
        print('Evaluation Plan:', json.dumps(result, ensure_ascii=False))
        return result
    model_config = yaml.safe_load(open("configs/model.yaml"))
    model_name = model_config.get("model_name", "unknown").replace("/", "_")

    save_dir = f"logs/{model_name}/{args.task_domain}/{args.mas}/{args.suite}"
    os.makedirs(save_dir, exist_ok=True)

    suite = build_suite(args)
    result = suite.eval()
    print("Evaluation Results:", result)

    save_path = os.path.join(save_dir, "result.json")

    # 如果文件已存在，先加载内容
    if os.path.exists(save_path):
        with open(save_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []  # 如果文件损坏/为空，初始化为空列表
    else:
        data = []

    # 追加新的结果
    data.append({
        "meta_data": vars(args),
        "result": result
    })

    # 写回文件
    with open(save_path, "w") as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="aciarena Configuration")
    parser.add_argument('--attack_ids', nargs='+', help='Explicit manifest attack IDs for recorded CrewAI runs')
    parser.add_argument('--experiment_id', default=None)
    parser.add_argument('--experiment_config', default='configs/experiments/g5_v2.yaml')
    parser.add_argument('--phase', choices=['calibration', 'pilot', 'core', 'confirmation'], default='core')
    parser.add_argument('--repetition', type=int, default=1)
    parser.add_argument('--resume', action='store_true', help='Reuse completed records, including valid false outcomes')
    parser.add_argument('--retry_errors', action='store_true', help='Retry recorded transient provider failures, at most 3 attempts')
    parser.add_argument('--execute', action='store_true', help='Permit model calls; omitted means a zero-call dry-run')
    parser.add_argument('--model_config', default=None, help='Legacy non-CrewAI model configuration override')
    parser.add_argument('--judge_config', default=None, help='Legacy non-CrewAI Judge configuration override')
    parser.add_argument(
        "--mas",
        type=str,
        default="autogen",
        help="The structure of the multi-agent system. Options typically include 'linear', 'tree', or custom topologies."
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="hijacking",
        help="Specifies the evaluation suite."
    )
    parser.add_argument(
        "--attack_mode",
        type=str,
        default="continuous",
        help="Specifies how the attack is executed."
    )
    parser.add_argument(
        "--defense",
        type=str,
        default="none",
        help="Specifies the defense."
    )
    parser.add_argument(
        "--task_domain",
        type=str,
        default="code",
        help="Benign task domain."
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=1,
        help="The max workers for evaluation."
    )
    parser.add_argument(
    "--limit",
    type=int,
    default=None,
    help="Limit the number of evaluation tasks for testing."
    )
    parser.add_argument(
        "--task_ids",
        nargs='+',
        default=None,
        help="Run exact manifest task IDs; cannot be combined with --limit."
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="outputs/g7",
        help="Directory to save output files such as logs, results, or checkpoints."
    )
    parser.add_argument(
        "--malicious_agents",
        nargs='+',
        type=str,
        default=[],
        help="A list of agent names to target in the attack (e.g., 'agent_1', 'agent_2'). You can specify multiple agents separated by space."
    )
    args = parser.parse_args()
    main(args)
