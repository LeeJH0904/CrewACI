"""G3 calibration contract tests; no external model API is called."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aciarena.agent_components.base_agent import BaseAgent
from native_reference.calibration_contract import (
    CalibrationStore,
    AGENT_SPECS,
    build_record,
    load_calibration_tasks,
    load_model_config,
    utc_now,
)
from native_reference.compare_calibration import _messages_text, assess_record, build_report
from native_reference.reconstructed_adapter import run_reconstructed


class ScriptedLLM:
    def __init__(self, name, outputs):
        self.name = name
        self.outputs = outputs
        self.input_tokens = 0
        self.output_tokens = 0

    def call_llm(self, messages, *args, **kwargs):
        self.input_tokens += 1
        self.output_tokens += 1
        return self.outputs[self.name]


def synthetic_record(implementation):
    query = "Return the number 3."
    task = {
        "task_id": "math_test",
        "task_domain": "math",
        "query": query,
        "ground_truth": "3",
    }
    outputs = [
        {"task": "solve", "agent": "solver", "raw": "draft 3"},
        {"task": "review", "agent": "reviewer", "raw": "review 3"},
        {"task": "finalize", "agent": "finalizer", "raw": "3"},
    ]
    calls = [
        {"seq": 1, "agent": "solver", "messages": [{"content": query}], "response": "draft 3"},
        {"seq": 2, "agent": "reviewer", "messages": [{"content": query + " draft 3"}], "response": "review 3"},
        {"seq": 3, "agent": "finalizer", "messages": [{"content": query + " draft 3 review 3"}], "response": "3"},
    ]
    now = utc_now()
    return build_record(
        experiment_id="g3-test",
        implementation=implementation,
        task=task,
        runtime_version="test",
        model_config=load_model_config(),
        started_at=now,
        finished_at=now,
        latency_ms=0.0,
        status="success",
        raw_response="3",
        response_agent="finalizer",
        task_outputs=outputs,
        llm_calls=calls,
        usage=None,
    )


class G3CalibrationTests(unittest.TestCase):
    def test_manifest_selects_ten_balanced_tasks(self):
        tasks = load_calibration_tasks()
        self.assertEqual(len(tasks), 10)
        self.assertEqual(sum(task["task_domain"] == "math" for task in tasks), 5)
        self.assertEqual(sum(task["task_domain"] == "code" for task in tasks), 5)

    def test_reconstructed_adapter_records_order_context_and_source(self):
        outputs = {"solver": "draft marker", "reviewer": "review marker", "finalizer": "320"}

        def init_llm(agent, config):
            return ScriptedLLM(agent.name, outputs)

        task = {
            "task_id": "math_test",
            "task_domain": "math",
            "query": "original marker",
            "ground_truth": "320",
        }
        with patch.object(BaseAgent, "init_llm", init_llm):
            record = run_reconstructed(
                experiment_id="g3-test", task=task, model_config=load_model_config()
            )
        self.assertEqual(record["status"], "success")
        self.assertEqual([call["agent"] for call in record["llm_calls"]],
                         ["solver", "reviewer", "finalizer"])
        self.assertIn("draft marker", str(record["llm_calls"][1]["messages"]))
        self.assertIn("review marker", str(record["llm_calls"][2]["messages"]))
        self.assertEqual(record["raw_response"], "320")
        self.assertEqual(record["response_agent"], "finalizer")
        self.assertEqual(record["agents"], list(copy.deepcopy(AGENT_SPECS)))

    def test_store_rejects_duplicate_task(self):
        record = synthetic_record("reconstructed")
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory), "reconstructed")
            store.append(record)
            with self.assertRaisesRegex(ValueError, "already recorded"):
                store.append(record)
            self.assertEqual(store.read(), [record])

    def test_comparison_recomputes_utility_and_contract_evidence(self):
        rows = {
            "reconstructed": [synthetic_record("reconstructed")],
            "native": [synthetic_record("native")],
        }
        report = build_report(rows, ["math_test"])
        self.assertTrue(report["gate_passed"], report)
        self.assertEqual(report["utility_disagreements"], 0)
        self.assertEqual(report["utility_comparable_pairs"], 1)
        self.assertEqual(report["utility_uncomparable_pairs"], 0)
        for implementation in rows:
            self.assertEqual(report["summary"][implementation]["utility_successes"], 1)
            self.assertEqual(report["summary"][implementation]["context_contract_passed"], 1)

    def test_parse_unknown_remains_in_completed_denominator(self):
        rows = {
            "reconstructed": [synthetic_record("reconstructed")],
            "native": [synthetic_record("native")],
        }
        rows["native"][0]["raw_response"] = "not a number"
        rows["native"][0]["task_outputs"][-1]["raw"] = "not a number"
        report = build_report(rows, ["math_test"])
        native = report["summary"]["native"]
        self.assertEqual(native["parse_denominator"], 1)
        self.assertEqual(native["parsed"], 0)
        self.assertEqual(native["parse_rate"], 0.0)
        self.assertFalse(report["gate_passed"])

    def test_comparison_rejects_canonical_task_drift(self):
        rows = {
            "reconstructed": [synthetic_record("reconstructed")],
            "native": [synthetic_record("native")],
        }
        canonical = [{
            "task_id": "math_test",
            "task_domain": "math",
            "query": "Return the number 3.",
            "ground_truth": "4",
        }]
        report = build_report(rows, canonical)
        self.assertFalse(report["gate_passed"])
        self.assertIn(
            "reconstructed: canonical task drift for math_test", report["errors"]
        )

    def test_humaneval_parse_uses_prompt_plus_extracted_completion(self):
        row = synthetic_record("reconstructed")
        row["task_domain"] = "code"
        row["ground_truth"] = {
            "prompt": "def answer():\n",
            "test": "def check(candidate): assert candidate() == 3",
            "entry_point": "answer",
        }
        row["raw_response"] = "def answer():\n    return 3"
        row["task_outputs"][-1]["raw"] = row["raw_response"]
        with patch("native_reference.compare_calibration.verify_code", return_value=True):
            assessment = assess_record(row)
        self.assertTrue(assessment["parse_success"])
        self.assertEqual(assessment["utility_status"], "valid")
        self.assertTrue(assessment["utility_success"])

    def test_context_evidence_preserves_multiline_message_content(self):
        call = {"messages": [{"role": "user", "content": "first line\nsecond line"}]}
        self.assertIn("first line\nsecond line", _messages_text(call))


if __name__ == "__main__":
    unittest.main()
