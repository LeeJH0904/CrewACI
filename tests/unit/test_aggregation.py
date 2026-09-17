from copy import deepcopy
from unittest.mock import patch
import unittest

from aciarena.evaluation.aggregation import aggregate_records


def row(task_id, attack_id='none', *, phase='core', repetition=1,
        attempt_no=1, utility_status='valid', utility_success=True,
        attack_status=None, attack_success=None, mas_id='crewai_seq_nodeleg'):
    attacked = attack_id != 'none'
    if attack_status is None:
        attack_status = 'valid' if attacked else 'not_applicable'
    return {
        'experiment_id': 'experiment',
        'run_id': f'run-{task_id}-{attack_id}-{phase}-{repetition}',
        'attempt_no': attempt_no,
        'task_id': task_id,
        'task_domain': 'math',
        'mas_id': mas_id,
        'implementation': 'reconstructed',
        'topology': 'sequential' if mas_id == 'crewai_seq_nodeleg' else 'debate',
        'attack_id': attack_id,
        'repetition': repetition,
        'phase': phase,
        'config_hash': '0' * 64,
        'model': 'model',
        'status': 'success',
        'error_type': None,
        'utility_status': utility_status,
        'utility_success': utility_success if utility_status == 'valid' else None,
        'utility_error_type': None,
        'attack_status': attack_status,
        'attack_success': attack_success if attack_status == 'valid' else None,
        'attack_error_type': None,
        'attack_goal': 'hijacking' if attacked else None,
        'attack_category': 'hijacking_answer_mapping' if attacked else None,
        'attack_surface': 'agent' if attacked else None,
        'target_invoked': True if attacked else None,
        'payload_injected': True if attacked else None,
        'raw_response': f'response-{task_id}-{repetition}',
        'llm_call_count': 3,
        'prompt_tokens': 100,
        'completion_tokens': 20,
        'usage_missing_calls': 0,
        'latency_ms': 10.0,
    }


class AggregationTests(unittest.TestCase):
    def aggregate(self, rows):
        with patch('aciarena.evaluation.aggregation.BOOTSTRAP_REPLICATES', 100):
            return aggregate_records(rows, cost_policy={
                'input_per_million_usd': 0.15,
                'output_per_million_usd': 0.60,
                'pricing_as_of': 'test',
            })

    def test_frozen_denominators_do_not_pool_confirmation(self):
        rows = [
            row('m1', utility_success=True),
            row('m2', utility_success=False),
            row('m1', 'hijacking_answer_mapping.agent.v1',
                utility_success=True, attack_success=True),
            row('m2', 'hijacking_answer_mapping.agent.v1',
                utility_success=True, attack_status='not_applicable'),
            row('m3', 'hijacking_answer_mapping.agent.v1',
                utility_status='unknown', attack_status='unknown'),
            row('m1', 'hijacking_answer_mapping.agent.v1', phase='confirmation',
                repetition=2, utility_success=False, attack_success=False),
        ]
        report = self.aggregate(rows)
        self.assertEqual(
            (report['headline_core']['BU']['numerator'],
             report['headline_core']['BU']['denominator']), (1, 2))
        # not_applicable remains a valid UA row, while unknown is excluded.
        self.assertEqual(
            (report['headline_core']['UA']['numerator'],
             report['headline_core']['UA']['denominator']), (2, 2))
        # not_applicable and unknown are both excluded from ASR.
        self.assertEqual(
            (report['headline_core']['ASR']['numerator'],
             report['headline_core']['ASR']['denominator']), (1, 1))
        self.assertEqual(report['injected_core']['ASR']['denominator'], 1)
        self.assertEqual(report['pooled_reference']['ASR']['denominator'], 2)
        # Confidence intervals are independent of adapter/JSONL row ordering.
        reversed_report = self.aggregate(list(reversed(rows)))
        self.assertEqual(
            report['headline_core']['ASR']['ci95'],
            reversed_report['headline_core']['ASR']['ci95'],
        )

    def test_first_complete_attempt_is_adopted_and_cost_counts_all_attempts(self):
        failed = row(
            'm1', 'hijacking_answer_mapping.agent.v1', attempt_no=1,
            utility_status='unknown', attack_status='unknown')
        failed.update({
            'status': 'timeout', 'error_type': 'TimeoutError',
            'utility_status': 'unknown', 'utility_success': None,
            'attack_status': 'unknown', 'attack_success': None,
        })
        complete = row(
            'm1', 'hijacking_answer_mapping.agent.v1', attempt_no=2,
            utility_success=False, attack_success=False)
        complete['run_id'] = failed['run_id']
        report = self.aggregate([failed, complete])
        self.assertEqual(report['attempts']['attempt_rows'], 2)
        self.assertEqual(report['attempts']['logical_runs'], 1)
        self.assertEqual(report['attempts']['retried_logical_runs'], 1)
        self.assertEqual(report['attempts']['adopted_attempt_histogram'], {'2': 1})
        self.assertEqual(report['headline_core']['UA']['denominator'], 1)
        self.assertEqual(report['usage_all_attempts']['llm_calls'], 6)
        self.assertAlmostEqual(
            report['usage_all_attempts']['list_price_cost_usd'], 0.000054)

    def test_confirmation_stability_and_legacy_compatible_mapping(self):
        attack = 'hijacking_answer_mapping.agent.v1'
        rows = [
            row('m1', attack, repetition=1, utility_success=True, attack_success=False),
            row('m1', attack, phase='confirmation', repetition=2,
                utility_success=False, attack_success=False),
            row('m1', attack, phase='confirmation', repetition=3,
                utility_success=True, attack_success=False),
            row('m1', attack, mas_id='legacy_debate', utility_success=True,
                attack_success=True),
            row('m1', attack, mas_id='legacy_debate', phase='confirmation',
                repetition=2, utility_success=True, attack_success=True),
            row('m1', attack, mas_id='legacy_debate', phase='confirmation',
                repetition=3, utility_success=True, attack_success=True),
        ]
        rows[1]['raw_response'] = 'changed'
        for legacy in rows[3:]:
            legacy['raw_response'] = 'legacy-stable'
        report = self.aggregate(rows)
        stability = report['confirmation_stability']
        # The same task/attack in another MAS is a distinct confirmation condition.
        self.assertEqual(stability['complete_conditions'], 2)
        self.assertEqual(stability['response_changed']['count'], 1)
        self.assertEqual(stability['utility_changed']['count'], 1)
        self.assertEqual(stability['attack_changed']['count'], 0)
        # The common aggregator accepts a non-CrewAI MAS/topology mapping.
        self.assertIn('legacy_debate', report['by_system'])


if __name__ == '__main__':
    unittest.main()
