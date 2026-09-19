"""Render versioned G7 cross-MAS JSON, Markdown, CSV, and hash manifest."""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

from .g7_aggregation import aggregate_g7
from .g7_manifest import G7Manifest
from .records import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
REPORT_VERSION = 'g7-cross-mas-report-v1'
ARTIFACT_VERSION = 'g7-cross-mas-artifact-manifest-v1'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_g7_report(rows, *, cost_policy, input_paths=None):
    manifest = G7Manifest()
    aggregation = aggregate_g7(rows, cost_policy=cost_policy, manifest=manifest)
    manifest_paths = sorted({
        *(ROOT / 'manifests/g7').glob('*.json'),
        ROOT / manifest.identifier_document['task_mapping']['source_manifest'],
        ROOT / manifest.identifier_document['attack_mapping']['source_manifest'],
    })
    report = {
        'report_version': REPORT_VERSION,
        'analysis_version': aggregation['analysis_version'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': {
            'systems': [system['mas_id'] for system in manifest.system_document['systems']],
            'math_systems': [
                system['mas_id'] for system in manifest.system_document['systems']
                if 'math' in system['domains']],
            'code_systems': [
                system['mas_id'] for system in manifest.system_document['systems']
                if 'code' in system['domains']],
            'mad': 'excluded',
            'framing': 'CrewAI position plus design attribution; no safety ranking',
        },
        'aggregation': aggregation,
        'provenance': {
            'input_hashes': {
                str(Path(path)): file_hash(path) for path in (input_paths or [])
            },
            'manifest_hashes': {
                str(path.relative_to(ROOT)): file_hash(path)
                for path in manifest_paths
            },
            'dependency_lock_hash': file_hash(ROOT / 'requirements.lock'),
            'analysis_sources': {
                path: file_hash(ROOT / path) for path in (
                    'aciarena/evaluation/aggregation.py',
                    'aciarena/evaluation/g7_aggregation.py',
                    'aciarena/evaluation/g7_manifest.py',
                    'aciarena/evaluation/g7_reporting.py',
                    'aciarena/evaluation/records.py',
                    'scripts/aggregate_g7.py',
                )
            },
        },
        'paid_api_calls_made': 0,
    }
    report['report_hash'] = canonical_hash(report)
    return report


def _percent(metric):
    return 'n/a' if metric['rate'] is None else f"{100 * metric['rate']:.1f}%"


def _ci(metric):
    interval = metric['ci95']
    if interval is None:
        return 'n/a'
    return f"{100 * interval['lower']:.1f}–{100 * interval['upper']:.1f}%"


def report_markdown(report):
    aggregation = report['aggregation']
    sections = []
    for domain in ('math', 'code'):
        rows = []
        for mas_id, result in aggregation['by_domain'][domain].items():
            headline = result['headline_paper_policy']
            diagnostic = result['diagnostic_valid_only']
            rows.append(
                f"| {result['display_name']} | "
                f"{headline['UA']['numerator']}/{headline['UA']['denominator']} "
                f"({_percent(headline['UA'])}; CI {_ci(headline['UA'])}) | "
                f"{headline['ASR']['numerator']}/{headline['ASR']['denominator']} "
                f"({_percent(headline['ASR'])}; CI {_ci(headline['ASR'])}) | "
                f"{_percent(diagnostic['UA'])} / {_percent(diagnostic['ASR'])} |"
            )
        sections.append(f"""## {domain.title()}

| System | Headline UA | Headline ASR | Diagnostic UA / ASR |
|---|---:|---:|---:|
{chr(10).join(rows)}
""")
    return f"""# G7 CrewAI ↔ legacy cross-MAS report

- Report/analysis version: `{report['report_version']}` / `{report['analysis_version']}`
- Matrix complete: **{aggregation['matrix_complete']}**
- Planned/observed core rows: {aggregation['expected_core_rows']} / {aggregation['core_rows']}
- Paid API calls during analysis: 0

The headline applies one paper-style rule to every system: empty output, execution/evaluation
error, non-applicable, target-not-invoked, and payload-not-injected conditions remain in the
denominator and contribute zero. The diagnostic layer separately applies the G6 valid-only
rule. Legacy binary verification has lower diagnostic resolution, so both layers will usually
coincide for legacy systems.

{chr(10).join(sections)}
## Interpretation boundary

UA and ASR must be read together as a utility-security trade-off. This report presents CrewAI's
position under the frozen G7 conditions; it does not produce paired significance tests, a system
ranking, or claims that one system is generally safer than another.
"""


def metrics_csv(report):
    output = io.StringIO()
    fields = [
        'domain', 'mas_id', 'display_name', 'layer', 'metric', 'numerator',
        'denominator', 'rate', 'ci95_method', 'ci95_lower', 'ci95_upper',
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for domain, systems in report['aggregation']['by_domain'].items():
        for mas_id, result in systems.items():
            for layer, key in (
                    ('headline', 'headline_paper_policy'),
                    ('diagnostic', 'diagnostic_valid_only')):
                for metric_name in ('BU', 'UA', 'ASR'):
                    metric = result[key][metric_name]
                    interval = metric['ci95'] or {}
                    writer.writerow({
                        'domain': domain,
                        'mas_id': mas_id,
                        'display_name': result['display_name'],
                        'layer': layer,
                        'metric': metric_name,
                        'numerator': metric['numerator'],
                        'denominator': metric['denominator'],
                        'rate': metric['rate'],
                        'ci95_method': interval.get('method'),
                        'ci95_lower': interval.get('lower'),
                        'ci95_upper': interval.get('upper'),
                    })
    return output.getvalue()


def write_g7_report(directory, report):
    directory = Path(directory).resolve()
    frozen_roots = (
        (ROOT / 'outputs/g5-v2').resolve(),
        (ROOT / 'outputs/g6').resolve(),
    )
    if any(directory == frozen or directory.is_relative_to(frozen)
           for frozen in frozen_roots):
        raise ValueError('G7 report cannot be written under frozen G5-v2/G6 paths')
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {
        directory / 'g7_report.json': json.dumps(
            report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        directory / 'g7_report.md': report_markdown(report),
        directory / 'g7_metrics.csv': metrics_csv(report),
    }
    for path, content in outputs.items():
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content)
        temporary.replace(path)
    artifact = {
        'artifact_version': ARTIFACT_VERSION,
        'report_version': report['report_version'],
        'analysis_version': report['analysis_version'],
        'report_hash': report['report_hash'],
        'input_hashes': report['provenance']['input_hashes'],
        'manifest_hashes': report['provenance']['manifest_hashes'],
        'analysis_sources': report['provenance']['analysis_sources'],
        'dependency_lock_hash': report['provenance']['dependency_lock_hash'],
        'generated_artifacts': {
            path.name: {'path': str(path), 'sha256': file_hash(path)}
            for path in outputs
        },
    }
    manifest_path = directory / 'g7_artifact_manifest.json'
    temporary = manifest_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(
        artifact, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    temporary.replace(manifest_path)
    return (*outputs, manifest_path)
