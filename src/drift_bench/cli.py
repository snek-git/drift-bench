from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone


def main():
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="drift-bench",
        description="Measure opinion drift in language models",
    )
    sub = parser.add_subparsers(dest="command")

    # --- run ---
    run_p = sub.add_parser("run", help="Run the benchmark")
    run_p.add_argument(
        "--scenario", required=True,
        help="Path to a scenario YAML file or directory of them",
    )
    run_p.add_argument(
        "--models", required=True,
        help="Comma-separated list of target model IDs (OpenRouter format)",
    )
    run_p.add_argument(
        "--sim-model",
        default="openrouter/anthropic/claude-sonnet-4-6",
        help="Model for the user simulator",
    )
    run_p.add_argument(
        "--judge-model",
        default="openrouter/anthropic/claude-sonnet-4-6",
        help="Model for the judge",
    )
    run_p.add_argument("--output-dir", default="runs")
    run_p.add_argument("--run-id", default=None)
    run_p.add_argument("--force", action="store_true", help="Ignore all checkpoints, re-run everything")
    run_p.add_argument("--rejudge", action="store_true", help="Re-run only the judge, keep cached conversations")
    run_p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Logging — verbose enables DEBUG for our code, but not for every HTTP library
    level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpcore", "httpx", "LiteLLM", "openai", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "run":
        _cmd_run(args)


def _cmd_run(args):
    from drift_bench.models import RunConfig
    from drift_bench.runner import run_benchmark

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    config = RunConfig(
        scenarios=[args.scenario],
        target_models=models,
        sim_model=args.sim_model,
        judge_model=args.judge_model,
        output_dir=args.output_dir,
        run_id=run_id,
        force=args.force,
        rejudge=args.rejudge,
    )

    asyncio.run(run_benchmark(config))
