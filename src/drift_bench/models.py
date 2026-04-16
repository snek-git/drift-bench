from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


# --- Scenario schema (loaded from YAML) ---


class BranchConfig(BaseModel):
    opinion: str
    direction: str
    label: str


class Scenario(BaseModel):
    id: str
    topic: str
    description: str
    target_system_prompt: str
    neutral_turns: int = Field(ge=1, le=10)
    branch_a: BranchConfig
    branch_b: BranchConfig
    follow_up_turns: int = Field(ge=0, le=5)
    follow_up_mode: Literal["continue", "neutral"] = "continue"
    seed_question: str | None = None


def load_scenario(path: Path) -> Scenario:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Scenario.model_validate(raw)


def load_scenarios(path: Path) -> list[Scenario]:
    p = Path(path)
    if p.is_file():
        return [load_scenario(p)]
    if not p.is_dir():
        raise FileNotFoundError(f"Scenario path does not exist: {p}")
    found = sorted(p.glob("*.yaml"))
    if not found:
        raise FileNotFoundError(f"No .yaml files found in: {p}")
    return [load_scenario(f) for f in found]


# --- Conversation data models ---


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class Turn(BaseModel):
    user_message: str
    assistant_message: str


class NeutralResult(BaseModel):
    turns: list[Turn]
    usage: Usage


class BranchResult(BaseModel):
    branch_id: Literal["a", "b"]
    opinion_turn: Turn
    follow_up_turns: list[Turn]
    usage: Usage


class Judgment(BaseModel):
    position_shift: int = Field(ge=0, le=10)
    hedging_asymmetry: int = Field(ge=0, le=10)
    framing_adoption: int = Field(ge=0, le=10)
    evidence_cherry_picking: int = Field(ge=0, le=10)
    overall_drift: int = Field(ge=0, le=10)
    reasoning: str


class PairResult(BaseModel):
    scenario_id: str
    target_model: str
    neutral: NeutralResult
    branch_a: BranchResult
    branch_b: BranchResult
    judgment: Judgment
    total_usage: Usage


# --- Run config ---


class RunConfig(BaseModel):
    scenarios: list[str]
    target_models: list[str]
    sim_model: str
    judge_model: str
    output_dir: str = "runs"
    run_id: str
    force: bool = False
