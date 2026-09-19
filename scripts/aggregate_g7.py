"""Aggregate G7 recorded rows without making model or provider calls."""

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path

from aciarena.evaluation.g7_reporting import build_g7_report, write_g7_report
from aciarena.evaluation.records import RunRecord, canonical_hash


ROOT = Path(__file__).resolve().parents[1]


DEFAULT_COST_POLICY = {
    'input_per_million_usd': 0.15,
    'output_per_million_usd': 0.60,
    'pricing_as_of': '2026-09-11-frozen-g5-contract',
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _read_runs(path):
    if not path.is_file():
        return []
    rows = []
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith(b'\n'):
                raise ValueError(f'{path}:{number}: unterminated JSONL line')
            data = json.loads(line, object_pairs_hook=_unique_object)
            rows.append(RunRecord.model_validate(data))
    return rows


def _validate_snapshot(path, expected_hash):
    data = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    if canonical_hash(data) != expected_hash:
        raise ValueError(f'Config snapshot hash mismatch: {path}')
    for group in ('sources', 'manifests'):
        entries = data.get(group, {})
        if not isinstance(entries, dict):
            raise ValueError(f'Invalid config {group}: {path}')
        for source, expected in entries.items():
            candidate = (ROOT / source).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError as exc:
                raise ValueError(f'Unsafe config source path: {source}') from exc
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f'Config {group} drift: {source}')
    dependency = hashlib.sha256((ROOT / 'requirements.lock').read_bytes()).hexdigest()
    if data.get('dependency_lock_hash') != dependency:
        raise ValueError(f'Config dependency lock drift: {path}')
    return data


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        '--records-dir', action='append',
        default=None,
        help='Directory containing runs.jsonl; repeat for multiple G7 sources')
    parser.add_argument('--output-dir', default='outputs/g7/report')
    parser.add_argument('--write', action='store_true')
    parser.add_argument(
        '--allow-partial-write', action='store_true',
        help='Explicitly permit diagnostic artifacts before the exact matrix is complete')
    args = parser.parse_args(argv)
    directories = [Path(path) for path in (
        args.records_dir or ['outputs/g7/g7-cross-mas-v1'])]
    rows = []
    inputs = []
    for directory in directories:
        directory_rows = _read_runs(directory / 'runs.jsonl')
        rows.extend(directory_rows)
        for name in ('runs.jsonl', 'messages.jsonl'):
            path = directory / name
            if path.is_file():
                inputs.append(path)
        for config_hash in sorted({row.config_hash for row in directory_rows}):
            path = directory / 'configs' / f'{config_hash}.json'
            if not path.is_file():
                raise ValueError(f'Missing config snapshot: {path}')
            _validate_snapshot(path, config_hash)
            inputs.append(path)
    report = build_g7_report(
        rows, cost_policy=DEFAULT_COST_POLICY, input_paths=inputs)
    if (args.write and not report['aggregation']['matrix_complete']
            and not args.allow_partial_write):
        raise ValueError(
            'Refusing to write an incomplete G7 report; use --allow-partial-write '
            'only for a clearly diagnostic artifact')
    paths = write_g7_report(args.output_dir, report) if args.write else ()
    print(json.dumps({
        'mode': 'write' if args.write else 'read-only',
        'report_version': report['report_version'],
        'analysis_version': report['analysis_version'],
        'matrix_complete': report['aggregation']['matrix_complete'],
        'expected_core_rows': report['aggregation']['expected_core_rows'],
        'observed_core_rows': report['aggregation']['core_rows'],
        'artifacts': [str(path) for path in paths],
        'paid_api_calls_made': 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
