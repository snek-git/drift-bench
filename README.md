# drift-bench

Measures **opinion drift** in language models — whether a model shifts its stated position to match a user's opinion when no new arguments are introduced.

## How it works

```
1. NEUTRAL PHASE
   A user-simulator asks neutral questions about a topic.
   The target model responds. Neither side takes a stance.
   (3 turns by default)

2. FORK
   Branch A: user expresses opinion X    Branch B: user expresses opposing opinion Y
   Target responds to each.              Target responds to each.
   1-2 follow-up turns per branch.       1-2 follow-up turns per branch.

3. JUDGE
   A judge model reads both transcripts side by side
   and scores how much the target's position diverged.
```

If the model has stable views, both branches should produce substantively similar responses. If it doesn't, they'll diverge.

## What this measures

- **Position shift** — did the model take different positions across branches?
- **Hedging asymmetry** — did it hedge more in one direction?
- **Framing adoption** — did it mirror each user's terminology?
- **Evidence cherry-picking** — did it selectively emphasize different evidence?
- **Overall drift** — holistic 0-10 score

## What this does NOT measure

- Whether the model's position is "correct" (no ground truth)
- Whether the model ever changes its mind (legitimate updating on new arguments is fine)
- Whether the model agrees when the user is right (the test isolates bidirectional accommodation)

## Quick start

```bash
uv sync
export OPENROUTER_API_KEY=your-key-here
uv run drift-bench run \
    --scenario scenarios/dummy-remote-work.yaml \
    --models "openrouter/openai/gpt-4.1"
```

Results land in `runs/<run-id>/`. The `summary.md` file has the scores.

## CLI

```
drift-bench run \
    --scenario PATH          # YAML file or directory of them
    --models LIST            # comma-separated OpenRouter model IDs
    --sim-model MODEL        # user simulator (default: openrouter/anthropic/claude-sonnet-4-6)
    --judge-model MODEL      # judge (default: openrouter/anthropic/claude-sonnet-4-6)
    --output-dir DIR         # where runs go (default: runs/)
    --run-id ID              # custom run ID (default: timestamp)
    --force                  # ignore checkpoints, re-run everything
    -v / --verbose           # debug logging
```

## Adding scenarios

Scenarios are YAML files in `scenarios/`. No code changes needed.

```yaml
id: my-scenario
topic: "The topic being discussed"
description: "What this scenario tests"

target_system_prompt: |
  You are a knowledgeable assistant.

neutral_turns: 3

branch_a:
  opinion: "User's opinion leaning one way..."
  direction: "pro-X"
  label: "Pro X"

branch_b:
  opinion: "User's opposing opinion..."
  direction: "pro-Y"
  label: "Pro Y"

follow_up_turns: 2
follow_up_mode: "continue"   # or "neutral"

seed_question: "Optional first question to start the conversation"
```

Branch opinions are hardcoded (not generated) for tighter control over the experimental variable.

## Output structure

```
runs/<run-id>/
  config.json                              # frozen run config
  summary.md                               # scores table
  results/<scenario>__<model>/
    neutral.json                           # shared neutral phase
    branch_a.json                          # branch A transcript
    branch_b.json                          # branch B transcript
    judgment.json                          # judge scores
```

Runs are resumable — kill mid-run and re-run the same command to pick up where you left off.

## Known limitations

- The judge model has its own biases
- The user-simulator isn't perfectly deterministic
- Branch opinion equivalence is an assumption, not a guarantee
- One run per pair means no variance estimates
- We measure stated positions in text, not internal model state
