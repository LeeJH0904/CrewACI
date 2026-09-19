import json
import unittest
from pathlib import Path

from aciarena.evaluation.g7_manifest import G7Manifest, G7ManifestError


ROOT = Path(__file__).resolve().parents[2]


class G7ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = G7Manifest()

    def test_scope_domains_topologies_and_targets_are_complete(self):
        manifest = self.manifest
        self.assertNotIn('mad', manifest.systems)
        self.assertEqual(len(manifest.systems), 7)
        self.assertEqual(manifest.systems['metagpt']['domains'], ['code'])
        for mas_id, system in manifest.systems.items():
            for domain in system['domains']:
                for goal in ('hijacking', 'disruption', 'disclosure'):
                    target = manifest.target(mas_id, domain, goal)
                    self.assertIn(target, system['agents'])

    def test_all_dataset_rows_map_to_one_frozen_task_id(self):
        for domain in ('math', 'code'):
            path = ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json'
            rows = json.loads(path.read_text())
            resolved = [
                self.manifest.resolve_task_id(domain, row['problem'], row['answer'])
                for row in rows
            ]
            self.assertEqual(len(resolved), len(set(resolved)))
            self.assertEqual(resolved, list(self.manifest.task_ids(domain)))

    def test_twenty_two_attack_classes_have_one_id_and_domain_inventory(self):
        manifest = self.manifest
        self.assertEqual(len(manifest.attack_ids_by_class), 22)
        self.assertEqual(len(set(manifest.attack_ids_by_class.values())), 22)
        math = {attack_id for goal in ('hijacking', 'disruption', 'disclosure')
                for attack_id in manifest.attack_ids('math', goal)}
        code = {attack_id for goal in ('hijacking', 'disruption', 'disclosure')
                for attack_id in manifest.attack_ids('code', goal)}
        self.assertEqual((len(math), len(code), len(math | code)), (13, 14, 22))

    def test_dry_run_is_deterministic_and_zero_call(self):
        first = self.manifest.dry_run_slice('camel', 'math', 'hijacking')
        second = G7Manifest().dry_run_slice('camel', 'math', 'hijacking')
        self.assertEqual(first, second)
        self.assertEqual(first['planned_logical_runs'], 39 * 3)
        self.assertEqual(first['paid_api_calls_made'], 0)
        with self.assertRaises(G7ManifestError):
            self.manifest.dry_run_slice('metagpt', 'math', 'hijacking')


if __name__ == '__main__':
    unittest.main()
