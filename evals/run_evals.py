"""
evals/run_evals.py — ARIA Agent Evaluation Harness
============================================================
Runs 25 scripted test cases across all 5 tools.
Scores three dimensions:
  1. tool_call_accuracy  — did the agent call the right tool?
  2. correct_args        — were the arguments correct?
  3. no_hallucination    — does the reply not invent facts not in tool output?

Usage:
    python -m evals.run_evals                    # uses GEMINI_API_KEY from .env
    python -m evals.run_evals --output results.json
    python -m evals.run_evals --fast             # skip TTS, text-only

Output: evals/results.json + summary table in terminal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.database import init_db
from backend.agent import run_agent_turn

# ─────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    user_message: str
    expected_tool: str | None          # None = no tool call expected
    expected_args_subset: dict         # must all be present in actual args
    must_contain: list[str]            # strings that should appear in reply
    must_not_contain: list[str]        # hallucination check patterns


TEST_CASES: list[TestCase] = [
    # ── lookup_order ──────────────────────────────────────────
    TestCase(
        id="LO-01",
        user_message="What is the status of order ORD-1234?",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-1234"},
        must_contain=["delivered", "alex"],
        must_not_contain=["ORD-9999", "not found"],
    ),
    TestCase(
        id="LO-02",
        user_message="Can you track my order ORD-5678?",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-5678"},
        must_contain=["transit", "maria"],
        must_not_contain=[],
    ),
    TestCase(
        id="LO-03",
        user_message="Where is ORD-9012?",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-9012"},
        must_contain=["processing", "james"],
        must_not_contain=[],
    ),
    TestCase(
        id="LO-04",
        user_message="I need details on order ORD-3456",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-3456"},
        must_contain=["cancelled", "sarah"],
        must_not_contain=[],
    ),
    TestCase(
        id="LO-05",
        user_message="Order ORD-9999 status please",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-9999"},
        must_contain=["not found"],
        must_not_contain=["delivered", "transit"],
    ),

    # ── trigger_refund ────────────────────────────────────────
    TestCase(
        id="RF-01",
        user_message="I want a refund for order ORD-1234, it arrived damaged",
        expected_tool="trigger_refund",
        expected_args_subset={"order_id": "ORD-1234"},
        must_contain=["refund", "REF-"],
        must_not_contain=["cannot", "not eligible"],
    ),
    TestCase(
        id="RF-02",
        user_message="Please refund ORD-3456, I changed my mind",
        expected_tool="trigger_refund",
        expected_args_subset={"order_id": "ORD-3456"},
        must_contain=["refund"],
        must_not_contain=[],
    ),
    TestCase(
        id="RF-03",
        user_message="I want to return order ORD-5678 for a refund",
        expected_tool="trigger_refund",
        expected_args_subset={"order_id": "ORD-5678"},
        must_contain=["cannot", "transit"],
        must_not_contain=["REF-"],  # should NOT be refunded (in transit)
    ),
    TestCase(
        id="RF-04",
        user_message="Refund ORD-9012 please",
        expected_tool="trigger_refund",
        expected_args_subset={"order_id": "ORD-9012"},
        must_contain=["cannot", "processing"],
        must_not_contain=["REF-"],
    ),

    # ── create_support_ticket ─────────────────────────────────
    TestCase(
        id="TK-01",
        user_message="My package from ORD-1234 came completely broken, I need this escalated urgently",
        expected_tool="create_support_ticket",
        expected_args_subset={"priority": "urgent"},
        must_contain=["TKT-", "urgent"],
        must_not_contain=[],
    ),
    TestCase(
        id="TK-02",
        user_message="I have a general billing question",
        expected_tool="create_support_ticket",
        expected_args_subset={},
        must_contain=["TKT-"],
        must_not_contain=[],
    ),
    TestCase(
        id="TK-03",
        user_message="Create a high priority ticket — my account was charged twice",
        expected_tool="create_support_ticket",
        expected_args_subset={"priority": "high"},
        must_contain=["TKT-", "hours"],
        must_not_contain=[],
    ),

    # ── check_loyalty_points ──────────────────────────────────
    TestCase(
        id="LP-01",
        user_message="How many loyalty points does customer CUST-001 have?",
        expected_tool="check_loyalty_points",
        expected_args_subset={"customer_id": "CUST-001"},
        must_contain=["2450", "gold"],
        must_not_contain=["not found"],
    ),
    TestCase(
        id="LP-02",
        user_message="What tier is customer CUST-004?",
        expected_tool="check_loyalty_points",
        expected_args_subset={"customer_id": "CUST-004"},
        must_contain=["platinum", "5100"],
        must_not_contain=[],
    ),
    TestCase(
        id="LP-03",
        user_message="Check points for CUST-999",
        expected_tool="check_loyalty_points",
        expected_args_subset={"customer_id": "CUST-999"},
        must_contain=["not found"],
        must_not_contain=["gold", "silver", "platinum"],
    ),

    # ── escalate_to_human ─────────────────────────────────────
    TestCase(
        id="ES-01",
        user_message="I want to speak to a human agent right now",
        expected_tool="escalate_to_human",
        expected_args_subset={},
        must_contain=["human", "agent", "queue"],
        must_not_contain=[],
    ),
    TestCase(
        id="ES-02",
        user_message="This is ridiculous, connect me to a real person",
        expected_tool="escalate_to_human",
        expected_args_subset={},
        must_contain=["human", "agent"],
        must_not_contain=[],
    ),

    # ── no tool needed ────────────────────────────────────────
    TestCase(
        id="NT-01",
        user_message="Hello, what can you help me with?",
        expected_tool=None,
        expected_args_subset={},
        must_contain=["order", "refund"],
        must_not_contain=["error", "exception"],
    ),
    TestCase(
        id="NT-02",
        user_message="What are your business hours?",
        expected_tool=None,
        expected_args_subset={},
        must_contain=[],
        must_not_contain=["ORD-", "TKT-"],
    ),

    # ── anti-hallucination ────────────────────────────────────
    TestCase(
        id="AH-01",
        user_message="Did I order a PlayStation 5?",
        expected_tool="lookup_order",
        expected_args_subset={},
        must_contain=[],
        must_not_contain=["PlayStation 5", "yes, you ordered"],
    ),
    TestCase(
        id="AH-02",
        user_message="My refund of $500 was promised — where is it?",
        expected_tool=None,
        expected_args_subset={},
        must_contain=[],
        must_not_contain=["$500", "yes, we promised"],
    ),

    # ── multi-turn context ────────────────────────────────────
    TestCase(
        id="MT-01",
        user_message="What was the total amount for order ORD-1234?",
        expected_tool="lookup_order",
        expected_args_subset={"order_id": "ORD-1234"},
        must_contain=["129.99"],
        must_not_contain=["84.99", "349.99"],
    ),
    TestCase(
        id="MT-02",
        user_message="How much would my refund be for ORD-1234?",
        expected_tool="trigger_refund",
        expected_args_subset={"order_id": "ORD-1234"},
        must_contain=["129.99"],
        must_not_contain=[],
    ),

    # ── edge cases ────────────────────────────────────────────
    TestCase(
        id="EC-01",
        user_message="ord 1234",  # lowercase, no dash
        expected_tool="lookup_order",
        expected_args_subset={},
        must_contain=[],   # may or may not find — just check no crash
        must_not_contain=["exception", "traceback"],
    ),
    TestCase(
        id="EC-02",
        user_message="x" * 500,   # very long input
        expected_tool=None,
        expected_args_subset={},
        must_contain=[],
        must_not_contain=["exception", "traceback"],
    ),
]


# ─────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    test_id: str
    user_message: str
    expected_tool: str | None
    actual_tool: str | None
    actual_args: dict
    reply_text: str
    tool_call_accuracy: bool
    correct_args: bool
    no_hallucination: bool
    passed: bool
    duration_ms: float
    error: str | None = None


def score_result(case: TestCase, actual_tool: str | None, actual_args: dict, reply: str) -> tuple[bool, bool, bool]:
    reply_lower = reply.lower()

    # 1. Tool call accuracy
    if case.expected_tool is None:
        tool_ok = actual_tool is None
    else:
        tool_ok = actual_tool == case.expected_tool

    # 2. Args subset check
    if case.expected_args_subset:
        args_ok = all(
            str(v).lower() in str(actual_args.get(k, "")).lower()
            for k, v in case.expected_args_subset.items()
        )
    else:
        args_ok = True

    # 3. No hallucination
    halluc_ok = not any(h.lower() in reply_lower for h in case.must_not_contain)

    # Bonus: must_contain check (penalizes if expected content missing)
    content_ok = all(mc.lower() in reply_lower for mc in case.must_contain) if case.must_contain else True

    return tool_ok, args_ok and content_ok, halluc_ok


async def run_single_case(case: TestCase) -> EvalResult:
    t0 = time.perf_counter()
    try:
        reply, tool_calls = await run_agent_turn([], case.user_message)
        duration_ms = (time.perf_counter() - t0) * 1000

        actual_tool = tool_calls[0].name if tool_calls else None
        actual_args = tool_calls[0].args if tool_calls else {}

        tool_ok, args_ok, halluc_ok = score_result(case, actual_tool, actual_args, reply)
        passed = tool_ok and args_ok and halluc_ok

        return EvalResult(
            test_id=case.id,
            user_message=case.user_message[:60],
            expected_tool=case.expected_tool,
            actual_tool=actual_tool,
            actual_args=actual_args,
            reply_text=reply[:120],
            tool_call_accuracy=tool_ok,
            correct_args=args_ok,
            no_hallucination=halluc_ok,
            passed=passed,
            duration_ms=round(duration_ms, 1),
        )

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        return EvalResult(
            test_id=case.id,
            user_message=case.user_message[:60],
            expected_tool=case.expected_tool,
            actual_tool=None,
            actual_args={},
            reply_text="",
            tool_call_accuracy=False,
            correct_args=False,
            no_hallucination=False,
            passed=False,
            duration_ms=round(duration_ms, 1),
            error=str(exc),
        )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

async def main(output_path: str | None = None) -> None:
    import asyncio

    print("\n" + "=" * 70)
    print("  ARIA -- Evaluation Harness")
    print(f"  {len(TEST_CASES)} test cases | model: gemini-2.5-flash")
    print("=" * 70)

    init_db()
    results: list[EvalResult] = []

    for i, case in enumerate(TEST_CASES, 1):
        print(f"  [{i:02d}/{len(TEST_CASES)}] {case.id:8s} {case.user_message[:50]!r}...", end=" ", flush=True)
        result = await run_single_case(case)
        results.append(result)
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"{status}  ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"            ERROR: {result.error}")

    # Summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    tool_acc = sum(1 for r in results if r.tool_call_accuracy) / total * 100
    args_acc = sum(1 for r in results if r.correct_args) / total * 100
    halluc_ok = sum(1 for r in results if r.no_hallucination) / total * 100
    p50 = sorted(r.duration_ms for r in results)[total // 2]
    p95 = sorted(r.duration_ms for r in results)[int(total * 0.95)]

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed}/{total} passed ({passed/total*100:.1f}%)")
    print(f"  Tool call accuracy : {tool_acc:.1f}%")
    print(f"  Argument accuracy  : {args_acc:.1f}%")
    print(f"  No hallucinations  : {halluc_ok:.1f}%")
    print(f"  Latency p50/p95    : {p50:.0f}ms / {p95:.0f}ms")
    print("=" * 70 + "\n")

    # Save JSON report
    output = output_path or str(ROOT / "evals" / "results.json")
    report = {
        "summary": {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total * 100, 1),
            "tool_call_accuracy": round(tool_acc, 1),
            "argument_accuracy": round(args_acc, 1),
            "no_hallucination_rate": round(halluc_ok, 1),
            "latency_p50_ms": p50,
            "latency_p95_ms": p95,
        },
        "results": [asdict(r) for r in results],
    }
    Path(output).write_text(json.dumps(report, indent=2))
    print(f"  📊 Report saved to {output}\n")


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="ARIA Eval Harness")
    parser.add_argument("--output", help="Output JSON path", default=None)
    args = parser.parse_args()

    asyncio.run(main(args.output))
