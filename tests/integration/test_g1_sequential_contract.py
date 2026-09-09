"""G1 mock contract tests; no model API or task verifier is invoked."""

import copy
import unittest
from unittest.mock import patch

from aciarena.agent_components.base_agent import BaseAgent
from aciarena.mas.crewai.schemas import SequentialSuccessResult
from aciarena.mas.crewai.sequential_mas import CrewAISequentialNoDelegation


class ScriptedLLM:
    def __init__(self, name, outputs, calls):
        self.name = name
        self.outputs = outputs
        self.calls = calls
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, messages):
        self.calls.append((self.name, copy.deepcopy(messages)))
        return self.outputs[self.name]


class G1SequentialContractTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.outputs = {
            "solver": "draft marker",
            "reviewer": "review marker",
            "finalizer": " \ufeff320\r\n ",
        }

        def init_llm(agent, config):
            return ScriptedLLM(agent.name, self.outputs, self.calls)

        backend = patch.object(BaseAgent, "init_llm", init_llm)
        backend.start()
        self.addCleanup(backend.stop)

    def test_order_context_finalizer_source_and_standard_contract(self):
        mas = CrewAISequentialNoDelegation(llm_config={})
        hooks = []
        for name, agent in mas.agents.items():
            agent.pre_step = lambda value, name=name: hooks.append((name, "pre")) or value
            agent.post_step = lambda value, name=name: hooks.append((name, "post")) or value

        result = mas.run("original task marker")

        self.assertEqual(set(result), {
            "raw_response", "response", "response_agent", "conversation", "status",
        })
        self.assertEqual(result["raw_response"], " \ufeff320\r\n ")
        self.assertEqual(result["response"], "320")
        self.assertEqual(result["response_agent"], "finalizer")
        self.assertEqual(result["status"], "success")
        self.assertEqual([name for name, _ in self.calls], ["solver", "reviewer", "finalizer"])
        self.assertEqual(hooks, [
            ("solver", "pre"), ("solver", "post"),
            ("reviewer", "pre"), ("reviewer", "post"),
            ("finalizer", "pre"), ("finalizer", "post"),
        ])
        self.assertIn("original task marker", self.calls[1][1][-1]["content"])
        self.assertIn("draft marker", self.calls[1][1][-1]["content"])
        self.assertIn("original task marker", self.calls[2][1][-1]["content"])
        self.assertIn("draft marker", self.calls[2][1][-1]["content"])
        self.assertIn("review marker", self.calls[2][1][-1]["content"])
        self.assertEqual(
            [(event["turn"], event["sender"], event["receiver"], event["phase"])
             for event in result["conversation"]],
            [
                (0, "user", "solver", "task"),
                (1, "solver", "reviewer", "context"),
                (2, "reviewer", "finalizer", "review"),
                (3, "finalizer", "user", "final"),
            ],
        )
        self.assertEqual(result["conversation"][-1]["content"], result["raw_response"])
        invalid = copy.deepcopy(result)
        invalid["conversation"][1], invalid["conversation"][2] = (
            invalid["conversation"][2],
            invalid["conversation"][1],
        )
        with self.assertRaisesRegex(ValueError, "routes or order"):
            SequentialSuccessResult.model_validate(invalid)


if __name__ == "__main__":
    unittest.main()
