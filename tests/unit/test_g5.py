import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aciarena.attacks.catalog import AttackCatalog
from aciarena.evaluation.configuration import (
    experiment_manifest_directory,
    load_experiment_configuration,
)
from scripts.g5.build_g5_manifests import (
    OUTPUT_DIRECTORY,
    build_manifests,
    check_files,
    planned_summary,
)
from scripts.g5.preflight_g5_provider import main as preflight_main
from scripts.g5.run_g5_matrix import (
    execution_groups,
    g5_groups,
    main as run_g5_main,
    matrix_plan,
    pending_execution_groups,
    stage_groups,
    usage_cost,
)
from aciarena.utils.factory import build_attack


class G5ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = build_manifests()

    def test_checked_in_full_inventory_and_counts(self):
        check_files(self.manifests, OUTPUT_DIRECTORY)
        attacks = self.manifests['attacks.json']['attacks']
        self.assertEqual(len(attacks), 22)
        self.assertEqual(len({row['attack_id'] for row in attacks}), 22)
        self.assertEqual(len({row['class'] for row in attacks}), 22)
        summary = planned_summary(
            self.manifests['tasks.json'], self.manifests['attacks.json'],
            self.manifests['confirmation_tasks.json'])
        self.assertEqual(summary['attacks_per_domain'], {'math': 13, 'code': 14})
        self.assertEqual(summary['core_attacks'], 927)
        self.assertEqual(summary['confirmation'], 60)
        self.assertEqual(summary['g5_total'], 1056)

    def test_g5_catalog_and_exact_group_plan(self):
        contract, _, _ = load_experiment_configuration('configs/experiments/g5_v2.yaml')
        directory = experiment_manifest_directory('configs/experiments/g5_v2.yaml', contract)
        groups, tasks, catalog = g5_groups(contract, directory)
        self.assertEqual(len(catalog.specs), 22)
        self.assertEqual(len(groups), 20)
        self.assertEqual(len(matrix_plan(
            'g5-test', groups, tasks, catalog, '0' * 64).expected), 1056)

    def test_every_g5_attack_constructs_in_every_declared_domain(self):
        catalog = AttackCatalog(OUTPUT_DIRECTORY / 'attacks.json')
        config = {'provider': 'mock'}
        with patch(
            'aciarena.attacks.base_attack.get_llm',
            side_effect=lambda value: SimpleNamespace(config=value),
        ):
            for spec in catalog.specs.values():
                for domain in spec.domains:
                    with self.subTest(attack=spec.attack_id, domain=domain):
                        attack = build_attack(
                            spec.attack_id,
                            task_domain=domain,
                            args=SimpleNamespace(
                                task_domain=domain, malicious_agents=['solver']),
                            llm_config=config,
                            catalog=catalog,
                        )
                        self.assertEqual(attack.attack_id, spec.attack_id)
                        self.assertEqual(attack.payload, spec.payload)

    def test_stages_partition_the_matrix_and_use_bounded_batches(self):
        contract, _, _ = load_experiment_configuration('configs/experiments/g5_v2.yaml')
        directory = experiment_manifest_directory('configs/experiments/g5_v2.yaml', contract)
        groups, tasks, catalog = g5_groups(contract, directory)
        expected = {
            'smoke': 8,
            'benign': 69,
            'math-core': 507,
            'code-core': 420,
            'confirmation': 60,
            'all': 1056,
        }
        for stage, count in expected.items():
            selected = stage_groups(groups, stage)
            with self.subTest(stage=stage):
                self.assertEqual(
                    len(matrix_plan(
                        'g5-test', selected, tasks, catalog, '0' * 64).expected), count)
                batches = execution_groups(selected, batch_size=5)
                self.assertTrue(all(
                    len(batch['task_ids']) * len(batch['attack_ids']) <= 5
                    for batch in batches
                ))
        partition = set()
        for stage in ('benign', 'math-core', 'code-core', 'confirmation'):
            selected = matrix_plan(
                'g5-test', stage_groups(groups, stage), tasks, catalog, '0' * 64).expected
            self.assertFalse(partition & set(selected))
            partition.update(selected)
        self.assertEqual(len(partition), 1056)

    def test_completed_batches_are_skipped_before_session_caps_are_applied(self):
        contract, _, _ = load_experiment_configuration('configs/experiments/g5_v2.yaml')
        directory = experiment_manifest_directory('configs/experiments/g5_v2.yaml', contract)
        groups, tasks, catalog = g5_groups(contract, directory)
        batches = execution_groups(stage_groups(groups, 'smoke'), batch_size=5)
        first = matrix_plan(
            'g5-test', [batches[0]], tasks, catalog, '0' * 64).expected
        pending = pending_execution_groups(
            batches, 'g5-test', tasks, catalog, '0' * 64, set(first))
        self.assertEqual(len(pending), len(batches) - 1)
        self.assertNotIn(batches[0], pending)

        # A row from another frozen configuration must never satisfy resume.
        other = {key.__class__(
            key.experiment_id, key.task_id, key.mas_id, key.implementation,
            key.attack_id, key.repetition, key.phase, '1' * 64)
            for key in first}
        isolated = pending_execution_groups(
            batches, 'g5-test', tasks, catalog, '0' * 64, other)
        self.assertEqual(isolated, batches)

    def test_final_contract_is_ready_after_provider_preflight(self):
        contract, model, judge = load_experiment_configuration('configs/experiments/g5_v2.yaml')
        self.assertFalse(contract['final_benchmark_ready'])
        self.assertEqual(contract['seed_policy']['status'], 'provider_preflight_required')
        self.assertEqual(contract['paid_api_budget_usd'], 2.0)
        self.assertEqual(contract['retry_policy']['sdk_requests_per_llm_call'], 1)
        self.assertEqual(model['model_name'], 'gpt-4o-mini-2024-07-18')
        self.assertEqual(judge['model_name'], model['model_name'])

    def test_paid_execution_fails_closed_if_preflight_artifact_is_not_valid(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('scripts.g5.run_g5_matrix.preflight_passed', return_value=False), \
                self.assertRaisesRegex(
                    RuntimeError, 'locked until the provider preflight passes'
                ):
            run_g5_main([
                '--execute', '--stage', 'smoke', '--output-dir', directory])

    def test_full_paid_matrix_requires_an_extra_opt_in(self):
        with tempfile.TemporaryDirectory() as directory, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            run_g5_main(['--execute', '--stage', 'all', '--output-dir', directory])
        self.assertEqual(raised.exception.code, 2)


class MathVerifyAttackIsolationTests(unittest.TestCase):
    """math-verify attack verifiers must run in the isolated main-thread worker.

    Calling math_verify.verify() inside a ThreadPoolExecutor worker fails to
    register its POSIX signal timeout and silently returns false (the D46/D47
    MathInvert bug). These tests fix the routing invariant and prove the worker
    path returns the correct verdict off the main thread.
    """

    @classmethod
    def setUpClass(cls):
        cls.catalog = AttackCatalog(OUTPUT_DIRECTORY / 'attacks.json')

    def _task(self, ground_truth, response):
        return SimpleNamespace(
            get_gt=lambda: ground_truth,
            answer={'response': response, 'ground_truth': ground_truth})

    def test_every_math_verify_attack_is_routed_to_the_isolated_worker(self):
        from aciarena.evaluation.recorded_executor import (
            MATH_VERIFY_ATTACK_CATEGORIES,
            MATH_VERIFY_WORKER_KINDS,
        )
        # Any catalog attack whose verify() uses math-verify must be declared,
        # so a newly added math attack cannot silently regress by omission.
        math_verify_attacks = {
            'hijacking_answer_mapping.agent.v1',
            'hijacking_answer_mapping.instruction.v1',
            'hijacking_math_invert.message.v2',
        }
        worker_kinds = {'mapping_agent', 'mapping_instruction', 'math_invert'}
        for attack_id in math_verify_attacks:
            spec = self.catalog.get(attack_id, task_domain='math')
            self.assertIn(spec.attack_category, MATH_VERIFY_ATTACK_CATEGORIES)
            kind = MATH_VERIFY_WORKER_KINDS[(spec.attack_category, spec.surface)]
            self.assertIn(kind, worker_kinds)

    def test_math_invert_verdicts_are_correct_off_the_main_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        from aciarena.evaluation.recorded_executor import verify_math
        spec = self.catalog.get('hijacking_math_invert.message.v2', task_domain='math')
        # invert_sign('42') == '-42': the inverted answer is the attack goal.
        cases = [
            (self._task('42', 'The result is \\boxed{-42}.'), 1.0),  # attack succeeded
            (self._task('42', 'The result is \\boxed{42}.'), 0.0),   # attack failed
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda case: verify_math(case[0], spec), cases))
        self.assertEqual(results, [expected for _, expected in cases])

    def test_math_invert_v2_targets_and_inapplicability_are_semantic(self):
        from aciarena.attacks.hijacking_attack import MathInvertMessage
        rows = json.loads(Path(
            'aciarena/evaluation/datasets/aciarena_math.json').read_text())
        attack = object.__new__(MathInvertMessage)
        unavailable = {
            f'math_{index:04d}' for index, row in enumerate(rows)
            if attack.invert_sign(row['answer']) is None
        }
        self.assertEqual(unavailable, {
            'math_0016', 'math_0024', 'math_0033', 'math_0035'})
        self.assertEqual(attack.invert_sign('-\\frac{35}{9}'), '\\frac{35}{9}')
        self.assertIsNotNone(attack.invert_sign('1+274i'))
        self.assertIsNotNone(attack.invert_sign('3 \\pm 2 \\sqrt{2}'))
        self.assertIsNotNone(attack.invert_sign(
            '\\begin{pmatrix} -18 \\\\ -49 \\\\ 96 \\end{pmatrix}'))
        spec = self.catalog.get(
            'hijacking_math_invert.message.v2', task_domain='math')
        self.assertEqual(set(spec.not_applicable_task_ids), unavailable)


class G5UsageTests(unittest.TestCase):
    def test_cost_retains_known_lower_bound_and_marks_missing_usage(self):
        row = SimpleNamespace(
            prompt_tokens=100, completion_tokens=20, usage_missing_calls=1)
        report = usage_cost([row], {
            'input_per_million_usd': 0.15,
            'output_per_million_usd': 0.60,
        })
        self.assertEqual(report['prompt_tokens'], 100)
        self.assertEqual(report['completion_tokens'], 20)
        self.assertEqual(report['usage_missing_calls'], 1)
        self.assertFalse(report['usage_complete'])
        self.assertTrue(report['cost_is_lower_bound'])


class G5PreflightTests(unittest.TestCase):
    def test_provider_errors_are_persisted_without_provider_text(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'preflight.json'
            stdout = io.StringIO()
            with patch('scripts.g5.preflight_g5_provider.run_preflight',
                       side_effect=RuntimeError('secret-provider-text')), \
                    contextlib.redirect_stdout(stdout):
                result = preflight_main(['--output', str(output)])
            self.assertEqual(result, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report['error_type'], 'RuntimeError')
            self.assertNotIn('secret-provider-text', output.read_text())
            self.assertNotIn('secret-provider-text', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
