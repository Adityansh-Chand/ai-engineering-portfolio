"""What this system would cost to run, derived from what it was measured doing.

The portfolio runs on one laptop and spends nothing, which is a deliberate choice
and also a gap: an architecture argument that never mentions money is missing the
constraint that usually decides it. This closes that without spending anything.

The method has one rule: **measured where measurable, modelled where not, and
never mixed up.** Throughput comes from `scripts/load_test.py`, which really ran.
Prices come from `scripts/pricing.json`, which is dated and cites its sources.
Nothing here is an estimate of how fast the code "should" be.

    python scripts/cost_model.py
    python scripts/cost_model.py --requests 10000000
    python scripts/cost_model.py --no-save
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PRICING_PATH = ROOT / "scripts" / "pricing.json"
LOAD_PATH = ROOT / "docs" / "assets" / "load-test.json"
RESULTS_PATH = ROOT / "docs" / "assets" / "cost-model.json"
CARD_PATH = ROOT / "docs" / "assets" / "cost-model.svg"

PER = 1_000_000  # everything is quoted per million requests


def peak_throughput(rows):
    """The best sustained throughput, and the concurrency that produced it.

    Peak rather than maximum-concurrency, because both CPU-bound endpoints get
    *slower in aggregate* past their peak. Costing at 32 concurrent requests
    would price the system at its worst point and call it capacity.
    """
    best = max(rows, key=lambda row: row["throughput_rps"])
    return best["throughput_rps"], best["concurrency"], best["p95_ms"]


def compute_cost_per_million(throughput_rps, option, assumptions):
    """Task-seconds needed for a million requests, priced at the vCPU+GB rates."""
    if throughput_rps <= 0:
        return 0.0
    task_seconds = PER / throughput_rps
    vcpu = assumptions["task_vcpu"] * option["vcpu_second"]
    memory = assumptions["task_memory_gb"] * option["gb_second"]
    return task_seconds * (vcpu + memory)


def llm_cost_per_million(model, assumptions, batch=False, cache_hit_ratio=0.0,
                         modifiers=None):
    """Token cost for a million generation calls.

    `cache_hit_ratio` is the share of input tokens served from a prompt cache,
    which is the realistic case here: the system prompt and instructions are
    identical on every call, only the retrieved context and question change.
    """
    modifiers = modifiers or {}
    input_tokens = assumptions["llm_input_tokens_per_query"] * PER
    output_tokens = assumptions["llm_output_tokens_per_query"] * PER

    cached = input_tokens * cache_hit_ratio
    uncached = input_tokens - cached
    cache_multiplier = modifiers.get("cache_hit_input_multiplier", 0.1)

    input_cost = (
        uncached * model["input_per_mtok"] / PER
        + cached * model["input_per_mtok"] * cache_multiplier / PER
    )
    output_cost = output_tokens * model["output_per_mtok"] / PER
    total = input_cost + output_cost

    if batch:
        total *= modifiers.get("batch_discount", 0.5)
    return total


def build(pricing, load):
    assumptions = pricing["assumptions"]
    compute_options = pricing["compute"]["options"]
    x86 = compute_options["fargate_linux_x86"]
    arm = compute_options["fargate_linux_arm"]

    endpoints = {}
    for name, scenario in load["scenarios"].items():
        rps, concurrency, p95 = peak_throughput(scenario["rows"])
        endpoints[name] = {
            "label": scenario["label"],
            "peak_throughput_rps": rps,
            "at_concurrency": concurrency,
            "p95_ms_at_peak": p95,
            "compute_usd_per_million": {
                "fargate_linux_x86": round(
                    compute_cost_per_million(rps, x86, assumptions), 4
                ),
                "fargate_linux_arm": round(
                    compute_cost_per_million(rps, arm, assumptions), 4
                ),
            },
        }

    modifiers = pricing["llm"]["modifiers"]
    llm = {}
    for name, model in pricing["llm"]["models"].items():
        llm[name] = {
            "standard": round(
                llm_cost_per_million(model, assumptions, modifiers=modifiers), 2
            ),
            "with_prompt_cache": round(
                llm_cost_per_million(model, assumptions, cache_hit_ratio=0.5,
                                     modifiers=modifiers), 2
            ),
            "batch": round(
                llm_cost_per_million(model, assumptions, batch=True,
                                     modifiers=modifiers), 2
            ),
        }

    # Components that are built and benchmarked but off by default. Their
    # latency was measured elsewhere; what this model adds is the price of it,
    # sitting next to the quality it buys.
    components = {}
    for name, component in pricing.get("optional_components", {}).items():
        if not isinstance(component, dict) or "added_ms_per_query" not in component:
            continue
        seconds = component["added_ms_per_query"] / 1000.0
        cost = PER * seconds * (
            assumptions["task_vcpu"] * x86["vcpu_second"]
            + assumptions["task_memory_gb"] * x86["gb_second"]
        )
        components[name] = {
            "added_ms_per_query": component["added_ms_per_query"],
            "quality_delta_ndcg10": component["quality_delta_ndcg10"],
            "added_usd_per_million": round(cost, 2),
            "measured_on": component.get("measured_on"),
        }

    # The comparison the whole model exists to make.
    rag_compute = endpoints["rag_query"]["compute_usd_per_million"]["fargate_linux_x86"]
    cheapest_llm = min(entry["standard"] for entry in llm.values())

    for name, entry in components.items():
        entry["multiple_of_retrieval_compute"] = (
            round(entry["added_usd_per_million"] / rag_compute, 1)
            if rag_compute else None
        )

    sensitivity = build_sensitivity(pricing, endpoints, x86, arm, assumptions, modifiers)

    return {
        "as_of": pricing["as_of"],
        "basis": {
            "throughput": "measured, docs/assets/load-test.json",
            "prices": "dated inputs, scripts/pricing.json",
            "hardware": pricing["measurement_hardware"]["cpu"],
            "task_shape": f"{assumptions['task_vcpu']} vCPU / "
                          f"{assumptions['task_memory_gb']} GB per service",
        },
        "endpoints": endpoints,
        "optional_components": components,
        "llm_generation_usd_per_million": llm,
        "sensitivity": sensitivity,
        "headline": {
            "retrieval_compute_usd_per_million": rag_compute,
            "cheapest_llm_usd_per_million": cheapest_llm,
            "ratio": round(cheapest_llm / rag_compute, 0) if rag_compute else None,
        },
    }


def build_sensitivity(pricing, endpoints, x86, arm, assumptions, modifiers):
    """Move one assumption at a time and report the effect on the total.

    Computed rather than asserted. Hand-arithmetic on a table like this is how a
    document ends up confidently quoting a percentage nobody re-derived -- the
    context row below is 20.5%, not the 15% a first pass through it produced.
    """
    models = pricing["llm"]["models"]
    baseline_model = models["claude-haiku-4-5"]
    rps = endpoints["rag_query"]["peak_throughput_rps"]

    compute = compute_cost_per_million(rps, x86, assumptions)
    generation = llm_cost_per_million(baseline_model, assumptions, modifiers=modifiers)
    baseline = compute + generation

    # Context is the retrieved chunks; the rest of the input is the system prompt
    # and the question, which halving the context does not touch.
    context_tokens = 5 * 90
    fixed_input = assumptions["llm_input_tokens_per_query"] - context_tokens

    def with_tokens(input_tokens, output_tokens):
        changed = dict(assumptions)
        changed["llm_input_tokens_per_query"] = input_tokens
        changed["llm_output_tokens_per_query"] = output_tokens
        return compute + llm_cost_per_million(
            baseline_model, changed, modifiers=modifiers
        )

    variants = {
        "arm_instead_of_x86":
            compute_cost_per_million(rps, arm, assumptions) + generation,
        "double_retrieval_throughput":
            compute_cost_per_million(rps * 2, x86, assumptions) + generation,
        "opus_instead_of_haiku":
            compute + llm_cost_per_million(
                models["claude-opus-5"], assumptions, modifiers=modifiers),
        "batch_api":
            compute + llm_cost_per_million(
                baseline_model, assumptions, batch=True, modifiers=modifiers),
        "halve_answer_length":
            with_tokens(assumptions["llm_input_tokens_per_query"],
                        assumptions["llm_output_tokens_per_query"] // 2),
        "halve_retrieved_context":
            with_tokens(fixed_input + context_tokens // 2,
                        assumptions["llm_output_tokens_per_query"]),
        "no_llm_at_all": compute,
    }

    return {
        "baseline_usd_per_million": round(baseline, 2),
        "baseline_note": "rag retrieval compute (x86) + Claude Haiku 4.5 generation",
        "variants": {
            name: {
                "usd_per_million": round(total, 2),
                "change_pct": round((total - baseline) / baseline * 100, 4),
            }
            for name, total in variants.items()
        },
    }


def format_report(result):
    lines = []
    lines.append(f"basis: throughput measured on {result['basis']['hardware']}")
    lines.append(f"       prices dated {result['as_of']}, "
                 f"{result['basis']['task_shape']}")
    lines.append("")
    lines.append("compute, USD per million requests, at each endpoint's peak throughput")
    lines.append(f"{'endpoint':<14}{'peak rps':>10}{'conc':>6}{'x86':>10}{'arm':>10}")
    for name, entry in result["endpoints"].items():
        costs = entry["compute_usd_per_million"]
        lines.append(
            f"{name:<14}{entry['peak_throughput_rps']:>10.1f}"
            f"{entry['at_concurrency']:>6}"
            f"{costs['fargate_linux_x86']:>10.2f}{costs['fargate_linux_arm']:>10.2f}"
        )
    lines.append("")
    lines.append("optional components: what the quality costs (x86)")
    lines.append(f"{'component':<22}{'+ms/query':>11}{'dNDCG@10':>11}"
                 f"{'+USD/M':>10}{'x retrieval':>13}")
    for name, entry in result["optional_components"].items():
        lines.append(
            f"{name:<22}{entry['added_ms_per_query']:>11.1f}"
            f"{entry['quality_delta_ndcg10']:>+11.4f}"
            f"{entry['added_usd_per_million']:>10.2f}"
            f"{entry['multiple_of_retrieval_compute']:>13.1f}"
        )
    lines.append("")
    lines.append("LLM generation, USD per million answers")
    lines.append(f"{'model':<22}{'standard':>12}{'+cache 50%':>12}{'batch':>10}")
    for name, entry in result["llm_generation_usd_per_million"].items():
        lines.append(f"{name:<22}{entry['standard']:>12.2f}"
                     f"{entry['with_prompt_cache']:>12.2f}{entry['batch']:>10.2f}")
    lines.append("")
    headline = result["headline"]
    lines.append(f"retrieval compute   ${headline['retrieval_compute_usd_per_million']:.2f} "
                 f"per million")
    lines.append(f"cheapest LLM answer ${headline['cheapest_llm_usd_per_million']:.2f} "
                 f"per million")
    lines.append(f"the LLM path costs {headline['ratio']:,.0f}x the retrieval "
                 f"it sits on top of")

    sensitivity = result["sensitivity"]
    lines.append("")
    lines.append(f"sensitivity, from a baseline of "
                 f"${sensitivity['baseline_usd_per_million']:,.2f} per million")
    lines.append(f"({sensitivity['baseline_note']})")
    lines.append(f"{'change one assumption':<30}{'USD/M':>12}{'effect':>12}")
    for name, entry in sensitivity["variants"].items():
        lines.append(f"{name:<30}{entry['usd_per_million']:>12,.2f}"
                     f"{entry['change_pct']:>11.3f}%")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--verify", action="store_true",
                        help="fail if recomputing from the committed inputs "
                             "differs from the committed output")
    args = parser.parse_args()

    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    if not LOAD_PATH.exists():
        raise SystemExit("run scripts/load_test.py first -- this model costs measurements")
    load = json.loads(LOAD_PATH.read_text(encoding="utf-8"))

    result = build(pricing, load)
    report = format_report(result)
    text = json.dumps(result, indent=2) + "\n"

    if args.verify:
        # Pure arithmetic over two committed files, so this is byte-stable
        # anywhere. It catches the case that matters: a price edited without the
        # figures quoted in COST_MODEL.md being recomputed.
        if not RESULTS_PATH.exists():
            print("FAIL: cost-model.json missing; run without --verify first")
            return 1
        if RESULTS_PATH.read_text(encoding="utf-8") != text:
            print("FAIL: recomputed cost model differs from the committed file")
            return 1
        print("OK: cost model reproducible from pricing.json and load-test.json")
        return 0

    print(report)

    if not args.no_save:
        RESULTS_PATH.write_text(text, encoding="utf-8")
        print(f"\nresults -> {RESULTS_PATH.relative_to(ROOT)}")
        from capture_assets import render

        render(
            "Cost per million requests -- measured throughput, dated prices",
            "python scripts/cost_model.py",
            report,
            CARD_PATH,
        )
        print(f"card    -> {CARD_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
