import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.build_manifests import ROOT, build_manifests, check_files, planned_summary


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = build_manifests()

    def test_checked_in_files_match_source_and_policy(self):
        check_files(self.manifests, ROOT / 'manifests')

    def test_task_ids_sources_and_upstream_coverage(self):
        tasks = self.manifests['tasks.json']['tasks']
        self.assertEqual(len({task['task_id'] for task in tasks}), 69)
        self.assertEqual(sum(t['task_domain'] == 'math' for t in tasks), 39)
        self.assertEqual(sum(t['task_domain'] == 'code' for t in tasks), 30)
        self.assertTrue(all(t['upstream_task_id'] is None for t in tasks if t['task_domain'] == 'math'))
        selected = set(self.manifests['calibration_tasks.json']['task_ids'])
        sample = [task for task in tasks if task['task_id'] in selected]
        self.assertEqual(len(sample), 10)
        self.assertEqual(sum(t['task_domain'] == 'math' for t in sample), 5)
        self.assertEqual(sum(t['upstream_dataset'] == 'humaneval' for t in sample), 2)
        self.assertEqual(sum(t['upstream_dataset'] == 'mbpp' for t in sample), 3)

    def test_variants_are_explicit_and_cover_three_surfaces(self):
        attacks = self.manifests['attacks.json']['attacks']
        self.assertEqual(len({a['attack_id'] for a in attacks}), 8)
        self.assertEqual(len({a['attack_category'] for a in attacks}), 8)
        self.assertEqual({a['surface'] for a in attacks}, {'agent', 'instruction', 'message'})
        for attack in attacks:
            self.assertLessEqual(set(attack['domains']), set(attack['registered_domains']))
            self.assertEqual(attack['target'], 'solver')
            self.assertTrue(attack['applicability'])

    def test_source_description_matches_real_objects_without_llm(self):
        # Validate the static builder against actual constructors. A new Judge
        # initialization is substituted at its boundary, never sent to a provider.
        import aciarena.attacks.base_attack
        with patch.object(aciarena.attacks.base_attack, 'get_llm', return_value=object()):
            for entry in self.manifests['attacks.json']['attacks']:
                with self.subTest(attack=entry['attack_id']):
                    module, name = entry['class'].rsplit('.', 1)
                    attack = getattr(importlib.import_module(module), name)(args=SimpleNamespace(), llm_config={})
                    self.assertEqual(attack.payload, entry['payload'])
                    self.assertEqual(hashlib.sha256(attack.payload.encode()).hexdigest(), entry['payload_hash'])
                    self.assertTrue(callable(attack.verify))

    def test_confirmation_coverage_and_compatibility(self):
        confirmation = self.manifests['confirmation_tasks.json']
        self.assertEqual(confirmation['task_ids'], self.manifests['calibration_tasks.json']['task_ids'])
        by_id = {a['attack_id']: a for a in self.manifests['attacks.json']['attacks']}
        for domain, ids in confirmation['attack_ids_by_domain'].items():
            self.assertEqual(len(set(ids)), 3)
            entries = [by_id[attack_id] for attack_id in ids]
            self.assertEqual({a['surface'] for a in entries}, {'instruction', 'agent', 'message'})
            self.assertEqual({a['goal'] for a in entries}, {'disclosure', 'disruption', 'hijacking'})
            self.assertTrue(all(domain in a['domains'] for a in entries))

    def test_counts_follow_actual_domain_support(self):
        summary = planned_summary(self.manifests)
        self.assertEqual(summary['core_attacks'], 306)
        self.assertEqual(summary['core_attack_not_applicable'], 1)
        self.assertEqual(summary['core_attack_max_valid_denominator'], 305)
        self.assertEqual(summary['total_excluding_pilot_and_retries'], 455)
        self.assertEqual(summary['pilot_separate'], 30)
        self.assertEqual(summary['confirmation'], 60)

    def test_drift_duplicate_or_missing_manifest_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in self.manifests.items():
                (root / name).write_text(json.dumps(value))
            check_files(self.manifests, root)
            bad = copy.deepcopy(self.manifests['tasks.json'])
            bad['tasks'][1]['task_id'] = bad['tasks'][0]['task_id']
            (root / 'tasks.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, 'differs'):
                check_files(self.manifests, root)
            (root / 'tasks.json').unlink()
            with self.assertRaisesRegex(ValueError, 'tasks.json'):
                check_files(self.manifests, root)


if __name__ == '__main__':
    unittest.main()
