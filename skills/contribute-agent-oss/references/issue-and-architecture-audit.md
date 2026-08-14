# Issue and Architecture Audit

## Repository Understanding

Read files that exist; record those that do not:

- README and package/module READMEs;
- CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, governance, CLA/DCO, and AI-use policy;
- CHANGELOG or HISTORY;
- package manifests, runtime/version, lint, format, type, and test configuration;
- likely entry points and the concrete call chain implementing the Agent loop.

Generate a depth-3 tree that excludes `.git`, dependencies, build output, generated/vendor trees, caches, secrets, and binary data. In a monorepo, identify each relevant package before selecting one. Describe the main Agent loop and planning paradigm (ReAct, Plan-and-Execute, CoT, or no explicit planning) in 2-3 sentences. Cite `path:symbol` evidence; use `unknown` when no defensible classification exists.

## Issue Triage

Use the union of labels found throughout the handbook:

- `good first issue`
- `help wanted`
- `bug`
- `documentation`
- `enhancement`

Require all applicable hard conditions:

- state is open;
- updated within the previous 60 days, with the boundary treated inclusively;
- no assignee;
- no active claim in comments, linked PRs, or maintainer status;
- description contains expected behavior or reproducible/acceptance detail;
- likely scope is 1-3 files and does not require a repository-wide redesign.

Use comment phrase matching only as a prefilter. Review semantic variants, retracted claims, quoted text, bots, translations, and linked work. Mark ambiguity for human review. Estimate clarity and file scope from source evidence; never present them as API facts.

Classify contribution types as docs/translation, bug, tests, tool/integration, or core feature. Prefer a bug, tested fix, or scoped integration for interview depth. Keep documentation candidates but explain their lower technical narrative value when applicable.

Output both accepted and rejected candidates with reasons, evidence links, confidence, required skills, and effort. Return an empty list when none qualify.

## Seven-Dimension Audit

Inspect every dimension. For a missing capability, cite the search terms, directories, and call chain inspected before stating `not found in inspected scope`.

1. **Task planning:** decomposition, explicit plan creation, re-planning after failure, persistence, checkpoint/resume, and whether a planning layer fits.
2. **Multi-Agent collaboration:** topology, orchestrator/worker roles, communication protocol, aggregation, state sharing, and natural decomposition opportunities.
3. **Context management:** hard truncation, rolling windows, summarization, token accounting, retention of tool history/intermediate results, cross-turn storage, and differentiated handling of instructions/tools/dialogue.
4. **Human-in-the-loop:** risk/confidence gates, pause/approval for writes/APIs/messages, checkpoints, resume, and incorporation of human feedback.
5. **Evaluation:** eval modules/data, final-output versus trajectory evaluation, tool-choice/argument scoring, LangSmith/Arize/custom integrations, reproducibility, and minimal-pipeline cost.
6. **Tool retrieval/routing:** full-schema injection versus retrieval, behavior above about 20 tools, semantic collisions, selection telemetry, MCP support, and feasible integration points.
7. **Streaming and intermediate state:** token streaming, current task/tool/arguments visibility, event/state subscriptions, backpressure/errors, and low-intrusion broadcast options.

For each dimension use exactly:

```markdown
### <Dimension>
**Current state:** <path:symbol evidence>
**Gap:** <problem, absence, or unknown>
**Impact:** high | medium | low
**Improvement:** <1-3 sentences>
**Change scope:** <estimated files and line range, with confidence>
**Interview angle:** <one sentence>
```

## Ranking Directions

Combine eligible Issues and architecture findings. Rank at most three using:

- one-sentence contribution;
- source: Issue URL or architecture dimension;
- entry files/symbols;
- fit to the user's actual stack;
- small/medium/large effort and basis;
- interview value through a concrete decision or measurable behavior;
- maintainer-acceptance and implementation risks;
- confidence and unresolved questions.

Prefer a small accepted Issue over a speculative architectural feature unless the latter has maintainer interest. Do not rank security vulnerabilities for public Issue/PR handling; follow private disclosure policy.
