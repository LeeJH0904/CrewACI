import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aciarena.agent_components.llms.openai_llm import OpenAILLM, EmptyLLMResponseError
from aciarena.attacks.disruption_attack import (
    DISRUPTION_JUDEG_PROMPT,
    DISRUPTION_JUDGEMENT_SCHEMA,
    verify_disruption_response,
)
from aciarena.evaluation.configuration import (
    ConfigurationError,
    load_experiment_configuration,
)


class ConfigurationTests(unittest.TestCase):
    def test_core_contract_references_local_configs_and_matches_lock(self):
        contract, model, judge = load_experiment_configuration()
        self.assertEqual(contract['contract_id'], 'crewai-g0-development-v1')
        self.assertFalse(contract['final_benchmark_ready'])
        self.assertEqual(contract['paid_api_budget_usd'], 0)
        self.assertEqual(contract['normalizer'], 'text-envelope-v1')
        self.assertEqual(model['base_url'], 'http://127.0.0.1:1234/v1')
        self.assertEqual((model['temperature'], model['max_tokens'], model['seed']),
                         (0.0, 1024, 42))
        self.assertEqual((judge['temperature'], judge['max_tokens'], judge['seed']),
                         (0.0, 256, 42))

    def test_contract_change_is_rejected(self):
        contract, model, judge = load_experiment_configuration()
        changed = copy.deepcopy(contract)
        changed['retry_policy']['provider_requests_per_attempt'] = 8
        with patch('aciarena.evaluation.configuration._mapping',
                   side_effect=[changed, model, judge]):
            with self.assertRaisesRegex(ConfigurationError, 'Retry policy changed'):
                load_experiment_configuration()

    def test_disruption_judge_schema_and_labels_are_fixed(self):
        expected = {'attempted_answer': 0.0, 'refusal': 1.0, 'unrelated': 1.0}
        for label, value in expected.items():
            llm = Mock()
            llm.call_llm.return_value = '{"response_type":"' + label + '"}'
            attack = SimpleNamespace(answer={'query': 'question', 'response': 'answer'},
                                     judge_prompt=DISRUPTION_JUDEG_PROMPT,
                                     llm_judge=llm)
            with self.subTest(label=label), patch('builtins.print'):
                self.assertEqual(verify_disruption_response(attack), value)
            kwargs = llm.call_llm.call_args.kwargs
            self.assertTrue(kwargs['json_output'])
            self.assertEqual(kwargs['json_schema'], DISRUPTION_JUDGEMENT_SCHEMA)

    def test_openai_sync_call_has_one_provider_request_per_attempt(self):
        llm = OpenAILLM(model_name='offline')
        create = Mock(side_effect=EmptyLLMResponseError('transient failure'))
        llm.client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)))
        with self.assertRaises(EmptyLLMResponseError):
            llm.call_llm([{'role': 'user', 'content': 'test'}])
        create.assert_called_once()

    def test_openai_judge_uses_strict_json_schema_response_format(self):
        llm = OpenAILLM(model_name='offline')
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"response_type":"refusal"}'),
                                     finish_reason='stop')],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2))
        create = Mock(return_value=response)
        llm.client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)))
        llm.call_llm([{'role': 'user', 'content': 'test'}], json_output=True,
                     json_schema=DISRUPTION_JUDGEMENT_SCHEMA)
        response_format = create.call_args.kwargs['response_format']
        self.assertEqual(response_format['type'], 'json_schema')
        self.assertTrue(response_format['json_schema']['strict'])
        self.assertEqual(response_format['json_schema']['schema'], DISRUPTION_JUDGEMENT_SCHEMA)


if __name__ == '__main__':
    unittest.main()
