import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aciarena.attacks.catalog import AttackCatalog, BenignAttack, CatalogError, DEFAULT_MANIFEST
from aciarena.utils.factory import ATTACK_CLASS_REGISTRY, build_attack


ATTACK_ID = 'disruption_ddos.message.v1'


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(DEFAULT_MANIFEST.read_text())
        self.args = SimpleNamespace(task_domain='math', malicious_agents=['solver'], nested={'items': []})
        self.config = {'provider': 'mock', 'nested': {'items': []}}
        self.judge_patch = patch('aciarena.attacks.base_attack.get_llm', side_effect=lambda config: SimpleNamespace(
            config=config, input_tokens=0, output_tokens=0, client=object()))
        self.judges = self.judge_patch.start()
        self.addCleanup(self.judge_patch.stop)

    def build(self, catalog, attack_id=ATTACK_ID, domain='math'):
        args = copy.deepcopy(self.args)
        args.task_domain = domain
        return build_attack(attack_id, task_domain=domain, args=args, llm_config=self.config, catalog=catalog)

    def load_modified(self, change):
        change(self.manifest)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attacks.json'
            path.write_text(json.dumps(self.manifest))
            return AttackCatalog(path)

    def test_all_selected_classes_construct_in_their_domains(self):
        catalog = AttackCatalog()
        self.judges.assert_not_called()
        for spec in catalog.specs.values():
            for domain in spec.domains:
                with self.subTest(attack=spec.attack_id, domain=domain):
                    attack = self.build(catalog, spec.attack_id, domain)
                    self.assertEqual(f'{type(attack).__module__}.{type(attack).__name__}', spec.class_path)
                    self.assertEqual(attack.payload, spec.payload)
                    self.assertEqual(attack.attack_id, spec.attack_id)
                    self.assertIs(attack.spec, spec)
        self.assertEqual(self.judges.call_count, 9)

    def test_factory_loads_default_catalog(self):
        attack = build_attack(ATTACK_ID, task_domain='math', args=self.args, llm_config=self.config)
        self.assertEqual(attack.attack_id, ATTACK_ID)

    def test_run_state_and_configuration_are_independent(self):
        catalog = AttackCatalog()
        first, second = self.build(catalog), self.build(catalog)
        first.answer = {'response': 'first'}
        first.malicious_agents.append('marker')
        first.turn_count = 99
        first.payload = 'changed'
        first.args.nested['items'].append('first')
        first.llm_judge.config['nested']['items'].append('first')
        first.llm_judge.input_tokens = 123
        self.assertIsNot(first, second)
        self.assertIsNot(first.llm_judge, second.llm_judge)
        self.assertIsNot(first.llm_judge.client, second.llm_judge.client)
        self.assertIsNone(second.answer)
        self.assertEqual(second.malicious_agents, [])
        self.assertEqual(second.turn_count, 0)
        self.assertEqual(second.payload, second.spec.payload)
        self.assertEqual(second.llm_judge.input_tokens, 0)
        self.assertEqual(second.args.nested['items'], [])
        self.assertEqual(second.llm_judge.config['nested']['items'], [])
        self.assertEqual(self.args.nested['items'], [])
        self.assertEqual(self.config['nested']['items'], [])

    def test_twenty_concurrent_builds_have_distinct_state(self):
        catalog = AttackCatalog()

        def build(index):
            attack = self.build(catalog)
            attack.answer = {'response': str(index)}
            attack.llm_judge.input_tokens = index
            return attack

        with ThreadPoolExecutor(max_workers=8) as pool:
            attacks = list(pool.map(build, range(20)))
        self.assertEqual(len({id(a) for a in attacks}), 20)
        self.assertEqual(len({id(a.llm_judge) for a in attacks}), 20)
        self.assertEqual(len({id(a.llm_judge.client) for a in attacks}), 20)
        for index, attack in enumerate(attacks):
            self.assertEqual(attack.answer['response'], str(index))
            self.assertEqual(attack.llm_judge.input_tokens, index)

    def test_benign_build_is_fresh_and_has_no_judge_or_verdict(self):
        catalog = AttackCatalog()
        first = self.build(catalog, 'none')
        second = self.build(catalog, 'none')
        self.assertIsInstance(first, BenignAttack)
        self.assertIsNot(first, second)
        self.assertIsNone(first.verify())
        self.assertIsNone(first.llm_judge)
        self.assertIsNone(first.payload)
        first.answer = {'response': 'changed'}
        self.assertIsNone(second.answer)
        self.judges.assert_not_called()

    def test_registry_order_and_contents_do_not_choose_the_attack(self):
        with patch.dict(ATTACK_CLASS_REGISTRY, {}, clear=True):
            self.assertEqual(self.build(AttackCatalog()).attack_id, ATTACK_ID)

    def test_invalid_requests_fail_before_judge_creation(self):
        catalog = AttackCatalog()
        for attack_id, domain in [('unknown', 'math'), ('hijacking_answer_mapping.agent.v1', 'code'),
                                  (ATTACK_ID, 'science'), ('none', 'science')]:
            with self.subTest(attack=attack_id, domain=domain), self.assertRaises(CatalogError):
                self.build(catalog, attack_id, domain)
        for kwargs in (dict(target='reviewer'), dict(args=SimpleNamespace(task_domain='code')),
                       dict(args=SimpleNamespace(malicious_agents=['reviewer']))):
            request = dict(task_domain='math', args=self.args, llm_config=self.config)
            request.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(CatalogError):
                catalog.build(ATTACK_ID, **request)
        self.judges.assert_not_called()

    def test_bad_metadata_fails_before_judge_creation(self):
        pristine = copy.deepcopy(self.manifest)
        for changes in ({'payload_hash': '0' * 64}, {'payload': 'modified'},
                        {'source_sha256': '0' * 64}, {'verifier_source_hash': '0' * 64},
                        {'verifier': 'wrong.verify'}, {'surface': 'agent'},
                        {'domains': ['math', 'code']}, {'registered_domains': ['code']},
                        {'target': 'reviewer'}, {'goal': 'hijacking'},
                        {'class': 'os.system'}, {'source': '../../outside.py'},
                        {'attack_id': 'none'}, {'unknown_field': 'typo'}):
            self.manifest = copy.deepcopy(pristine)
            with self.subTest(changes=changes), self.assertRaises(CatalogError):
                self.load_modified(lambda m: m['attacks'][0].update(changes))
        self.judges.assert_not_called()

    def test_missing_duplicate_and_dependency_drift_are_rejected(self):
        pristine = copy.deepcopy(self.manifest)
        for change in (lambda m: m['attacks'].pop(),
                       lambda m: m['attacks'].append(m['attacks'][0]),
                       lambda m: m.update(manifest_version='unknown'),
                       lambda m: m['dependencies'].clear(),
                       lambda m: m['dependencies'].update({'aciarena/attacks/base_attack.py': '0' * 64})):
            self.manifest = copy.deepcopy(pristine)
            with self.assertRaises(CatalogError):
                self.load_modified(change)
        self.judges.assert_not_called()

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attacks.json'
            path.write_text('{"attacks": [], "attacks": []}')
            with self.assertRaises(CatalogError):
                AttackCatalog(path)

    def test_catalog_spec_cannot_be_mutated(self):
        catalog = AttackCatalog()
        with self.assertRaises(TypeError):
            catalog.specs[ATTACK_ID] = None
        with self.assertRaises(ValueError):
            catalog.specs[ATTACK_ID].payload = 'changed'

    def test_cached_catalog_rechecks_live_payload_before_construction(self):
        catalog = AttackCatalog()
        with patch('aciarena.attacks.disruption_attack.ALERT_PROMPT', 'drift'):
            with self.assertRaises(CatalogError):
                self.build(catalog)
        self.judges.assert_not_called()


class OpenAIJudgeIsolationTests(unittest.TestCase):
    def test_real_judge_wrappers_and_both_clients_are_new(self):
        # Exercise the real provider factory with SDK constructors substituted;
        # client initialization and API calls do not leave the process.
        with patch('aciarena.agent_components.llms.openai_llm.OpenAI', side_effect=lambda **kw: object()), \
             patch('aciarena.agent_components.llms.openai_llm.AsyncOpenAI', side_effect=lambda **kw: object()):
            catalog = AttackCatalog()
            config = {'provider': 'openai', 'api_key': 'synthetic-unit-test', 'model_name': 'mock'}
            attacks = [build_attack(ATTACK_ID, task_domain='math', args=SimpleNamespace(),
                                    llm_config=config, catalog=catalog) for _ in range(2)]
            first, second = [attack.llm_judge for attack in attacks]
            self.assertIsNot(first, second)
            self.assertIsNot(first.client, second.client)
            self.assertIsNot(first.async_client, second.async_client)
            first.input_tokens = 7
            self.assertEqual(second.input_tokens, 0)


if __name__ == '__main__':
    unittest.main()
