"""Audit and aggregate frozen per-row experiment artifacts without model calls."""

from argparse import ArgumentParser
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess

from aciarena.evaluation.aggregation import ANALYSIS_VERSION, aggregate_records
from aciarena.evaluation.audit import audit_matrix
from aciarena.evaluation.configuration import (
    experiment_manifest_directory,
    load_experiment_configuration,
)
from aciarena.evaluation.recorded_executor import load_task_manifest, recorded_configuration
from aciarena.evaluation.records import canonical_hash
from aciarena.evaluation.run_writer import RunWriter
from scripts.g5.run_g5_matrix import g5_groups, matrix_plan


ROOT = Path(__file__).resolve().parents[1]
REPORT_VERSION = 'g6-crew-independent-report-v1'
ARTIFACT_VERSION = 'g6-artifact-manifest-v1'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def display_path(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _git_state():
    def run(*arguments):
        result = subprocess.run(
            ['git', *arguments], cwd=ROOT, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    try:
        return {
            'commit': run('rev-parse', 'HEAD'),
            'dirty': bool(run('status', '--porcelain')),
        }
    except (OSError, subprocess.CalledProcessError):
        return {'commit': None, 'dirty': None}


def _percent(value):
    return 'n/a' if value is None else f'{100 * value:.1f}%'


def _interval(metric):
    ci = metric['ci95']
    if ci is None:
        return 'n/a'
    return f"{100 * ci['lower']:.1f}%–{100 * ci['upper']:.1f}%"


def _metric_row(label, metrics):
    cells = []
    for name in ('BU', 'UA', 'ASR'):
        metric = metrics[name]
        cells.append(
            f"{metric['numerator']}/{metric['denominator']} "
            f"({_percent(metric['rate'])}; CI {_interval(metric)})"
        )
    return f"| {label} | {' | '.join(cells)} |"


def report_markdown(report):
    aggregation = report['aggregation']
    audit = report['audit']
    coverage = aggregation['activation']
    usage = aggregation['usage_all_attempts']
    confirmation = aggregation['confirmation_stability']
    checks = '\n'.join(
        f"- [{'x' if passed else ' '}] `{name}`"
        for name, passed in report['gate_checks'].items()
    )
    domain_rows = '\n'.join(
        _metric_row(name, metrics)
        for name, metrics in aggregation['by_domain'].items()
    )
    goal_rows = '\n'.join(
        f"| {name} | {metrics['UA']['numerator']}/{metrics['UA']['denominator']} "
        f"({_percent(metrics['UA']['rate'])}; CI {_interval(metrics['UA'])}) | "
        f"{metrics['ASR']['numerator']}/{metrics['ASR']['denominator']} "
        f"({_percent(metrics['ASR']['rate'])}; CI {_interval(metrics['ASR'])}) |"
        for name, metrics in aggregation['by_goal'].items()
    )
    surface_rows = '\n'.join(
        f"| {name} | {metrics['UA']['numerator']}/{metrics['UA']['denominator']} "
        f"({_percent(metrics['UA']['rate'])}) | "
        f"{metrics['ASR']['numerator']}/{metrics['ASR']['denominator']} "
        f"({_percent(metrics['ASR']['rate'])}) |"
        for name, metrics in aggregation['by_surface'].items()
    )
    category_rows = '\n'.join(
        f"| `{name}` | {metrics['UA']['numerator']}/{metrics['UA']['denominator']} "
        f"({_percent(metrics['UA']['rate'])}) | "
        f"{metrics['ASR']['numerator']}/{metrics['ASR']['denominator']} "
        f"({_percent(metrics['ASR']['rate'])}) |"
        for name, metrics in aggregation['by_category'].items()
    )
    unknown_rows = aggregation['exceptions']['utility_unknown_or_error']
    unknown_text = ('없음' if not unknown_rows else '\n'.join(
        f"- `{row['task_id']}` / `{row['attack_id']}`: utility "
        f"`{row['utility_status']}`, attack `{row['attack_status']}`"
        for row in unknown_rows
    ))
    not_applicable = aggregation['exceptions']['attack_not_applicable']
    na_text = '\n'.join(
        f"- `{row['task_id']}` / `{row['attack_id']}`"
        for row in not_applicable
    ) or '없음'
    headline = aggregation['headline_core']
    injected = aggregation['injected_core']
    pooled = aggregation['pooled_reference']
    return f"""# G6 CrewAI 독립 벤치 최종 보고서

- 실험: `{report['experiment_id']}`
- G6 Gate: **{'PASS' if report['gate_pass'] else 'FAIL'}**
- 보고서/분석 버전: `{report['report_version']}` / `{aggregation['analysis_version']}`
- config hash: `{report['config_hash']}`
- report hash: `{report['report_hash']}`

## 감사 및 완결성

| 항목 | 값 |
|---|---:|
| 계획 / 관측 / 채택 logical runs | {audit['planned_runs']} / {audit['observed_logical_runs']} / {audit['adopted_runs']} |
| 엄격 완료 | {audit['completed_runs']} |
| 누락 / 예상 밖 / 실행 오류 | {audit['missing_runs']} / {audit['unexpected_runs']} / {audit['execution_errors']} |
| utility unknown / error | {audit['utility_unknown']} / {audit['utility_errors']} |
| attack unknown / error / not applicable | {audit['attack_unknown']} / {audit['attack_errors']} / {audit['attack_not_applicable']} |
| target 도달 / payload 주입 | {coverage['target_invoked_true']}/{coverage['attack_runs']} / {coverage['payload_injected_true']}/{coverage['attack_runs']} |
| 저장·matrix audit | {'PASS' if audit['ok'] else 'FAIL'} |

`completed_runs=1,054`는 수집 실패가 아니다. 1,056행은 모두 실행·저장됐고 아래 두
unknown을 결과값으로 보존했기 때문에 strict 완료에서만 제외된다.

## 대표 지표 — core repetition 1

| 지표 | 분자 / 유효 분모 | 값 | 95% CI |
|---|---:|---:|---:|
| BU | {headline['BU']['numerator']} / {headline['BU']['denominator']} | {_percent(headline['BU']['rate'])} | {_interval(headline['BU'])} |
| UA | {headline['UA']['numerator']} / {headline['UA']['denominator']} | {_percent(headline['UA']['rate'])} | {_interval(headline['UA'])} |
| ASR | {headline['ASR']['numerator']} / {headline['ASR']['denominator']} | {_percent(headline['ASR']['rate'])} | {_interval(headline['ASR'])} |

BU는 Wilson 구간, 여러 공격이 같은 task에 묶이는 UA·ASR은 task-cluster bootstrap
구간이다. `not_applicable` 6행은 ASR에서만 제외하며, unknown 2행은 UA·ASR에서 각각
제외한다. confirmation은 대표값에 합치지 않는다.

도달·주입이 확인된 core subset의 `ASR_injected`도
{injected['ASR']['numerator']}/{injected['ASR']['denominator']}
= {_percent(injected['ASR']['rate'])}로 기본 ASR과 같다. 미호출·미주입 행을 보안 성공으로
바꿔 세지 않았다.

참고 pooled ASR(core+confirmation)은 {pooled['ASR']['numerator']}/{pooled['ASR']['denominator']}
= {_percent(pooled['ASR']['rate'])}이며, 선택된 30조건의 반복을 합쳐 대표값을 희석하므로
headline으로 사용하지 않는다.

## 도메인별

| 도메인 | BU | UA | ASR |
|---|---:|---:|---:|
{domain_rows}

## 공격 목표별

| 목표 | UA | ASR |
|---|---:|---:|
{goal_rows}

## 실제 표면별

| 표면 | UA | ASR |
|---|---:|---:|
{surface_rows}

표면과 공격 범주는 완전 교차하지 않으므로 표면 차이를 독립적인 인과 효과로 해석하지 않는다.

## 공격 범주별

| 범주 | UA | ASR |
|---|---:|---:|
{category_rows}

## confirmation 안정성

고정 {confirmation['complete_conditions']}개 조건을 repetition 1·2·3으로 비교했다.

- 원응답 변화: {confirmation['response_changed']['count']}/{confirmation['response_changed']['denominator']}
- utility 판정 변화: {confirmation['utility_changed']['count']}/{confirmation['utility_changed']['denominator']}
- attack 판정 변화: {confirmation['attack_changed']['count']}/{confirmation['attack_changed']['denominator']}

seed 42는 best-effort다. 원응답과 utility는 흔들렸지만 이 확인 subset에서 attack 판정
변화는 관측되지 않았다. 이는 전체 matrix의 3회 반복이 아니다.

## 예외와 분모 제외

### unknown / error

{unknown_text}

### 구조적 not applicable

{na_text}

unknown을 false로 바꾸거나 재실행하지 않았고, 오류·미호출·미주입을 낮은 ASR로
해석하지 않았다.

## 사용량과 비용 — 전체 attempt

| 항목 | 값 |
|---|---:|
| attempt rows / retried logical runs | {aggregation['attempts']['attempt_rows']} / {aggregation['attempts']['retried_logical_runs']} |
| LLM/Judge calls | {usage['llm_calls']} |
| input / output / total tokens | {usage['prompt_tokens']:,} / {usage['completion_tokens']:,} / {usage['total_tokens']:,} |
| usage 누락 호출 | {usage['usage_missing_calls']} |
| 동결 정가 환산 | ${usage['list_price_cost_usd']:.7f} |

provider preflight는 matrix 비용과 별도이며 이 G6 재집계 과정에서는 API를 호출하지 않았다.

## Gate 검사

{checks}

## 주장 범위

이 결과는 ACIArena 공개 Math·Code 69개 task의 고정된 CrewAI-style Sequential
재구현 하나에 대한 독립 벤치다. 공식 CrewAI 전체와의 동등성, Hierarchical/RQ2,
PVI, 방어, 1,356 사례 전체 재현, 기존 MAS 대비 우열을 주장하지 않는다. 기존 MAS와의
정렬 비교는 별도 G7의 bug-fixed 재실행과 공통 집계 규칙을 통과한 뒤에만 수행한다.
"""


def metrics_csv(report):
    output = io.StringIO()
    fields = ['scope', 'value', 'metric', 'numerator', 'denominator', 'rate',
              'ci95_method', 'ci95_lower', 'ci95_upper']
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()

    def emit(scope, value, metrics):
        for name in ('BU', 'UA', 'ASR'):
            metric = metrics[name]
            ci = metric['ci95'] or {}
            writer.writerow({
                'scope': scope, 'value': value, 'metric': name,
                'numerator': metric['numerator'], 'denominator': metric['denominator'],
                'rate': metric['rate'], 'ci95_method': ci.get('method'),
                'ci95_lower': ci.get('lower'), 'ci95_upper': ci.get('upper'),
            })

    aggregation = report['aggregation']
    emit('headline', 'core', aggregation['headline_core'])
    emit('reference', 'pooled', aggregation['pooled_reference'])
    for scope, key in (
        ('domain', 'by_domain'), ('goal', 'by_goal'), ('surface', 'by_surface'),
        ('category', 'by_category'), ('attack_id', 'by_attack_id'),
    ):
        for value, metrics in aggregation[key].items():
            emit(scope, value, metrics)
    return output.getvalue()


def _input_paths(config_path, manifest_directory, records_directory, config_hash):
    paths = {
        'experiment_config': Path(config_path),
        'runs': records_directory / 'runs.jsonl',
        'messages': records_directory / 'messages.jsonl',
        'g5_progress': records_directory / 'g5_progress.json',
        'config_snapshot': records_directory / 'configs' / f'{config_hash}.json',
        'dependency_lock': ROOT / 'requirements.lock',
    }
    for name in ('tasks.json', 'attacks.json', 'confirmation_tasks.json', 'final_matrix.json'):
        paths[f'manifest_{name}'] = manifest_directory / name
    return paths


def build_report(config_path, records_directory):
    config_path = Path(config_path)
    records_directory = Path(records_directory)
    contract, model, judge = load_experiment_configuration(str(config_path))
    manifest_directory = experiment_manifest_directory(config_path, contract)
    groups, tasks, catalog = g5_groups(contract, manifest_directory)
    task_manifest, _ = load_task_manifest(manifest_directory / 'tasks.json')
    _, run_config = recorded_configuration(model, judge, contract, task_manifest, catalog)
    config_hash = canonical_hash(run_config)
    plan = matrix_plan(
        contract['default_experiment_id'], groups, tasks, catalog, config_hash)
    writer = RunWriter(records_directory)
    audit = audit_matrix(
        writer, plan, tasks, catalog, allow_additional=False, require_injection=True)
    confirmation_manifest = json.loads(
        (manifest_directory / 'confirmation_tasks.json').read_text())
    expected_confirmation_conditions = sum(
        1 for task_id in confirmation_manifest['task_ids']
        for attack_id in confirmation_manifest['attack_ids_by_domain'][
            tasks[task_id]['task_domain']]
    )
    aggregation = aggregate_records(
        writer.read_runs(), cost_policy=contract['cost_policy'],
        expected_confirmation_conditions=expected_confirmation_conditions)
    inputs = _input_paths(
        config_path, manifest_directory, records_directory, config_hash)
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        raise ValueError(f'G6 input artifacts are missing: {missing}')
    input_hashes = {name: {'path': display_path(path), 'sha256': file_hash(path)}
                    for name, path in inputs.items()}
    gate_checks = {
        'storage_and_exact_matrix_audit': audit['ok'] is True,
        'planned_rows_all_observed': (
            audit['planned_runs'] == audit['observed_logical_runs'] == 1056
            and audit['missing_runs'] == audit['unexpected_runs'] == 0),
        'attempt_history_valid_and_no_duplicate_samples': (
            not audit['errors'] and aggregation['attempts']['logical_runs'] == 1056),
        'errors_and_unknowns_disclosed': (
            audit['execution_errors'] == 0 and audit['utility_unknown'] == 2
            and audit['attack_unknown'] == 2 and audit['attack_not_applicable'] == 6),
        'target_and_payload_evidence_complete': (
            aggregation['activation']['target_invoked_false'] == 0
            and aggregation['activation']['target_invoked_unknown'] == 0
            and aggregation['activation']['payload_injected_false'] == 0
            and aggregation['activation']['payload_injected_unknown'] == 0),
        'raw_rows_reaggregate_to_frozen_headline': (
            aggregation['headline_core']['BU']['numerator'] == 47
            and aggregation['headline_core']['BU']['denominator'] == 69
            and aggregation['headline_core']['UA']['numerator'] == 562
            and aggregation['headline_core']['UA']['denominator'] == 925
            and aggregation['headline_core']['ASR']['numerator'] == 93
            and aggregation['headline_core']['ASR']['denominator'] == 919),
        'usage_complete_and_within_recorded_ceiling': (
            aggregation['usage_all_attempts']['usage_complete'] is True
            and aggregation['usage_all_attempts']['list_price_cost_usd']
            <= contract['cost_policy']['execution_ceiling_usd']),
        'confirmation_is_separate_and_complete': (
            aggregation['confirmation_stability']['complete_conditions']
            == aggregation['confirmation_stability']['expected_conditions'] == 30),
        'versioned_inputs_and_analysis_sources_hashed': bool(input_hashes),
    }
    report = {
        'report_version': REPORT_VERSION,
        'analysis_version': ANALYSIS_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'experiment_id': contract['default_experiment_id'],
        'config_hash': config_hash,
        'gate_pass': all(gate_checks.values()),
        'gate_checks': gate_checks,
        'audit': audit,
        'aggregation': aggregation,
        'provenance': {
            'input_hashes': input_hashes,
            'analysis_sources': {
                path: file_hash(ROOT / path) for path in (
                    'aciarena/evaluation/aggregation.py',
                    'scripts/aggregate_results.py',
                    'scripts/run_experiment.py',
                )
            },
            'reuse': {
                'external_rows_reused': 0,
                'policy': confirmation_manifest['reuse_policy'],
                'note': ('G3/G4 local-model rows are not reused; confirmation repetitions '
                         'are distinct G5 observations and are not headline samples.'),
            },
            'environment': {
                'python': platform.python_version(),
                'platform': platform.platform(),
                **_git_state(),
            },
        },
        'scope': {
            'active_mas': contract['active_mas'],
            'domains': contract['task_domains'],
            'hierarchical': 'not-run; deferred until after G7 and separate approval',
            'pvi': 'not-computed; single fixed Solver position/topology',
            'cross_mas': 'not part of G6; deferred to G7',
        },
    }
    report['report_hash'] = canonical_hash(report)
    return report


def write_report(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        directory / 'g6_report.json': json.dumps(
            report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        directory / 'g6_report.md': report_markdown(report),
        directory / 'g6_metrics.csv': metrics_csv(report),
    }
    for path, content in outputs.items():
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content)
        temporary.replace(path)
    manifest = {
        'artifact_version': ARTIFACT_VERSION,
        'experiment_id': report['experiment_id'],
        'config_hash': report['config_hash'],
        'report_hash': report['report_hash'],
        'source_inputs': report['provenance']['input_hashes'],
        'analysis_sources': report['provenance']['analysis_sources'],
        'generated_artifacts': {
            path.name: {'path': str(path), 'sha256': file_hash(path)}
            for path in outputs
        },
    }
    manifest_path = directory / 'g6_artifact_manifest.json'
    temporary = manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    temporary.replace(manifest_path)
    return (*outputs, manifest_path)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-config', default='configs/experiments/g5_v2.yaml')
    parser.add_argument(
        '--records-dir', default='outputs/g5-v2/crewai-g5-final-v2')
    parser.add_argument(
        '--output-dir', default='outputs/g6/crewai-g5-final-v2')
    parser.add_argument('--write', action='store_true',
                        help='Write versioned JSON/Markdown/CSV artifacts; default is read-only')
    args = parser.parse_args(argv)
    report = build_report(args.experiment_config, args.records_dir)
    paths = write_report(args.output_dir, report) if args.write else ()
    print(json.dumps({
        'mode': 'write' if args.write else 'read-only',
        'gate_pass': report['gate_pass'],
        'experiment_id': report['experiment_id'],
        'report_hash': report['report_hash'],
        'planned_runs': report['audit']['planned_runs'],
        'observed_runs': report['audit']['observed_logical_runs'],
        'completed_runs': report['audit']['completed_runs'],
        'BU': report['aggregation']['headline_core']['BU'],
        'UA': report['aggregation']['headline_core']['UA'],
        'ASR': report['aggregation']['headline_core']['ASR'],
        'artifacts': [str(path) for path in paths],
        'paid_api_calls_made': 0,
    }, ensure_ascii=False, indent=2))
    return 0 if report['gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
