import json
from pathlib import Path
import unittest

from math_verify import ExprExtractionConfig, LatexExtractionConfig, parse, verify

from aciarena.attacks.catalog import AttackCatalog
from aciarena.attacks.hijacking_attack import AnswerMappingAgent, SafetyCheckInstruction
from aciarena.evaluation.normalizers import NORMALIZER_VERSION, normalize_response
from aciarena.evaluation.recorded_executor import (
    ATTACK_NOT_APPLICABLE,
    ROOT,
    verify_code,
    verify_math,
)
from aciarena.evaluation.task import CodeTask, MathTask


GOLDEN = Path(__file__).resolve().parents[1] / 'golden/g2_verifier.json'


def task_at(task_id):
    domain, raw_index = task_id.split('_')
    index = int(raw_index)
    row = json.loads((ROOT / f'aciarena/evaluation/datasets/aciarena_{domain}.json').read_text())[index]
    task = (MathTask if domain == 'math' else CodeTask)(row['problem'], row['answer'])
    task.task_id = task_id
    return task


def code_response(task, template):
    ground = task.get_gt()
    correct = ground.get('prompt', '') + ground.get('canonical_solution', ground.get('code', ''))
    return template.replace('{correct}', correct).replace('{prompt}', ground.get('prompt', ''))


class G2VerifierGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN.read_text())
        cls.catalog = AttackCatalog()

    def set_answer(self, task, raw):
        task.set_answer({'raw_response': raw, 'response': normalize_response(raw)})

    def test_fixture_version_matches_normalizer(self):
        self.assertEqual(self.golden['schema_version'], 'g2-v1')
        self.assertEqual(self.golden['normalizer'], NORMALIZER_VERSION)

    def test_math_correct_incorrect_explanation_fence_and_empty(self):
        for case in self.golden['math']:
            with self.subTest(case=case['case_id']):
                task = task_at(case['task_id'])
                self.set_answer(task, case['response'])
                value = verify_math(task)
                self.assertEqual(None if value is None else bool(value), case['expected_utility'])

    def test_answer_mapping_integer_fraction_original_and_applicability(self):
        spec = self.catalog.get(
            'hijacking_answer_mapping.agent.v1', task_domain='math')
        for case in self.golden['answer_mapping']:
            with self.subTest(case=case['case_id']):
                task = task_at(case['task_id'])
                self.set_answer(task, case['response'])
                utility = verify_math(task)
                attack = verify_math(task, spec)
                self.assertEqual(None if utility is None else bool(utility), case['expected_utility'])
                if case['applicable']:
                    self.assertIsNot(attack, ATTACK_NOT_APPLICABLE)
                    self.assertEqual(None if attack is None else bool(attack), case['expected_attack'])
                else:
                    self.assertIs(attack, ATTACK_NOT_APPLICABLE)
                    self.assertIsNone(case['expected_attack'])

    def test_answer_mapping_has_one_declared_non_applicable_math_task(self):
        mapper = AnswerMappingAgent.__new__(AnswerMappingAgent)
        rows = json.loads((ROOT / 'aciarena/evaluation/datasets/aciarena_math.json').read_text())
        extraction = (ExprExtractionConfig(), LatexExtractionConfig())
        non_applicable = []
        for index, row in enumerate(rows):
            original = row['answer']
            mapped = mapper.apply_mapping(original)
            if not mapper.is_applicable(original):
                non_applicable.append(f'math_{index:04d}')
                continue
            original_values = parse(f'${original}$', extraction_config=extraction)
            mapped_values = parse(f'${mapped}$', extraction_config=extraction)
            self.assertTrue(original_values, f'math_{index:04d} original did not parse')
            self.assertTrue(mapped_values, f'math_{index:04d} mapped target did not parse')
            self.assertFalse(verify(original_values, mapped_values),
                             f'math_{index:04d} mapped target equals utility target')
        self.assertEqual(non_applicable, ['math_0016'])

    def test_code_correct_incorrect_explanation_fence_empty_and_timeout(self):
        for case in self.golden['code']:
            with self.subTest(case=case['case_id']):
                task = task_at(case['task_id'])
                self.set_answer(task, code_response(task, case['response_template']))
                self.assertEqual(bool(verify_code(task)), case['expected_utility'])

    def test_code_attack_evidence_and_utility_are_independent(self):
        case = self.golden['code_attack_mix']
        task = task_at(case['task_id'])
        response = code_response(task, case['response_template'])
        self.set_answer(task, response)
        attack = SafetyCheckInstruction.__new__(SafetyCheckInstruction)
        attack.answer = task.answer
        self.assertEqual(bool(verify_code(task)), case['expected_utility'])
        self.assertEqual(bool(attack.verify()), case['expected_attack'])


if __name__ == '__main__':
    unittest.main()
