import json
from pathlib import Path
import tempfile
import unittest

from aciarena.evaluation.g7_aggregation import aggregate_g7
from aciarena.evaluation.g7_reporting import build_g7_report, write_g7_report
from scripts.aggregate_g7 import main as aggregate_main


COST_POLICY = {
    'input_per_million_usd': 0.15,
    'output_per_million_usd': 0.60,
    'pricing_as_of': 'fixture',
}


def row(mas_id, implementation, domain, index, *, attack_id='none', status='success',
        utility_status='valid', utility_success=True, attack_status='not_applicable',
        attack_success=None, target=None, payload=None):
    attacked = attack_id != 'none'
    return {
        'experiment_id': 'g7-fixture',
        'task_id': f'{domain}_{index:04d}',
        'mas_id': mas_id,
        'implementation': implementation,
        'attack_id': attack_id,
        'repetition': 1,
        'phase': 'core',
        'config_hash': 'a' * 64,
        'run_id': f'run_{domain}_{mas_id}_{index}_{attack_id}',
        'attempt_no': 1,
        'task_domain': domain,
        'topology': 'sequential' if mas_id == 'crewai_seq_nodeleg' else 'horizontal',
        'model': 'mock',
        'status': status,
        'utility_status': utility_status,
        'utility_success': utility_success,
        'attack_status': attack_status,
        'attack_success': attack_success,
        'attack_goal': 'disclosure' if attacked else None,
        'attack_category': 'disclosure_generic_apikey' if attacked else None,
        'attack_surface': 'agent' if attacked else None,
        'target_invoked': target,
        'payload_injected': payload,
        'raw_response': '' if status == 'success' else None,
        'llm_call_count': 1,
        'prompt_tokens': 1,
        'completion_tokens': 1,
        'usage_missing_calls': 0,
        'latency_ms': 1.0,
    }


def system_rows(mas_id, implementation, domain):
    return [
        row(mas_id, implementation, domain, 0),
        row(
            mas_id, implementation, domain, 1, attack_id='attack.valid',
            attack_status='valid', attack_success=False, target=True, payload=True),
        row(
            mas_id, implementation, domain, 2, attack_id='attack.error',
            status='model_error', utility_status='unknown', utility_success=None,
            attack_status='unknown', attack_success=None, target=False, payload=False),
        row(
            mas_id, implementation, domain, 3, attack_id='attack.na',
            attack_status='not_applicable', attack_success=None,
            target=True, payload=True),
    ]


class G7AggregationTests(unittest.TestCase):
    def setUp(self):
        math_systems = (
            'crewai_seq_nodeleg', 'autogen', 'camel', 'sc',
            'llm_debate', 'agentverse',
        )
        code_systems = (*math_systems, 'metagpt')
        self.rows = []
        for domain, systems in (('math', math_systems), ('code', code_systems)):
            for mas_id in systems:
                implementation = ('reconstructed' if mas_id == 'crewai_seq_nodeleg'
                                  else 'legacy')
                self.rows.extend(system_rows(mas_id, implementation, domain))

    def test_same_two_layer_policy_applies_to_crewai_and_legacy(self):
        report = aggregate_g7(self.rows, cost_policy=COST_POLICY)
        for domain, systems in report['by_domain'].items():
            for mas_id, system in systems.items():
                with self.subTest(domain=domain, mas_id=mas_id):
                    headline = system['headline_paper_policy']
                    diagnostic = system['diagnostic_valid_only']
                    self.assertEqual(
                        (headline['UA']['numerator'], headline['UA']['denominator']),
                        (2, 3))
                    self.assertEqual(
                        (headline['ASR']['numerator'], headline['ASR']['denominator']),
                        (0, 3))
                    self.assertEqual(
                        (diagnostic['UA']['numerator'], diagnostic['UA']['denominator']),
                        (2, 2))
                    self.assertEqual(
                        (diagnostic['ASR']['numerator'], diagnostic['ASR']['denominator']),
                        (0, 1))
                    self.assertEqual(system['status_counts']['execution_errors'], 1)
            self.assertEqual(system['status_counts']['attack_not_applicable'], 1)
        self.assertEqual(report['expected_core_rows'], 6426)
        self.assertFalse(report['matrix_complete'])
        self.assertGreater(report['matrix_audit']['missing_conditions'], 0)
        self.assertGreater(report['matrix_audit']['unexpected_conditions'], 0)

    def test_diagnostic_layer_survives_retried_conditions(self):
        # A condition whose first attempt was a transient error and whose second
        # attempt succeeded: adopt_attempts keeps attempt_no=2. The valid-only
        # diagnostic re-runs adopt_attempts internally, so it must see the full
        # 1..n sequence, not the lone adopted attempt. Regression guard: feeding
        # the adopted rows crashes with 'Attempt sequence is not contiguous'.
        first = row('camel', 'legacy', 'math', 7, attack_id='attack.retry',
                    status='model_error', utility_status='unknown',
                    utility_success=None, attack_status='unknown',
                    attack_success=None, target=False, payload=False)
        first['attempt_no'] = 1
        second = row('camel', 'legacy', 'math', 7, attack_id='attack.retry',
                     attack_status='valid', attack_success=False,
                     target=True, payload=True)
        second['attempt_no'] = 2
        rows = [row('camel', 'legacy', 'math', 0), first, second]
        report = aggregate_g7(rows, cost_policy=COST_POLICY)  # must not raise
        system = report['by_domain']['math']['camel']
        # The adopted attempt (no. 2) is a valid attack condition, so it stays in
        # both the headline and the valid-only diagnostic denominators.
        self.assertEqual(system['headline_paper_policy']['UA']['denominator'], 1)
        self.assertEqual(system['diagnostic_valid_only']['UA']['denominator'], 1)
        self.assertEqual(system['diagnostic_valid_only']['UA']['numerator'], 1)

    def test_report_is_g7_versioned_and_writes_separate_artifacts(self):
        report = build_g7_report(self.rows, cost_policy=COST_POLICY)
        self.assertTrue(report['report_version'].startswith('g7-'))
        self.assertTrue(report['analysis_version'].startswith('g7-'))
        self.assertEqual(report['scope']['framing'],
                         'CrewAI position plus design attribution; no safety ranking')
        with tempfile.TemporaryDirectory() as directory:
            paths = write_g7_report(directory, report)
            self.assertEqual({path.name for path in paths}, {
                'g7_report.json', 'g7_report.md', 'g7_metrics.csv',
                'g7_artifact_manifest.json',
            })
            artifact = json.loads((Path(directory) / 'g7_artifact_manifest.json').read_text())
            self.assertTrue(artifact['artifact_version'].startswith('g7-'))
            self.assertEqual(artifact['report_hash'], report['report_hash'])

    def test_read_only_cli_creates_no_input_or_output_and_frozen_write_is_rejected(self):
        report = build_g7_report(self.rows, cost_policy=COST_POLICY)
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing-records'
            output = Path(directory) / 'report'
            self.assertEqual(aggregate_main([
                '--records-dir', str(missing), '--output-dir', str(output),
            ]), 0)
            self.assertFalse(missing.exists())
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                aggregate_main([
                    '--records-dir', str(missing), '--output-dir', str(output),
                    '--write',
                ])
            self.assertFalse(output.exists())
        frozen = Path(__file__).resolve().parents[2] / 'outputs/g6/g7-forbidden'
        with self.assertRaisesRegex(ValueError, 'frozen'):
            write_g7_report(frozen, report)
        self.assertFalse(frozen.exists())


if __name__ == '__main__':
    unittest.main()
