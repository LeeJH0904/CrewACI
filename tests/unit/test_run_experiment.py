import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_experiment import main


class UnifiedOrchestratorTests(unittest.TestCase):
    def dry_run(self, arguments):
        stdout = io.StringIO()
        with patch(
            'scripts.run_experiment.RecordedEvaluationSuite.eval',
            side_effect=AssertionError('dry-run attempted execution'),
        ), contextlib.redirect_stdout(stdout):
            result = main(arguments)
        self.assertEqual(result, 0)
        return json.loads(stdout.getvalue())

    def test_final_matrix_defaults_to_zero_call_dry_run(self):
        report = self.dry_run([])
        self.assertEqual(report['mode'], 'dry-run')
        self.assertEqual(report['logical_runs'], 1056)
        self.assertEqual(report['paid_api_calls_made'], 0)

    def test_suite_expands_from_the_frozen_manifest(self):
        report = self.dry_run([
            '--stage', 'core', '--matrix', 'attacks',
            '--domain', 'math', '--suite', 'hijacking',
        ])
        # Three frozen Math hijacking IDs × 39 tasks.
        self.assertEqual(report['logical_runs'], 117)
        self.assertEqual(
            {attack for group in report['groups'] for attack in group['attack_ids']},
            {
                'hijacking_answer_mapping.agent.v1',
                'hijacking_answer_mapping.instruction.v1',
                'hijacking_math_invert.message.v2',
            },
        )

    def test_attack_ids_select_a_precise_subset(self):
        report = self.dry_run([
            '--stage', 'core', '--matrix', 'attacks', '--domain', 'math',
            '--attack-ids', 'hijacking_answer_mapping.agent.v1',
        ])
        self.assertEqual(report['logical_runs'], 39)

    def test_development_gate_uses_the_predeclared_pilot(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.dry_run([
                '--config', 'configs/experiments/core.yaml',
                '--experiment-id', 'dry-g4', '--output-dir', directory,
                '--stage', 'pilot', '--report', 'gate',
            ])
        self.assertEqual(report['logical_runs'], 30)
        self.assertEqual(report['report'], 'gate')


if __name__ == '__main__':
    unittest.main()
