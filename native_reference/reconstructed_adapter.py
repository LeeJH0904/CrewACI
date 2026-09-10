"""Adapter for the ACIArena CrewAI-style reconstruction."""

from __future__ import annotations

import copy
from importlib.metadata import version
import time
from typing import Any

from aciarena.mas.crewai.sequential_mas import CrewAISequentialNoDelegation

from .calibration_contract import AGENT_SPECS, build_record, utc_now


class RecordingLLM:
    def __init__(self, delegate: Any, agent_name: str, calls: list[dict[str, Any]]):
        self.delegate = delegate
        self.agent_name = agent_name
        self.calls = calls

    @property
    def input_tokens(self):
        return self.delegate.input_tokens

    @property
    def output_tokens(self):
        return self.delegate.output_tokens

    def call_llm(self, messages, *args, **kwargs):
        call = {
            "seq": len(self.calls) + 1,
            "agent": self.agent_name,
            "messages": copy.deepcopy(messages),
            "response": None,
        }
        self.calls.append(call)
        response = self.delegate.call_llm(messages, *args, **kwargs)
        call["response"] = response
        return response


def run_reconstructed(*, experiment_id: str, task: dict[str, Any],
                      model_config: dict[str, Any]) -> dict[str, Any]:
    started_at = utc_now()
    clock = time.monotonic()
    calls: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    result = None
    error = None
    try:
        mas = CrewAISequentialNoDelegation(llm_config=model_config, malicious_agents=[])
        for spec in AGENT_SPECS:
            agent = mas.agents.get(spec["name"])
            actual = {
                "name": getattr(agent, "name", None),
                "role": getattr(agent, "role", None),
                "goal": getattr(agent, "goal", None),
                "backstory": getattr(agent, "backstory", None),
                "allow_delegation": getattr(agent, "allow_delegation", None),
            }
            if actual != spec:
                raise ValueError(f"Reconstructed Agent contract drift: {spec['name']}")
        for name, agent in mas.agents.items():
            agent.llm = RecordingLLM(agent.llm, name, calls)
        result = mas.run(task["query"])
        conversation = result["conversation"]
        outputs = [
            {"task": "solve", "agent": "solver", "raw": conversation[1]["content"]},
            {"task": "review", "agent": "reviewer", "raw": conversation[2]["content"]},
            {"task": "finalize", "agent": "finalizer", "raw": conversation[3]["content"]},
        ]
        usage = mas.get_token_usage()
    except Exception as exc:
        error = exc
        usage = None
    return build_record(
        experiment_id=experiment_id,
        implementation="reconstructed",
        task=task,
        runtime_version=version("aciarena"),
        model_config=model_config,
        started_at=started_at,
        finished_at=utc_now(),
        latency_ms=(time.monotonic() - clock) * 1000,
        status="error" if error else "success",
        raw_response=result["raw_response"] if result else None,
        response_agent=result["response_agent"] if result else None,
        task_outputs=outputs,
        llm_calls=calls,
        usage=usage,
        error=error,
    )
