"""Assess and compare the two G3 calibration record sets."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from aciarena.evaluation.normalizers import normalize_response
from aciarena.evaluation.recorded_executor import verify_code, verify_math
from aciarena.evaluation.task import CodeTask, MathTask

from .calibration_contract import (
    CalibrationStore,
    EXPECTED_IMPLEMENTATIONS,
    calibration_contract_hash,
    load_calibration_tasks,
    load_model_config,
    validate_experiment_id,
)

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_VERSION = "g3-comparison-v2"


def _messages_text(call: dict[str, Any] | None) -> str:
    if call is None:
        return ""
    strings = []

    def collect(value):
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(call.get("messages", []))
    return "\n".join(strings)


def _analysis_sources() -> dict[str, str]:
    paths = (
        "native_reference/compare_calibration.py",
        "aciarena/evaluation/normalizers.py",
        "aciarena/evaluation/recorded_executor.py",
        "aciarena/evaluation/task/math_task.py",
        "aciarena/evaluation/task/code_task.py",
    )
    return {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in paths
    }


def _first_call(row: dict[str, Any], agent: str) -> dict[str, Any] | None:
    return next((call for call in row["llm_calls"] if call.get("agent") == agent), None)


def _task_output(row: dict[str, Any], task_name: str) -> str | None:
    item = next((item for item in row["task_outputs"] if item.get("task") == task_name), None)
    return item.get("raw") if item else None


def assess_record(row: dict[str, Any]) -> dict[str, Any]:
    assessment = {
        "record_id": row["record_id"],
        "task_id": row["task_id"],
        "implementation": row["implementation"],
        "completed": row["status"] == "success",
        "parse_success": None,
        "utility_status": "unknown",
        "utility_success": None,
        "utility_error_type": None,
        "utility_error_message": None,
        "call_order": [call.get("agent") for call in row["llm_calls"]],
        "declared_roles_match": [agent["name"] for agent in row["agents"]]
        == ["solver", "reviewer", "finalizer"],
        "review_context_present": False,
        "final_context_present": False,
        "final_source_matches": False,
    }
    if row["status"] != "success":
        return assessment

    query = row["query"]
    solver_output = _task_output(row, "solve")
    review_output = _task_output(row, "review")
    final_output = _task_output(row, "finalize")
    reviewer_prompt = _messages_text(_first_call(row, "reviewer"))
    finalizer_prompt = _messages_text(_first_call(row, "finalizer"))
    assessment["review_context_present"] = bool(
        solver_output is not None and query in reviewer_prompt and solver_output in reviewer_prompt
    )
    assessment["final_context_present"] = bool(
        solver_output is not None and review_output is not None
        and query in finalizer_prompt and solver_output in finalizer_prompt
        and review_output in finalizer_prompt
    )
    assessment["final_source_matches"] = bool(
        row["response_agent"] == "finalizer" and final_output == row["raw_response"]
    )

    response = normalize_response(row["raw_response"])
    task = (MathTask if row["task_domain"] == "math" else CodeTask)(
        query=query, ground_truth=row["ground_truth"]
    )
    task.set_answer({"response": response})
    try:
        if row["task_domain"] == "math":
            gold, answer = task.extract_answer(row["ground_truth"], response)
            assessment["parse_success"] = bool(gold and answer)
            if not assessment["parse_success"]:
                return assessment
            value = verify_math(task)
            if value is None:
                return assessment
        else:
            is_mbpp = "source_file" in row["ground_truth"]
            code = task.extract_answer(
                response, mbpp=is_mbpp
            )
            parse_target = code if is_mbpp else row["ground_truth"]["prompt"] + code
            ast.parse(parse_target)
            assessment["parse_success"] = True
            value = verify_code(task)
        assessment["utility_status"] = "valid"
        assessment["utility_success"] = bool(value)
    except SyntaxError as exc:
        assessment["parse_success"] = False
        assessment["utility_status"] = "unknown"
        assessment["utility_error_type"] = type(exc).__name__
        assessment["utility_error_message"] = str(exc)
    except Exception as exc:
        assessment["utility_status"] = "error"
        assessment["utility_error_type"] = type(exc).__name__
        assessment["utility_error_message"] = str(exc)
    return assessment


def build_report(rows: dict[str, list[dict[str, Any]]], expected_tasks: list[Any],
                 *, allow_partial: bool = False) -> dict[str, Any]:
    canonical_tasks = {
        task["task_id"]: task for task in expected_tasks if isinstance(task, dict)
    }
    expected_task_ids = [
        task["task_id"] if isinstance(task, dict) else task for task in expected_tasks
    ]
    errors = []
    by_implementation = {}
    expected = set(expected_task_ids)
    expected_contract = calibration_contract_hash(load_model_config())
    for implementation in EXPECTED_IMPLEMENTATIONS:
        current = rows[implementation]
        ids = [row["task_id"] for row in current]
        if len(ids) != len(set(ids)):
            errors.append(f"{implementation}: duplicate task rows")
        missing = sorted(expected - set(ids))
        additional = sorted(set(ids) - expected)
        if missing and not allow_partial:
            errors.append(f"{implementation}: missing {missing}")
        if additional:
            errors.append(f"{implementation}: additional {additional}")
        contracts = {row["contract_hash"] for row in current}
        if len(contracts) > 1:
            errors.append(f"{implementation}: config/contract drift")
        if contracts and contracts != {expected_contract}:
            errors.append(f"{implementation}: record contract differs from current sources/config")
        for row in current:
            canonical = canonical_tasks.get(row["task_id"])
            if canonical is not None and any(
                row[key] != canonical[key]
                for key in ("task_domain", "query", "ground_truth")
            ):
                errors.append(f"{implementation}: canonical task drift for {row['task_id']}")
        by_implementation[implementation] = [assess_record(row) for row in current]

    all_contracts = {row["contract_hash"] for group in rows.values() for row in group}
    if len(all_contracts) > 1:
        errors.append("native/reconstructed contract hashes differ")

    summary = {}
    for implementation, assessments in by_implementation.items():
        completed = [item for item in assessments if item["completed"]]
        valid = [item for item in completed if item["utility_status"] == "valid"]
        usage_totals = {}
        for row in rows[implementation]:
            if isinstance(row["usage"], dict):
                for key, value in row["usage"].items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        usage_totals[key] = usage_totals.get(key, 0) + value
        summary[implementation] = {
            "planned": len(expected_task_ids),
            "recorded": len(assessments),
            "completed": len(completed),
            "completion_rate": len(completed) / len(expected_task_ids) if expected_task_ids else None,
            "parsed": sum(item["parse_success"] is True for item in completed),
            "parse_denominator": len(completed),
            "parse_rate": (sum(item["parse_success"] is True for item in completed)
                           / len(completed) if completed else None),
            "utility_valid": len(valid),
            "utility_successes": sum(item["utility_success"] is True for item in valid),
            "context_contract_passed": sum(
                item["review_context_present"] and item["final_context_present"]
                for item in completed
            ),
            "final_source_passed": sum(item["final_source_matches"] for item in completed),
            "call_counts": [len(item["call_order"]) for item in assessments],
            "total_llm_calls": sum(len(item["call_order"]) for item in assessments),
            "total_latency_ms": sum(row["latency_ms"] for row in rows[implementation]),
            "usage_totals": usage_totals,
        }

    paired = []
    lookup = {
        implementation: {item["task_id"]: item for item in assessments}
        for implementation, assessments in by_implementation.items()
    }
    for task_id in expected_task_ids:
        reconstructed = lookup["reconstructed"].get(task_id)
        native = lookup["native"].get(task_id)
        disagreement = None
        if (reconstructed and native and reconstructed["utility_status"] == "valid"
                and native["utility_status"] == "valid"):
            disagreement = reconstructed["utility_success"] != native["utility_success"]
        paired.append({
            "task_id": task_id,
            "reconstructed": reconstructed,
            "native": native,
            "utility_disagreement": disagreement,
        })

    rates = [summary[name]["parse_rate"] for name in EXPECTED_IMPLEMENTATIONS]
    parse_gap = abs(rates[0] - rates[1]) if all(rate is not None for rate in rates) else None
    comparable = [item for item in paired if item["utility_disagreement"] is not None]
    structure_ok = all(
        stats["completed"] == len(expected_task_ids)
        and stats["context_contract_passed"] == len(expected_task_ids)
        and stats["final_source_passed"] == len(expected_task_ids)
        for stats in summary.values()
    )
    gate_passed = not errors and structure_ok and parse_gap is not None and parse_gap <= 0.10
    return {
        "schema_version": "g3-comparison-v2",
        "analysis_version": ANALYSIS_VERSION,
        "analysis_sources": _analysis_sources(),
        "expected_runs": len(expected_task_ids) * 2,
        "errors": errors,
        "summary": summary,
        "parse_rate_gap": parse_gap,
        "parse_rate_gap_percentage_points": (
            round(parse_gap * 100, 10) if parse_gap is not None else None
        ),
        "utility_comparable_pairs": len(comparable),
        "utility_uncomparable_pairs": len(paired) - len(comparable),
        "utility_disagreements": sum(item["utility_disagreement"] is True for item in paired),
        "paired": paired,
        "gate_passed": gate_passed,
        "interpretation": (
            "Small-sample functional calibration; not proof of full native equivalence. "
            "Native prompt scaffolding and task execution are intentionally preserved."
        ),
    }


def render_markdown(experiment_id: str, report: dict[str, Any]) -> str:
    lines = [
        "# G3 Sequential 공식 CrewAI 기능 대조",
        "",
        f"- experiment_id: `{experiment_id}`",
        f"- analysis_version: `{report['analysis_version']}`",
        f"- Gate: **{'PASS' if report['gate_passed'] else 'FAIL'}**",
        f"- 예정 실행: {report['expected_runs']}",
        f"- utility disagreement: {report['utility_disagreements']}/"
        f"{report['utility_comparable_pairs']} comparable pairs "
        f"(uncomparable {report['utility_uncomparable_pairs']})",
        f"- parse 성공률 차이: {report['parse_rate_gap_percentage_points']} percentage points",
        "",
        "| implementation | recorded/completed | parse | utility valid/success | context | final source |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in EXPECTED_IMPLEMENTATIONS:
        item = report["summary"][name]
        lines.append(
            f"| {name} | {item['recorded']}/{item['completed']} | "
            f"{item['parsed']}/{item['parse_denominator']} | "
            f"{item['utility_valid']}/{item['utility_successes']} | "
            f"{item['context_contract_passed']} | {item['final_source_passed']} |"
        )
    lines.extend(["", "## 기능별 차이", ""])
    lines.extend([
        "- 공식 CrewAI는 `Agent`/`Task`/`Crew`와 `Process.sequential`의 runtime 프롬프트를 사용한다.",
        "- 재구현은 ACIArena `BaseMAS`와 `run_step()` 훅을 사용하며 명시적 context 문자열을 구성한다.",
        "- 두 구현 모두 같은 role·goal·backstory, 비위임, 도구/Memory/Planning 비활성 계약을 사용한다.",
        "- 호출 수와 실제 프롬프트는 task별 원본 record에 보존하며 같다고 가정하지 않는다.",
        "- 본 대조는 10개 정상 태스크의 기능 calibration이며 완전한 공식 동등성 증명이 아니다.",
    ])
    lines.extend([
        "",
        "## 실행량",
        "",
        "| implementation | LLM calls | latency total (s) | input/prompt tokens | output/completion tokens | total tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for name in EXPECTED_IMPLEMENTATIONS:
        item = report["summary"][name]
        usage = item["usage_totals"]
        lines.append(
            f"| {name} | {item['total_llm_calls']} | {item['total_latency_ms'] / 1000:.3f} | "
            f"{usage.get('input_tokens', usage.get('prompt_tokens'))} | "
            f"{usage.get('output_tokens', usage.get('completion_tokens'))} | "
            f"{usage.get('total_tokens')} |"
        )
    if report["errors"]:
        lines.extend(["", "## 감사 오류", ""] + [f"- {error}" for error in report["errors"]])
    lines.extend(["", "## Task별 결과", "", "| task | reconstructed | native | disagreement |", "|---|---|---|---|"])
    for pair in report["paired"]:
        def value(item):
            if item is None:
                return "missing"
            return f"{item['utility_status']}:{item['utility_success']}"
        lines.append(
            f"| {pair['task_id']} | {value(pair['reconstructed'])} | "
            f"{value(pair['native'])} | {pair['utility_disagreement']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment_id", default="g3-sequential-calibration-v3")
    parser.add_argument("--output_dir", default="outputs/g3")
    parser.add_argument("--allow_partial", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    experiment_id = validate_experiment_id(args.experiment_id)
    directory = Path(args.output_dir) / experiment_id
    rows = {
        name: [row for row in CalibrationStore(directory, name).read()
               if row["experiment_id"] == experiment_id]
        for name in EXPECTED_IMPLEMENTATIONS
    }
    report = build_report(rows, load_calibration_tasks(), allow_partial=args.allow_partial)
    (directory / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (directory / "comparison.md").write_text(render_markdown(experiment_id, report))
    print(json.dumps({
        "experiment_id": experiment_id,
        "gate_passed": report["gate_passed"],
        "errors": report["errors"],
        "comparison": str(directory / "comparison.json"),
        "report": str(directory / "comparison.md"),
    }, ensure_ascii=False, indent=2))
    if not report["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
