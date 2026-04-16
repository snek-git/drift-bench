from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from drift_bench.conversation import run_branch, run_neutral_phase
from drift_bench.judge import judge_drift
from drift_bench.models import (
    BranchResult,
    Judgment,
    NeutralResult,
    RunConfig,
    Scenario,
    Usage,
    load_scenarios,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _model_slug(model: str) -> str:
    return model.removeprefix("openrouter/").replace("/", "--")


def _pair_dir(run_dir: Path, scenario_id: str, model: str) -> Path:
    return run_dir / "results" / f"{scenario_id}__{_model_slug(model)}"


def _save(path: Path, data: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data.model_dump_json(indent=2))
    os.replace(tmp, path)


def _load(path: Path, model: type[T]) -> T | None:
    if not path.exists():
        return None
    try:
        return model.model_validate_json(path.read_text())
    except Exception:
        logger.warning("Corrupt checkpoint %s, will re-run", path)
        return None


async def _run_pair(
    scenario: Scenario,
    target_model: str,
    sim_model: str,
    judge_model: str,
    pair_dir: Path,
    force: bool,
) -> dict | None:
    """Run one (scenario, model) pair. Returns score dict or None on failure."""
    slug = _model_slug(target_model)
    logger.info("=== %s x %s ===", scenario.id, slug)

    try:
        # Neutral phase
        neutral_path = pair_dir / "neutral.json"
        neutral = None if force else _load(neutral_path, NeutralResult)
        if neutral is None:
            neutral = await run_neutral_phase(scenario, target_model, sim_model)
            _save(neutral_path, neutral)

        # Branches (parallel)
        branch_a_path = pair_dir / "branch_a.json"
        branch_b_path = pair_dir / "branch_b.json"

        branch_a = None if force else _load(branch_a_path, BranchResult)
        branch_b = None if force else _load(branch_b_path, BranchResult)

        tasks = []
        if branch_a is None:
            tasks.append(("a", run_branch(scenario, neutral, scenario.branch_a, "a", target_model, sim_model)))
        if branch_b is None:
            tasks.append(("b", run_branch(scenario, neutral, scenario.branch_b, "b", target_model, sim_model)))

        if tasks:
            results = await asyncio.gather(*(t[1] for t in tasks))
            for (bid, _), result in zip(tasks, results):
                if bid == "a":
                    branch_a = result
                    _save(branch_a_path, branch_a)
                else:
                    branch_b = result
                    _save(branch_b_path, branch_b)

        # Judge
        judgment_path = pair_dir / "judgment.json"
        judgment = None if force else _load(judgment_path, Judgment)
        if judgment is None:
            judgment, judge_usage = await judge_drift(
                scenario, neutral, branch_a, branch_b, judge_model
            )
            _save(judgment_path, judgment)

        total_usage = neutral.usage + branch_a.usage + branch_b.usage
        logger.info(
            "Done: %s x %s — overall_drift=%d, tokens=%d",
            scenario.id, slug, judgment.overall_drift, total_usage.total_tokens,
        )

        return {
            "scenario_id": scenario.id,
            "model": target_model,
            "model_slug": slug,
            "scores": judgment.model_dump(),
            "total_tokens": total_usage.total_tokens,
        }

    except Exception:
        logger.exception("Failed: %s x %s", scenario.id, slug)
        return None


def _write_summary(run_dir: Path, all_results: list[dict]) -> None:
    lines = ["# drift-bench run summary\n"]

    if not all_results:
        lines.append("No results.\n")
        (run_dir / "summary.md").write_text("\n".join(lines))
        return

    # Per-pair table
    lines.append("## Results\n")
    lines.append("| Scenario | Model | Position Shift | Hedging Asymmetry | Framing Adoption | Evidence Cherry-Picking | Overall Drift | Tokens |")
    lines.append("|----------|-------|:-:|:-:|:-:|:-:|:-:|------:|")

    for r in all_results:
        s = r["scores"]
        lines.append(
            f"| {r['scenario_id']} | {r['model_slug']} "
            f"| {s['position_shift']} | {s['hedging_asymmetry']} "
            f"| {s['framing_adoption']} | {s['evidence_cherry_picking']} "
            f"| {s['overall_drift']} | {r['total_tokens']:,} |"
        )

    # Per-model averages
    from collections import defaultdict
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in all_results:
        by_model[r["model_slug"]].append(r["scores"])

    lines.append("\n## Per-model averages\n")
    lines.append("| Model | Avg Overall Drift | Avg Position Shift | n |")
    lines.append("|-------|:-:|:-:|:-:|")

    for slug, scores in sorted(by_model.items()):
        avg_drift = sum(s["overall_drift"] for s in scores) / len(scores)
        avg_shift = sum(s["position_shift"] for s in scores) / len(scores)
        lines.append(f"| {slug} | {avg_drift:.1f} | {avg_shift:.1f} | {len(scores)} |")

    (run_dir / "summary.md").write_text("\n".join(lines))


async def run_benchmark(config: RunConfig) -> None:
    run_dir = Path(config.output_dir) / config.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save config snapshot
    config_path = run_dir / "config.json"
    config_path.write_text(config.model_dump_json(indent=2))

    # Load scenarios
    scenarios: list[Scenario] = []
    for s in config.scenarios:
        scenarios.extend(load_scenarios(Path(s)))

    logger.info(
        "Running %d scenarios x %d models",
        len(scenarios), len(config.target_models),
    )

    all_results: list[dict] = []

    for scenario in scenarios:
        for model in config.target_models:
            # Enforce: target != sim and target != judge
            if model == config.sim_model or model == config.judge_model:
                logger.warning(
                    "Skipping %s — same as sim or judge model", model
                )
                continue

            pair_dir = _pair_dir(run_dir, scenario.id, model)
            result = await _run_pair(
                scenario, model, config.sim_model, config.judge_model,
                pair_dir, config.force,
            )
            if result:
                all_results.append(result)

    _write_summary(run_dir, all_results)
    logger.info("Summary written to %s/summary.md", run_dir)
