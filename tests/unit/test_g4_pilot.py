import json
from pathlib import Path
import tempfile
import unittest

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.audit import build_manifest_plan
from aciarena.evaluation.pilot import (
    REPORT_VERSION,
    build_g4_report,
    pilot_groups,
    pilot_manifest,
)
from aciarena.evaluation.recorded_executor import load_task_manifest
from aciarena.evaluation.run_writer import RunWriter


class G4PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.tasks = load_task_manifest()
        cls.catalog = AttackCatalog()

    def test_fixed_manifest_builds_exact_six_groups_and_thirty_runs(self):
        manifest = pilot_manifest()
        groups = pilot_groups(self.tasks, self.catalog, manifest)
        self.assertEqual(len(groups), 6)
        self.assertEqual(sum(len(group['task_ids']) * len(group['attack_ids'])
                             for group in groups), 30)
        self.assertEqual({group['task_domain'] for group in groups}, {'math', 'code'})
        self.assertEqual({group['suite'] for group in groups},
                         {'disclosure', 'disruption', 'hijacking'})
        plan = build_manifest_plan(
            'pilot', experiment_id='g4-test', tasks=self.tasks, catalog=self.catalog)
        self.assertEqual(len(plan.expected), 30)

    def test_empty_evidence_fails_closed_and_reports_every_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_g4_report(
                RunWriter(directory), experiment_id='g4-empty',
                tasks=self.tasks, catalog=self.catalog)
        self.assertFalse(report['gate_pass'])
        self.assertEqual(report['counts']['planned_logical_runs'], 30)
        self.assertEqual(report['counts']['observed_logical_runs'], 0)
        self.assertEqual(report['hierarchical']['technical_decision'],
                         'not_eligible_gate_failed')
        self.assertFalse(report['hierarchical']['team_consensus_recorded'])
        self.assertEqual(report['cost']['paid_api_cost_usd'], 0.0)
        self.assertEqual(REPORT_VERSION, 'g4-pilot-report-v2')
        self.assertEqual(report['report_version'], REPORT_VERSION)
        self.assertIn('math_evaluation_valid_at_least_98pct', report['checks'])
        self.assertRegex(report['report_hash'], r'^[0-9a-f]{64}$')
        self.assertIn('missing_planned_runs', report['audit']['errors'][0])

    def test_pilot_manifest_rejects_duplicate_tasks(self):
        manifest = pilot_manifest()
        manifest['task_ids'][1] = manifest['task_ids'][0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pilot.json'
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'ten unique'):
                pilot_manifest(path)


if __name__ == '__main__':
    unittest.main()
