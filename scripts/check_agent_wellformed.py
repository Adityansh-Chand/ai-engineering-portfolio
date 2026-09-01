"""Check the agent's task set and parsers without a model or a running stack.

The agent evaluation needs five services and about an hour of CPU, so it runs
locally and its results are committed. That leaves a gap CI can still close: the
things that silently rot are the *references* -- a tool renamed in `tools.py`
while `tasks.py` still names the old one, a check pointing at a field the
service no longer returns, a killed service that is not in the port map.

None of that needs a model to catch, and all of it would otherwise surface an
hour into a run as a task that scores zero for a reason that is not the agent's.

    python scripts/check_agent_wellformed.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "agent" / "eval"))

import baseline  # noqa: E402
import loop  # noqa: E402
from service_harness import PORTS  # noqa: E402
from tasks import TASKS, minimum_steps  # noqa: E402
from tools import REFUSE, TOOLS  # noqa: E402

CHECK_KINDS = {"anchors", "tool_field", "refuse", "no_fabrication"}

failures = []


def require(condition, message):
    if not condition:
        failures.append(message)


def check_tasks():
    seen = set()
    for task in TASKS:
        task_id = task.get("id", "<missing id>")
        require(task_id not in seen, f"{task_id}: duplicate id")
        seen.add(task_id)

        for key in ("id", "category", "prompt", "expected_tools", "check"):
            require(key in task, f"{task_id}: missing key {key}")

        for tool in task.get("expected_tools", []):
            require(tool in TOOLS, f"{task_id}: expected_tools names unknown {tool}")

        check = task.get("check", {})
        kind = check.get("kind")
        require(kind in CHECK_KINDS, f"{task_id}: unknown check kind {kind}")

        if kind == "anchors":
            require(bool(check.get("any_of")), f"{task_id}: anchors check is empty")
        if kind == "no_fabrication":
            require(bool(check.get("forbidden")),
                    f"{task_id}: no_fabrication check is empty")
        if kind == "tool_field":
            tool = check.get("tool")
            require(tool in TOOLS, f"{task_id}: tool_field names unknown tool {tool}")
            require(tool in task.get("expected_tools", []),
                    f"{task_id}: tool_field checks {tool}, which the task does not "
                    f"expect to be called")

        category = task.get("category")
        if category == "no_tool":
            require(not task.get("expected_tools"),
                    f"{task_id}: no_tool task expects tools")
            require(kind == "refuse", f"{task_id}: no_tool task must check refusal")
        if category == "tool_down":
            require("kill" in task, f"{task_id}: tool_down task names no service")
            require(task.get("kill") in PORTS,
                    f"{task_id}: kill names unknown service {task.get('kill')}")
            require(kind == "no_fabrication",
                    f"{task_id}: tool_down task must check for fabrication")

        for tool, arguments in (task.get("defaults") or {}).items():
            require(tool in TOOLS, f"{task_id}: defaults name unknown tool {tool}")
            for key in arguments:
                require(key in TOOLS.get(tool, {}).get("parameters", {}),
                        f"{task_id}: defaults set {tool}.{key}, which is not a "
                        f"parameter of {tool}")

        require(minimum_steps(task) >= 1, f"{task_id}: minimum_steps below one")


def check_parsers():
    tool, arguments, error = loop.parse_json_call(
        '{"tool": "knowledge_search", "arguments": {"query": "ERR-4021"}}'
    )
    require(error is None and tool == "knowledge_search"
            and arguments.get("query") == "ERR-4021",
            "json parser: plain object not parsed")

    tool, _, error = loop.parse_json_call(
        'Sure. {"tool":"answer","arguments":{"text":"done"}} hope that helps'
    )
    require(error is None and tool == "answer",
            "json parser: object surrounded by prose not parsed")

    _, arguments, error = loop.parse_json_call(
        '{"tool": "x", "arguments": {"a": "brace } inside a string"}}'
    )
    require(error is None and arguments.get("a") == "brace } inside a string",
            "json parser: brace inside a string terminated the object early")

    _, _, error = loop.parse_json_call("no json at all")
    require(error == "no_json_object", "json parser: missing object not reported")

    tool, arguments, error = loop.parse_lines_call("TOOL: account_score\nARG: acct_1")
    require(error is None and tool == "account_score"
            and arguments.get("customer_id") == "acct_1",
            "lines parser: primary argument not mapped")

    for name in TOOLS:
        require(name in loop.PRIMARY_ARGUMENT,
                f"lines parser: no primary argument mapped for {name}")


def check_baseline():
    for task in TASKS:
        routed = baseline.route(task["prompt"])
        require(routed == REFUSE or routed in TOOLS,
                f"{task['id']}: baseline routed to unknown tool {routed}")
        arguments = baseline.arguments_for(routed, task["prompt"],
                                           task.get("defaults"))
        if routed in TOOLS:
            for key in arguments:
                require(key in TOOLS[routed]["parameters"],
                        f"{task['id']}: baseline passes {routed}.{key}, which is "
                        f"not a parameter of {routed}")


def main():
    check_tasks()
    check_parsers()
    check_baseline()

    if failures:
        print(f"{len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print(f"agent definitions are well-formed: {len(TASKS)} tasks, "
          f"{len(TOOLS)} tools")


if __name__ == "__main__":
    main()
