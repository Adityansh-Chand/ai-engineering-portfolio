"""The agent: choose a tool, call it, look at what came back, answer.

This is the smallest loop that is honestly agentic -- the model decides which
service to call and whether it has enough to answer, rather than following a
route decided in code. Everything else in this portfolio decides in code, which
is why `agent/baseline.py` exists to be the thing this has to beat.

**Bounded on purpose.** Three steps maximum. An unbounded loop driven by a
0.5B model does not converge, it wanders, and at three tokens per second a
wandering loop is measured in hours. The step limit is a property of the design,
not a limitation to apologise for: the tasks are reachable in one or two calls
and `steps_used` against `steps_minimum` is reported so over-stepping shows up.

**Two output formats, because the format is a real variable.** `json` is what
every tool-calling API expects and what a reviewer will assume. `lines` is a
flatter `TOOL:` / `ARG:` grammar that a small model finds much easier to hold.
Both are implemented so the cost of the industry-standard format can be
measured on a small model rather than asserted -- see `docs/AGENT.md`.
"""
import json
import re

from tools import ANSWER, REFUSE, TOOLS, describe_tools, invoke

MAX_STEPS = 3

# Long enough for a tool call plus a short argument, short enough that a model
# which starts writing an essay is cut off rather than paid for.
SELECT_TOKENS = 64
ANSWER_TOKENS = 128

_SYSTEM_JSON = """You are an operations assistant. You answer by calling tools.

Available tools:
{tools}
- answer(text): give the final answer, using only what the tools returned

Reply with exactly one JSON object and nothing else:
{{"tool": "<name>", "arguments": {{"<key>": "<value>"}}}}

Example: {{"tool": "knowledge_search", "arguments": {{"query": "reset a password"}}}}
Example: {{"tool": "answer", "arguments": {{"text": "Retry the request once."}}}}"""

_SYSTEM_LINES = """You are an operations assistant. You answer by calling tools.

Available tools:
{tools}
- answer(text): give the final answer, using only what the tools returned

Reply with exactly two lines and nothing else:
TOOL: <name>
ARG: <value>

Example:
TOOL: knowledge_search
ARG: reset a password"""

# The first argument each tool wants, for the `lines` format, which carries one
# unnamed value. Multi-argument tools get the rest filled from the task's own
# fields -- a small model reliably producing three named arguments is not
# something to design around.
PRIMARY_ARGUMENT = {name: next(iter(tool["parameters"])) for name, tool in TOOLS.items()}


def _balanced_json(text):
    """First balanced {...} in the text, or None.

    A regex cannot do this -- `arguments` is a nested object, so any
    non-greedy pattern stops at the inner brace and any greedy one swallows
    trailing commentary the model added after the object.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def parse_json_call(text):
    """Returns (tool, arguments, error)."""
    blob = _balanced_json(text)
    if blob is None:
        return None, None, "no_json_object"
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None, None, "malformed_json"
    if not isinstance(parsed, dict):
        return None, None, "not_an_object"
    tool = parsed.get("tool") or parsed.get("name")
    if not isinstance(tool, str):
        return None, None, "no_tool_field"
    arguments = parsed.get("arguments") or parsed.get("args") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    return tool.strip(), arguments, None


def parse_lines_call(text):
    tool_match = re.search(r"TOOL:\s*([A-Za-z_]+)", text)
    if not tool_match:
        return None, None, "no_tool_line"
    tool = tool_match.group(1).strip()
    argument_match = re.search(r"ARG:\s*(.+)", text)
    value = argument_match.group(1).strip() if argument_match else ""
    if tool == ANSWER:
        return tool, {"text": value}, None
    if tool == REFUSE:
        return tool, {}, None
    key = PRIMARY_ARGUMENT.get(tool)
    return tool, ({key: value} if key else {}), None


PARSERS = {"json": parse_json_call, "lines": parse_lines_call}
SYSTEMS = {"json": _SYSTEM_JSON, "lines": _SYSTEM_LINES}

REPAIR = {
    "json": ('Your last reply was not valid. Reply with only a JSON object, '
             'starting with { and ending with }, and no other text.'),
    "lines": ('Your last reply was not valid. Reply with only two lines: '
              'a TOOL: line and an ARG: line.'),
}


def build_user_prompt(task, observations, repair=None):
    parts = [f"Question: {task}"]
    for name, observation in observations:
        parts.append(f"Result of {name}:\n{observation}")
    if observations:
        parts.append(
            "If this is enough, use answer. If no tool can answer, use refuse."
        )
    if repair:
        # Decoding is greedy, so an unchanged prompt regenerates the identical
        # bad output. Without this the retry is not a retry -- it is the same
        # call charged twice, and the invalid-call rate counts one mistake
        # three times.
        parts.append(repair)
    return "\n\n".join(parts)


def run_task(model, task, output_format="json", max_steps=MAX_STEPS,
             defaults=None):
    """Run one task. Returns a trace dict the evaluation harness scores.

    `defaults` supplies arguments the task states but the `lines` format cannot
    carry (a customer id alongside a message, for instance). They are applied
    only to keys the model did not provide, so they can never overwrite a
    choice the model actually made.
    """
    system = SYSTEMS[output_format].format(tools=describe_tools())
    parse = PARSERS[output_format]

    observations, steps = [], []
    final_answer, outcome = None, "no_answer"
    repair = None
    # Identical calls already made. A small model frequently ignores the
    # observation it was just given and re-issues the same call verbatim, which
    # costs a full generation to learn nothing. Detecting it is ordinary loop
    # protection, and it is also two thirds of this evaluation's runtime.
    attempted = set()

    for step_index in range(max_steps):
        prompt = build_user_prompt(task, observations, repair)
        completion = model.complete(
            system, prompt, max_new_tokens=SELECT_TOKENS, stop=["\n\n"]
        )
        tool, arguments, parse_error = parse(completion.text)
        step = {
            "raw": completion.text.strip()[:300],
            "tool": tool,
            "arguments": arguments,
            "parse_error": parse_error,
            "seconds": round(completion.seconds, 2),
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
        }

        if parse_error:
            steps.append(step)
            outcome = "invalid_call"
            repair = REPAIR[output_format]
            continue

        if tool == ANSWER:
            final_answer = str(arguments.get("text", "")).strip()
            step["result"] = "answered"
            steps.append(step)
            outcome = "answered"
            break

        if tool == REFUSE:
            step["result"] = "refused"
            steps.append(step)
            outcome = "refused"
            break

        if tool not in TOOLS:
            step["result"] = "unknown_tool"
            steps.append(step)
            outcome = "invalid_call"
            repair = (f"There is no tool called {tool}. Choose one of: "
                      f"{', '.join(TOOLS)}, {REFUSE}.")
            continue

        repair = None

        merged = dict((defaults or {}).get(tool, {}))
        merged.update({k: v for k, v in arguments.items() if v not in (None, "")})

        signature = (tool, json.dumps(merged, sort_keys=True, default=str))
        if signature in attempted:
            step["result"] = "repeat_call"
            steps.append(step)
            outcome = "looped"
            break
        attempted.add(signature)

        result, error = invoke(tool, merged)
        if error:
            step["result"] = f"error:{error}"
            # The failure is shown to the model rather than hidden. Whether it
            # then says so or invents a number is exactly what the tool-failure
            # tasks are there to find out.
            observations.append((tool, f"tool failed: {error}"))
        else:
            step["result"] = "ok"
            observations.append((tool, result["observation"]))
            step["raw_result"] = result["raw"]
        steps.append(step)

    # Out of steps with tools called but nothing said. Ask once for the answer
    # rather than scoring a blank, so a model that routed correctly is not
    # marked wrong for failing to also volunteer a summary.
    if final_answer is None and outcome != "refused" and observations:
        completion = model.complete(
            system.split("\n\nReply with")[0],
            build_user_prompt(task, observations)
            + "\n\nAnswer the question directly in one or two sentences.",
            max_new_tokens=ANSWER_TOKENS,
        )
        final_answer = completion.text.strip()
        outcome = "answered_after_prompting"
        steps.append({
            "tool": "forced_answer",
            "seconds": round(completion.seconds, 2),
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
        })

    return {
        "task": task,
        "format": output_format,
        "outcome": outcome,
        "answer": final_answer or "",
        "tools_called": [s["tool"] for s in steps if s.get("result") in ("ok",)],
        "first_tool": next(
            (s["tool"] for s in steps if s.get("tool") not in (None, "forced_answer")),
            None,
        ),
        "invalid_calls": sum(1 for s in steps if s.get("parse_error")
                             or s.get("result") == "unknown_tool"),
        "steps": steps,
        "steps_used": len(steps),
        "seconds": round(sum(s.get("seconds", 0.0) for s in steps), 2),
    }
