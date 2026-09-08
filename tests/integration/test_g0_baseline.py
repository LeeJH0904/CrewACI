"""Offline baseline regressions; these do not certify G1/G2 or model quality."""

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from aciarena.agent_components.base_agent import BaseAgent
from aciarena.attacks.hijacking_attack import AnswerMappingAgent
from aciarena.evaluation.task import CodeTask, MathTask
from aciarena.mas.base_mas import BaseMAS
from aciarena.mas.crewai.sequential_mas import CrewAISequentialNoDelegation
from aciarena.mas.self_consistency.self_consistency_mas import SelfConsistency
from aciarena.utils.factory import ATTACK_CLASS_REGISTRY


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / 'tests/golden/g0_baseline.json').read_text())


class ScriptedLLM:
    """Snapshot real Agent inputs while replacing only the model boundary."""

    def __init__(self, agent, responses, calls):
        self.agent = agent
        self.responses = responses
        self.calls = calls
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, messages):
        self.calls.append((self.agent.name, copy.deepcopy(messages)))
        response = self.responses[self.agent.name]
        if isinstance(response, Exception):
            raise response
        return response


class BaselineTests(unittest.TestCase):
    def setUp(self):
        # A new code path must not accidentally create a real provider client.
        guard = patch(
            'aciarena.agent_components.base_agent.get_llm',
            side_effect=AssertionError('Real LLM initialization in offline test'),
        )
        guard.start()
        self.addCleanup(guard.stop)
        self.responses = {}
        self.calls = []

        def init_llm(agent, config):
            return ScriptedLLM(agent, self.responses, self.calls)

        backend = patch.object(BaseAgent, 'init_llm', init_llm)
        backend.start()
        self.addCleanup(backend.stop)

    def make_task(self, domain):
        fixture = FIXTURES[domain]
        data = (ROOT / fixture['dataset']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), fixture['dataset_sha256'])
        row = json.loads(data)[fixture['source_index']]
        task_class = MathTask if domain == 'math' else CodeTask
        return task_class(query=row['problem'], ground_truth=row['answer'])

    def verify_task(self, task):
        if isinstance(task, CodeTask):
            return task.verify(timeout=2.0)
        return task.verify()

    def check_legacy(self, domain):
        """Exercise the existing MAS -> response -> real verifier path."""
        for outcome in ('correct', 'incorrect'):
            with self.subTest(domain=domain, outcome=outcome):
                self.calls.clear()
                task = self.make_task(domain)
                answer = FIXTURES[domain]['responses'][outcome]
                self.responses.update(sc=answer, aggregate=answer)
                mas = SelfConsistency(llm_config={}, logger=Mock())
                result = mas.run(task.get_query())
                task.set_answer(result)
                self.assertEqual(
                    self.verify_task(task),
                    FIXTURES[domain]['expected_utility'][outcome],
                )
                self.assertEqual([name for name, _ in self.calls], ['sc'] * 5 + ['aggregate'])

    def test_existing_mas_math_correct_and_incorrect(self):
        self.check_legacy('math')

    def test_existing_mas_code_correct_and_incorrect(self):
        self.check_legacy('code')

    def test_sequential_context_hooks_and_final_output(self):
        self.responses.update(solver='draft marker', reviewer='review marker', finalizer='320')
        task = self.make_task('math')
        mas = CrewAISequentialNoDelegation(llm_config={})
        hooks = []
        for name, agent in mas.agents.items():
            def pre(query, name=name):
                hooks.append((name, 'pre'))
                return query

            def post(response, name=name):
                hooks.append((name, 'post'))
                return response

            agent.pre_step = pre
            agent.post_step = post

        result = mas.run(task.get_query())
        self.assertEqual([name for name, _ in self.calls], ['solver', 'reviewer', 'finalizer'])
        self.assertEqual(hooks, [
            ('solver', 'pre'), ('solver', 'post'),
            ('reviewer', 'pre'), ('reviewer', 'post'),
            ('finalizer', 'pre'), ('finalizer', 'post'),
        ])
        for _, messages in self.calls:
            self.assertIn(task.get_query(), messages[-1]['content'])
        self.assertIn('draft marker', self.calls[1][1][-1]['content'])
        self.assertIn('draft marker', self.calls[2][1][-1]['content'])
        self.assertIn('review marker', self.calls[2][1][-1]['content'])
        self.assertEqual(result['response'], '320')
        task.set_answer(result)
        self.assertEqual(task.verify(), 1.0)

    def test_sequential_code_output_reaches_real_verifier(self):
        task = self.make_task('code')
        answer = FIXTURES['code']['responses']['correct']
        self.responses.update(solver=answer, reviewer='Looks correct.', finalizer=answer)
        result = CrewAISequentialNoDelegation(llm_config={}).run(task.get_query())
        task.set_answer(result)
        self.assertEqual(self.verify_task(task), 1.0)

    def test_effective_profile_reaches_system_input(self):
        self.responses.update(solver='draft', reviewer='review', finalizer='answer')
        mas = CrewAISequentialNoDelegation(llm_config={})
        mas.get_agent('solver').profile = 'effective profile marker'
        mas.run('task')
        self.assertEqual(self.calls[0][1][0], {
            'role': 'system', 'content': 'effective profile marker',
        })
        fresh = CrewAISequentialNoDelegation(llm_config={})
        self.assertNotIn('effective profile marker', fresh.get_agent('solver').profile)
        self.assertEqual(len(fresh.get_agent('solver').memory.conversation), 1)

    def test_model_error_is_not_echoed_or_replaced_with_success(self):
        self.responses.update(solver='draft', reviewer=RuntimeError('mock provider failure'))
        mas = CrewAISequentialNoDelegation(llm_config={})
        with self.assertRaisesRegex(RuntimeError, 'mock provider failure'):
            mas.run('task')
        self.assertEqual([name for name, _ in self.calls], ['solver', 'reviewer'])

    def test_base_agent_tools_are_not_shared(self):
        first, second = BaseAgent({}), BaseAgent({})
        first.tools.append('marker')
        self.assertEqual(second.tools, [])

    def test_base_mas_default_targets_are_not_shared(self):
        class MinimalMAS(BaseMAS):
            def init_agents(self):
                return {}

            def bootstrap(self, query):
                return {}, True

            def step(self, args):
                return args, True

            def conclude(self, args):
                return args

        first, second = MinimalMAS({}), MinimalMAS({})
        first.malicious_agents.append('marker')
        self.assertEqual(second.malicious_agents, [])

    def test_answer_mapping_profile_registered_once(self):
        classes = ATTACK_CLASS_REGISTRY['hijacking_math']
        matches = [cls for cls in classes if cls.__name__ == 'AnswerMappingAgent']
        self.assertEqual(matches, [AnswerMappingAgent])


if __name__ == '__main__':
    unittest.main()
