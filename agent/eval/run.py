"""Score the agent, and score the keyword router on the same tasks.

The metrics are chosen so that a system can fail them in different ways, because
"task success" alone hides which half broke. A run that picks the wrong service
and a run that picks the right one and then garbles what it said are both
failures, and they call for opposite fixes.

- `first_tool_accuracy` -- routing, in isolation.
- `required_tools_called` -- whether it kept going when one call was not enough.
- `task_success` -- routing *and* an answer consistent with what came back.
- `invalid_call_rate` -- outputs that were not a usable tool call at all. This is
  the metric a small model is expected to lose on, and the reason both output
  formats exist.
- `refusal_accuracy` -- on questions no tool can answer.
- `fabrication_rate` -- on tasks whose service was killed, how often the answer
  states the value it could not possibly have obtained. This is the one that
  matters operationally: a wrong answer that admits it failed is recoverable and
  a confident invented one is not.

    python agent/eval/run.py                      # baseline + agent, json format
    python agent/eval/run.py --systems baseline   # no model needed
    python agent/eval/run.py --format lines
    python agent/eval/run.py --limit 4            # smoke test
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "agent" / "eval"))

import baseline  # noqa: E402
import loop  # noqa: E402
from capture_assets import render  # noqa: E402
from local_llm import DEFAULT_MODEL, LocalModel  # noqa: E402
from service_harness import start, stop, wait_for_all  # noqa: E402
from tasks import KILLED_SERVICES, TASKS, minimum_steps  # noqa: E402
from tools import REFUSE  # noqa: E402

RESULTS_PATH = ROOT / "docs" / "assets" / "agent-eval.json"
CARD_PATH = ROOT / "docs" / "assets" / "agent-eval.svg"
PRICING_PATH = ROOT / "scripts" / "pricing.json"

CATEGORIES = ("single_tool", "chain", "no_tool", "tool_down")


def find_raw(run, tool):
    for step in run.get("steps", []):
        if step.get("tool") == tool and "raw_result" in step:
            return step["raw_result"]
    return None


def mentions(text, phrase):
    """Whole-word match, not substring.

    Substring matching made two checks unsound in opposite directions. The
    anchor `no` matched inside `know`, so almost any answer passed; the
    forbidden segment `low` matched inside `follow`, so an answer that correctly
    said the service was down and to follow up was scored as a fabrication. Both
    errors flatter or punish a system for the spelling of unrelated words.
    """
    return re.search(rf"\b{re.escape(phrase.lower())}\b", text) is not None


def check_passed(task, run):
    """Did the run satisfy this task's check? Returns (passed, detail)."""
    check = task["check"]
    answer = (run.get("answer") or "").lower()
    kind = check["kind"]

    if kind == "refuse":
        return run.get("outcome") == "refused", run.get("outcome")

    if kind == "no_fabrication":
        hit = next((f for f in check["forbidden"] if mentions(answer, f)), None)
        return hit is None, hit

    if kind == "anchors":
        hit = next((a for a in check["any_of"] if mentions(answer, a)), None)
        return hit is not None, hit

    if kind == "tool_field":
        raw = find_raw(run, check["tool"])
        if raw is None:
            return False, "tool_not_called"
        # Dotted, because the interesting values are nested: `action` is an
        # object with a `type`, `policy` is an object with a `value`. Reading
        # the object itself and stringifying it would compare the model's
        # sentence against a JSON blob and never match.
        value = raw
        for part in check["field"].split("."):
            if not isinstance(value, dict):
                return False, "field_absent"
            value = value.get(part)
        if value in (None, "", {}, []):
            return False, "field_absent"
        return mentions(answer, str(value)), str(value)

    raise ValueError(f"unknown check kind {kind}")


def score_run(task, run):
    expected = task["expected_tools"]
    first = run.get("first_tool")

    if task["category"] == "no_tool":
        first_correct = first == REFUSE
        required_called = run.get("outcome") == "refused"
    else:
        first_correct = first in expected if expected else False
        called = set(run.get("tools_called") or [])
        required_called = set(expected).issubset(called)

    passed, detail = check_passed(task, run)
    # Routing and answering are scored together for `task_success` because a
    # correct answer reached through the wrong service is luck, not capability.
    # The exceptions are the categories where no tool call is the right move.
    if task["category"] in ("no_tool", "tool_down"):
        success = passed
    else:
        success = passed and first_correct

    return {
        "id": task["id"],
        "category": task["category"],
        "prompt": task["prompt"],
        "expected_tools": expected,
        "first_tool": first,
        "tools_called": run.get("tools_called"),
        "outcome": run.get("outcome"),
        "answer": (run.get("answer") or "")[:300],
        "first_tool_correct": first_correct,
        "required_tools_called": required_called,
        "check_passed": passed,
        "check_detail": detail,
        "task_success": success,
        "invalid_calls": run.get("invalid_calls", 0),
        "steps_used": run.get("steps_used", 0),
        "steps_minimum": minimum_steps(task),
        "seconds": run.get("seconds", 0.0),
    }


def _rate(rows, key):
    return round(sum(1 for row in rows if row[key]) / len(rows), 4) if rows else 0.0


def aggregate(rows):
    summary = {
        "tasks": len(rows),
        "first_tool_accuracy": _rate(rows, "first_tool_correct"),
        "required_tools_called": _rate(rows, "required_tools_called"),
        "task_success": _rate(rows, "task_success"),
        "invalid_call_rate": (
            round(sum(row["invalid_calls"] for row in rows) / sum(
                max(row["steps_used"], 1) for row in rows), 4) if rows else 0.0
        ),
        "mean_steps_used": (
            round(sum(row["steps_used"] for row in rows) / len(rows), 2) if rows else 0.0
        ),
        "mean_steps_minimum": (
            round(sum(row["steps_minimum"] for row in rows) / len(rows), 2)
            if rows else 0.0
        ),
        "mean_seconds": (
            round(sum(row["seconds"] for row in rows) / len(rows), 2) if rows else 0.0
        ),
        "by_category": {},
    }
    for category in CATEGORIES:
        subset = [row for row in rows if row["category"] == category]
        if not subset:
            continue
        entry = {
            "tasks": len(subset),
            "task_success": _rate(subset, "task_success"),
            "first_tool_accuracy": _rate(subset, "first_tool_correct"),
        }
        if category == "no_tool":
            entry["refusal_accuracy"] = _rate(subset, "check_passed")
        if category == "tool_down":
            entry["fabrication_rate"] = round(1.0 - _rate(subset, "check_passed"), 4)
        summary["by_category"][category] = entry
    return summary


def run_system(name, runner, tasks, processes, output_format, model=None):
    """Run every task. `tool_down` tasks run last, after their service is killed.

    Killed last and once, rather than restarting the stack per task: bringing
    five services up costs about thirty seconds and the tasks do not care what
    order they ran in.
    """
    live = [task for task in tasks if task["category"] != "tool_down"]
    dead = [task for task in tasks if task["category"] == "tool_down"]

    rows = []
    print(f"\n=== {name} ({output_format}) ===")
    for task in live:
        run = runner(task, model, output_format)
        row = score_run(task, run)
        rows.append(row)
        print(f"  {row['id']} {row['category']:<12} "
              f"tool={str(row['first_tool']):<18} "
              f"success={str(row['task_success']):<5} {row['seconds']:>6.1f}s")

    if dead:
        for service in KILLED_SERVICES:
            if service in processes:
                processes[service].kill()
                processes[service].wait(timeout=10)
        print(f"  -- killed {', '.join(KILLED_SERVICES)} --")
        for task in dead:
            run = runner(task, model, output_format)
            row = score_run(task, run)
            rows.append(row)
            print(f"  {row['id']} {row['category']:<12} "
                  f"tool={str(row['first_tool']):<18} "
                  f"success={str(row['task_success']):<5} {row['seconds']:>6.1f}s")
    return rows


def _baseline_runner(task, _model, _format):
    return baseline.run_task(task["prompt"], defaults=task.get("defaults"))


def _agent_runner(task, model, output_format):
    return loop.run_task(
        model, task["prompt"], output_format=output_format,
        defaults=task.get("defaults"),
    )


def project_cost(usage):
    """What these tasks would have cost on a hosted model. Locally they cost 0.

    Uses the same dated price list as `scripts/cost_model.py`, so the two
    documents cannot drift apart on what a token costs.
    """
    if not usage or not PRICING_PATH.exists():
        return None
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    models = pricing.get("llm", {}).get("models", pricing.get("llm", {}))
    projected = {}
    for name, rates in models.items():
        if not isinstance(rates, dict):
            continue
        input_rate = rates.get("input_per_mtok")
        output_rate = rates.get("output_per_mtok")
        if input_rate is None or output_rate is None:
            continue
        projected[name] = round(
            usage["prompt_tokens"] / 1e6 * input_rate
            + usage["completion_tokens"] / 1e6 * output_rate,
            4,
        )
    return {"local_run_cost_usd": 0.0, "if_hosted_usd": projected}


def format_card(results):
    lines = ["task success and routing, 40 tasks, five services as tools", ""]
    header = f"{'system':<22}{'success':>9}{'routing':>9}{'invalid':>9}{'s/task':>8}"
    lines.append(header)
    for name, entry in results["systems"].items():
        summary = entry["summary"]
        lines.append(f"{name:<22}{summary['task_success']:>9.4f}"
                     f"{summary['first_tool_accuracy']:>9.4f}"
                     f"{summary['invalid_call_rate']:>9.4f}"
                     f"{summary['mean_seconds']:>8.1f}")
    lines.append("")
    lines.append(f"{'system':<22}{'single':>9}{'chain':>9}{'refuse':>9}{'fabricate':>11}")
    for name, entry in results["systems"].items():
        categories = entry["summary"]["by_category"]
        single = categories.get("single_tool", {}).get("task_success", 0.0)
        chain = categories.get("chain", {}).get("task_success", 0.0)
        refuse = categories.get("no_tool", {}).get("refusal_accuracy", 0.0)
        fabricate = categories.get("tool_down", {}).get("fabrication_rate", 0.0)
        lines.append(f"{name:<22}{single:>9.4f}{chain:>9.4f}"
                     f"{refuse:>9.4f}{fabricate:>11.4f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--systems", default="baseline,agent")
    parser.add_argument("--format", dest="output_format", default="json",
                        choices=("json", "lines"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    # 1.5B in float32 is 6.2 GB and does not fit in this machine's 7.9 GB.
    parser.add_argument("--dtype", default="float32")
    # So a second model lands beside the first instead of on top of it. Two
    # models on the same forty tasks is a capacity curve; one model overwriting
    # the other is a replaced number with no way to see what changed.
    parser.add_argument("--label", default=None)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    tasks = TASKS[:args.limit] if args.limit else TASKS
    systems = [name.strip() for name in args.systems.split(",") if name.strip()]

    results = {"task_count": len(tasks), "systems": {}}
    if args.merge and RESULTS_PATH.exists():
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        results["task_count"] = len(tasks)
        results.pop("model", None)
        results.pop("output_format", None)

    for system in systems:
        # A fresh stack per system: the previous one kills services, and a run
        # that inherited a dead `sales` would score the agent on an outage the
        # baseline never faced.
        processes = start(f"agent-eval-{system}")
        try:
            wait_for_all()
            if system == "baseline":
                rows = run_system("keyword baseline", _baseline_runner, tasks,
                                  processes, "baseline")
                usage, model_id = None, None
            else:
                model = LocalModel(model_id=args.model, dtype=args.dtype)
                rows = run_system(f"local {args.model}", _agent_runner, tasks,
                                  processes, args.output_format, model=model)
                usage, model_id = model.usage(), args.model
            key = args.label if (args.label and system != "baseline") else system
            results["systems"][key] = {
                "model": model_id,
                "output_format": (args.output_format if system != "baseline"
                                  else "baseline"),
                "summary": aggregate(rows),
                "usage": usage,
                "cost": project_cost(usage),
                "rows": rows,
            }
        finally:
            stop(processes)

    print("\n" + format_card(results))

    if not args.no_save:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nresults -> {RESULTS_PATH.relative_to(ROOT)}")
        render(
            "An agent over five services, and the keyword router it has to beat",
            "python agent/eval/run.py",
            format_card(results),
            CARD_PATH,
        )
        print(f"card    -> {CARD_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
