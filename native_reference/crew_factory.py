"""Official CrewAI 1.15.21 Sequential factory for G3 only."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from importlib.metadata import version
import os
from pathlib import Path
import signal
import time
from typing import Any

from .calibration_contract import (
    AGENT_SPECS,
    NATIVE_CREWAI_VERSION,
    build_record,
    render_tasks,
    utc_now,
)


def _native_imports():
    installed = version("crewai")
    if installed != NATIVE_CREWAI_VERSION:
        raise RuntimeError(
            f"G3 requires crewai=={NATIVE_CREWAI_VERSION}, found {installed}"
        )
    from crewai import Agent, Crew, LLM, Process, Task
    from crewai.hooks import (
        clear_all_llm_call_hooks,
        register_after_llm_call_hook,
        register_before_llm_call_hook,
    )
    return Agent, Crew, LLM, Process, Task, (
        clear_all_llm_call_hooks,
        register_before_llm_call_hook,
        register_after_llm_call_hook,
    )


def _model(model_config: dict[str, Any], LLM):
    api_key = model_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for native calibration")
    return LLM(
        model=model_config["model_name"],
        provider="openai",
        base_url=model_config["base_url"],
        api_key=api_key,
        temperature=model_config["temperature"],
        max_tokens=model_config["max_tokens"],
        seed=model_config["seed"],
        timeout=120,
    )


@contextmanager
def _task_deadline(seconds: int = 180):
    """Bound one official runtime task without changing CrewAI internals."""
    previous = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise TimeoutError(f"Official CrewAI calibration exceeded {seconds}s")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def run_native(*, experiment_id: str, task: dict[str, Any],
               model_config: dict[str, Any]) -> dict[str, Any]:
    storage = Path(os.environ.setdefault(
        "CREWAI_STORAGE_DIR", str(Path("/tmp") / "crewai-g3-reference")
    ))
    storage.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")
    Agent, Crew, LLM, Process, Task, hooks = _native_imports()
    clear_hooks, register_before, register_after = hooks
    clear_hooks()

    started_at = utc_now()
    clock = time.monotonic()
    calls: list[dict[str, Any]] = []
    task_outputs: list[dict[str, Any]] = []
    output = None
    crew = None
    rendered = []
    native_tasks = {}
    error = None
    role_to_name = {spec["role"]: spec["name"] for spec in AGENT_SPECS}

    def before_call(context):
        calls.append({
            "seq": len(calls) + 1,
            "agent": role_to_name.get(getattr(context.agent, "role", ""),
                                      getattr(context.agent, "role", "unknown")),
            "messages": copy.deepcopy(context.messages),
            "response": None,
        })

    def after_call(context):
        for call in reversed(calls):
            if call["response"] is None:
                call["response"] = context.response
                break

    register_before(before_call)
    register_after(after_call)
    try:
        agents = {}
        for spec in AGENT_SPECS:
            agents[spec["name"]] = Agent(
                role=spec["role"],
                goal=spec["goal"],
                backstory=spec["backstory"],
                allow_delegation=False,
                tools=[],
                llm=_model(model_config, LLM),
                memory=False,
                cache=False,
                reasoning=False,
                planning=False,
                max_iter=1,
                max_retry_limit=0,
                verbose=False,
            )
            actual = {
                "name": spec["name"],
                "role": agents[spec["name"]].role,
                "goal": agents[spec["name"]].goal,
                "backstory": agents[spec["name"]].backstory,
                "allow_delegation": agents[spec["name"]].allow_delegation,
            }
            if actual != spec:
                raise ValueError(f"Native Agent contract drift: {spec['name']}")
        rendered = render_tasks(task["query"])
        for spec in rendered:
            context = [native_tasks[name] for name in spec["context"]]
            native_tasks[spec["name"]] = Task(
                name=spec["name"],
                description=spec["description"],
                expected_output=spec["expected_output"],
                agent=agents[spec["agent"]],
                context=context,
            )
        crew = Crew(
            agents=[agents[spec["name"]] for spec in AGENT_SPECS],
            tasks=[native_tasks[spec["name"]] for spec in rendered],
            process=Process.sequential,
            memory=False,
            cache=False,
            planning=False,
            verbose=False,
            share_crew=False,
        )
        with _task_deadline():
            output = crew.kickoff()
        usage = crew.usage_metrics.model_dump() if crew.usage_metrics is not None else None
    except Exception as exc:
        error = exc
        usage = crew.usage_metrics.model_dump() if crew and crew.usage_metrics else None
    finally:
        clear_hooks()

    for spec in rendered:
        item = native_tasks.get(spec["name"])
        task_outputs.append({
            "task": spec["name"],
            "agent": spec["agent"],
            "raw": item.output.raw if item is not None and item.output is not None else None,
        })

    raw = output.raw if output is not None else None
    return build_record(
        experiment_id=experiment_id,
        implementation="native",
        task=task,
        runtime_version=version("crewai"),
        model_config=model_config,
        started_at=started_at,
        finished_at=utc_now(),
        latency_ms=(time.monotonic() - clock) * 1000,
        status="error" if error else "success",
        raw_response=raw,
        response_agent="finalizer" if raw is not None else None,
        task_outputs=task_outputs,
        llm_calls=calls,
        usage=usage,
        error=error,
    )
