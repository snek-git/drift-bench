# Benchmark Design Notes

This memo captures the design discussion around `drift-bench`: what user
frustration it is trying to measure, what the current benchmark does well, where
it is ambiguous, and what a good MVP should look like without overengineering
the project.

## The Real Failure Mode

The frustrating behavior is not simply that a model agrees with the user.
Sometimes agreement is appropriate. The deeper frustration is that the model can
feel epistemically unserious:

- It has no durable view of the topic.
- It changes standards depending on what the user wants.
- It validates weak claims too quickly.
- It retrieves different evidence for different users.
- It fails to push back when the user has not earned the concession.
- It sounds principled, but behaves like a mirror.

The core failure is:

> The model fails to maintain an independent standard of reasoning when exposed
> to one-sided user advocacy.

That framing is better than "does the model ever change its mind?" A good model
should update when the user gives strong evidence. The failure is updating
because the user asserted or argued for a position, not because the evidence
justified the update.

## User-Visible Failure Modes

The benchmark should be clear about which failure modes it is measuring.

### 1. Reflexive Validation

The model opens with phrases like "That's understandable", "You're right to
think that", or "Great point" before doing much reasoning.

This is not always branch drift, because the model may validate both sides
equally. But it is still a user-visible failure mode: the model seems too eager
to bless the user's premise.

### 2. Opinion Mirroring

The model's conclusion shifts toward the user's stated position even when the
user has not introduced strong new evidence.

This is the central behavior the current benchmark is aimed at.

### 3. Motivated Evidence Selection

The model cites pro-A evidence in Branch A and pro-B evidence in Branch B, even
though the underlying topic and neutral context were the same.

This may be one of the strongest signals. A model can preserve a balanced final
answer while still building a different evidentiary world for each user.

### 4. Concession Under Pressure

The model gives up its prior framing when the user pushes back, even if the
pushback is mostly restatement, confidence, emotional pressure, or weak
argument.

The important distinction is whether the user earned the concession.

### 5. Frame Capture

The model adopts the user's terms, assumptions, and emotionally loaded framing.
For example, it starts using phrases like "productivity theater", "AI slop", or
"legacy monolith mindset" because the user did.

The bottom-line recommendation might remain nuanced, but the model's frame has
still been captured.

### 6. Criteria Inconsistency

The model applies different standards in different branches. For example, in one
branch it treats autonomy as the dominant criterion, while in the other it treats
standardization as the dominant criterion.

This is close to the heart of the issue. The model should preserve stable
decision criteria even when the user advocates for one side.

### 7. False Neutrality

Some models avoid drift by refusing to take any stance: "it depends", "both
sides have merit", "context matters", forever.

That may score well on stability, but it can still be bad product behavior. The
benchmark should not accidentally reward useless mush as ideal reasoning.

### 8. Overcorrection

A model may resist the user just to avoid appearing sycophantic. That is also
bad. The goal is not "never move"; the goal is "move in proportion to evidence."

## What The Current Benchmark Measures

The current design is a good research harness. It measures branch-conditioned
divergence:

1. A shared neutral conversation happens first.
2. The conversation forks.
3. Branch A receives one user opinion.
4. Branch B receives the opposing user opinion.
5. The assistant responds and continues.
6. A judge extracts checklist facts.
7. Python computes a deterministic 0-100 score.

This is a strong skeleton. It is much better than asking a judge model for a
single vibe score. The checklist approach gives more observable handles:

- Can the assistant-only text reveal which opinion the user expressed?
- Did the bottom-line positions differ?
- Did the assistant concede differently?
- Did the evidence differ?
- Did validation differ?
- Did confidence differ?

The current benchmark is especially good at catching:

- Opinion mirroring.
- Evidence asymmetry.
- Framing differences.
- Branch-distinguishable assistant behavior.

## What It Does Not Fully Prove Yet

The current benchmark does not yet cleanly prove unjustified opinion drift.

The main issue is generated argumentative follow-ups. In real use, users argue
their claims. That realism matters. But if the simulator improvises arguments,
the two branches may differ in hidden ways:

- One side may make stronger arguments.
- One side may cite more concrete evidence.
- One side may be more emotionally loaded.
- One side may introduce facts the other side does not.
- One side may be more coherent or more aggressive.

Then, if the target model shifts more in one branch, the result is ambiguous. It
might be sycophancy, or the branch may simply have made a better case.

Other current limitations:

- There is no explicit baseline stance capture before the fork.
- The distinguishability check is not fully blind if the judge already sees the
  branch labels and user stances.
- One run per scenario/model is noisy.
- Evidence overlap is currently based on judge-authored free-text lists, which
  can make the deterministic score depend on fuzzy extraction.

## Clean MVP Versus Realistic MVP

There are two possible MVPs.

### Clean MVP

This version tests pure opinion mirroring.

The user says: "I am convinced X." No new arguments. The opposite branch says:
"I am convinced Y." No new arguments.

This is methodologically clean, but less like real-world usage.

### Realistic MVP

This version tests one-sided advocacy capture.

The user states an opinion and gives reasons. The opposite branch states the
opposite opinion and gives matched reasons.

This is closer to real usage, but only works if the arguments are controlled.
Otherwise the benchmark cannot tell whether model movement was justified.

## Recommended MVP

The best MVP is:

> Matched one-sided advocacy, with frozen branch messages, measuring whether the
> assistant maintains consistent reasoning standards under pressure.

This keeps the benchmark simple while making it closer to the actual user
frustration.

Recommended flow:

1. Run the shared neutral phase.
2. Capture a baseline stance from the target model after the neutral phase.
3. Fork into Branch A and Branch B.
4. In each branch, present a frozen user message with:
   - the user's opinion,
   - 2-3 reasons,
   - similar length,
   - similar pressure level,
   - similar specificity,
   - opposite direction.
5. Optionally include one scripted pushback per branch.
6. Run the target response.
7. Run a blind assistant-only distinguishability check.
8. Run a consistency checklist.
9. Compute the score deterministically in Python.

The core benchmark question should be:

> When exposed to matched one-sided advocacy, does the model preserve stable
> reasoning standards, or does its position, framing, evidence selection, and
> confidence become captured by the user's side?

## Why Freeze Or Hardcode Branch Arguments

Frozen branch messages are not about making the benchmark artificial. They are
about controlling the experimental variable.

The benchmark should compare:

> Same topic, same pressure level, same argumentative force, opposite direction.

That is difficult to guarantee if a simulator improvises the branch messages on
each run.

A good compromise:

1. Use a simulator or human brainstorming to generate candidate pro/con
   arguments.
2. Review and pair them for comparable strength, specificity, and pressure.
3. Freeze those branch messages in YAML.
4. Run the benchmark against the fixed scenario set.

This keeps realism without allowing randomness to leak into the score.

## Minimal Metrics

The benchmark should avoid trying to measure everything at once. A useful MVP
score could be built from:

- Stance movement from baseline.
- Branch divergence.
- Blind distinguishability from assistant-only text.
- Unsupported concession rate.
- Decision criteria consistency.
- Evidence symmetry.
- Frame adoption.
- Reflexive validation as a separate annoyance metric.
- Decisiveness/helpfulness as a separate utility metric.

The last two are important but should probably not be collapsed directly into
the main drift score. A model can be stable but unhelpfully vague, or helpful
but overly validating.

## Bottom Line

The current benchmark has the right skeleton. The forked-conversation design is
the correct basic move, and checklist extraction plus deterministic scoring is a
good direction.

The current version is best described as measuring conversational branch
divergence. To become a stronger benchmark for the target failure mode, it
should measure whether the model changes for the right reasons.

The non-overengineered next step is not a large taxonomy or complex judge
system. It is to freeze matched branch arguments, add baseline stance capture,
and make the distinguishability check blind.
