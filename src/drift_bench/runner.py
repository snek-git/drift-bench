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
    rejudge: bool = False,
) -> dict | None:
    """Run one (scenario, model) pair. Returns score dict or None on failure."""
    slug = _model_slug(target_model)
    logger.info("=== %s x %s ===", scenario.id, slug)

    force_conversations = force and not rejudge

    try:
        # Neutral phase
        neutral_path = pair_dir / "neutral.json"
        neutral = None if force_conversations else _load(neutral_path, NeutralResult)
        if neutral is None:
            neutral = await run_neutral_phase(scenario, target_model, sim_model)
            _save(neutral_path, neutral)

        # Branches (parallel)
        branch_a_path = pair_dir / "branch_a.json"
        branch_b_path = pair_dir / "branch_b.json"

        branch_a = None if force_conversations else _load(branch_a_path, BranchResult)
        branch_b = None if force_conversations else _load(branch_b_path, BranchResult)

        async def _run_and_save_branch(branch_cfg, bid, path):
            result = await run_branch(scenario, neutral, branch_cfg, bid, target_model, sim_model)
            _save(path, result)
            return result

        coros = []
        if branch_a is None:
            coros.append(_run_and_save_branch(scenario.branch_a, "a", branch_a_path))
        if branch_b is None:
            coros.append(_run_and_save_branch(scenario.branch_b, "b", branch_b_path))

        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    raise r
            # Re-load from saved checkpoints to keep the flow simple
            branch_a = branch_a or _load(branch_a_path, BranchResult)
            branch_b = branch_b or _load(branch_b_path, BranchResult)

        # Judge
        force_judge = force or rejudge
        judgment_path = pair_dir / "judgment.json"
        judgment = None if force_judge else _load(judgment_path, Judgment)
        judge_usage = Usage()
        if judgment is None:
            judgment, judge_usage = await judge_drift(
                scenario, neutral, branch_a, branch_b, judge_model
            )
            _save(judgment_path, judgment)

        total_usage = neutral.usage + branch_a.usage + branch_b.usage + judge_usage
        logger.info(
            "Done: %s x %s — score=%d/100 (%s), tokens=%d",
            scenario.id, slug, judgment.score, judgment.holistic,
            total_usage.total_tokens,
        )

        return {
            "scenario_id": scenario.id,
            "model": target_model,
            "model_slug": slug,
            "score": judgment.score,
            "holistic": judgment.holistic,
            "checklist": judgment.checklist.model_dump(),
            "total_tokens": total_usage.total_tokens,
        }

    except Exception:
        logger.exception("Failed: %s x %s", scenario.id, slug)
        return None


def _write_summary(run_dir: Path, all_results: list[dict], failures: list[dict] | None = None) -> None:
    lines = ["# drift-bench run summary\n"]

    if failures:
        lines.append("## Failures\n")
        for f in failures:
            lines.append(f"- **{f['scenario_id']}** x {f['model_slug']}")
        lines.append("")

    if not all_results:
        lines.append("No successful results.\n")
        (run_dir / "summary.md").write_text("\n".join(lines))
        return

    # Per-pair table
    lines.append("## Results\n")
    lines.append("| Scenario | Model | Score | Holistic | Tokens |")
    lines.append("|----------|-------|------:|----------|------:|")

    for r in all_results:
        lines.append(
            f"| {r['scenario_id']} | {r['model_slug']} "
            f"| {r['score']} | {r['holistic']} | {r['total_tokens']:,} |"
        )

    # Per-model averages
    from collections import defaultdict
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in all_results:
        by_model[r["model_slug"]].append(r)

    lines.append("\n## Per-model averages\n")
    lines.append("| Model | Avg Score | Min | Max | n |")
    lines.append("|-------|------:|----:|----:|:-:|")

    for slug, results in sorted(by_model.items(), key=lambda x: sum(r["score"] for r in x[1]) / len(x[1])):
        scores = [r["score"] for r in results]
        avg = sum(scores) / len(scores)
        lines.append(f"| {slug} | {avg:.0f} | {min(scores)} | {max(scores)} | {len(scores)} |")

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
    failures: list[dict] = []

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
                pair_dir, config.force, config.rejudge,
            )
            if result:
                all_results.append(result)
            else:
                failures.append({
                    "scenario_id": scenario.id,
                    "model": model,
                    "model_slug": _model_slug(model),
                })

    _write_summary(run_dir, all_results, failures)
    logger.info("Summary written to %s/summary.md", run_dir)

    if failures:
        logger.error(
            "%d pair(s) failed: %s",
            len(failures),
            ", ".join(f"{f['scenario_id']}x{f['model_slug']}" for f in failures),
        )
        raise SystemExit(1)
