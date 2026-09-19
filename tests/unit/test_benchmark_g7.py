from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark


class BenchmarkG7Tests(unittest.TestCase):
    def args(self, output_dir, **overrides):
        values = dict(
            attack_ids=None,
            experiment_id='g7-benchmark-test',
            experiment_config='configs/experiments/g5_v2.yaml',
            phase='core', repetition=1, resume=False, retry_errors=False,
            execute=False, model_config=None, judge_config=None,
            mas='camel', suite='hijacking', attack_mode='continuous',
            defense='none', task_domain='math', max_workers=1, limit=2,
            task_ids=None, output_dir=output_dir, malicious_agents=[],
        )
        values.update(overrides)
        return Namespace(**values)

    def test_default_g7_invocation_is_deterministic_zero_call_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'g7'
            args = self.args(str(output))
            with patch('aciarena.attacks.base_attack.get_llm',
                       side_effect=AssertionError('dry-run constructed an LLM')):
                first = benchmark.main(args)
                second = benchmark.main(args)
            self.assertEqual(first, second)
            self.assertEqual(first['mode'], 'dry-run')
            self.assertEqual(first['paid_api_calls_made'], 0)
            self.assertEqual(first['logical_runs'], 6)
            self.assertFalse(output.exists())

    def test_explicit_nonbenchmark_target_is_supported_but_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            result = benchmark.main(self.args(
                directory, malicious_agents=['assistant']))
            self.assertEqual(result['target_agent'], 'assistant')

    def test_crewai_dry_run_uses_full_g7_inventory_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'g7'
            result = benchmark.main(self.args(
                str(output), mas='crewai_seq_nodeleg', suite='disclosure',
                malicious_agents=[], limit=2))
            self.assertEqual(result['mode'], 'dry-run')
            self.assertEqual(result['target_agent'], 'solver')
            self.assertEqual(result['paid_api_calls_made'], 0)
            self.assertEqual(result['logical_runs'], 10)
            self.assertEqual(len(result['attack_ids']), 5)
            self.assertFalse(output.exists())

    def test_g7_cli_rejects_frozen_output_even_in_dry_run(self):
        frozen = Path(__file__).resolve().parents[2] / 'outputs/g6'
        with self.assertRaisesRegex(ValueError, 'frozen'):
            benchmark.main(self.args(
                str(frozen), mas='crewai_seq_nodeleg', suite='benign'))


if __name__ == '__main__':
    unittest.main()
