# Design and Alignment

## Refresh Context

Record the current commit and re-read every proposed integration file. Recheck the Issue state and relevant maintainer guidance because repository state may have changed since analysis.

## Define the Boundary

Write:

- one core problem;
- 2-3 explicit non-goals;
- observable or measurable success criteria;
- public API and backward-compatibility requirements;
- supported Python/Node/runtime versions from repository evidence;
- a target of about 300 changed lines and 1-3 core files, treated as planning bounds rather than guarantees;
- prohibited unrelated refactors or dependency changes.

If a safe solution exceeds the bound, propose smaller PRs and request a scope decision.

## Compare Solutions

Develop 2-3 materially different, feasible designs. For each include:

- 2-3 sentence approach;
- added/changed class, interface, function, or data contract;
- input -> processing -> output data flow;
- exact integration points;
- key signature or pseudocode;
- advantages;
- failure modes and maintenance risks;
- applicable situations.

Compare them in a matrix:

| Dimension | Solution 1 | Solution 2 | Solution 3 |
|---|---|---|---|
| Implementation complexity | | | |
| Intrusion into current code | | | |
| Extensibility | | | |
| Expected PR acceptance difficulty | | | |
| Interview narrative value | | | |

Recommend one with repository-specific reasons. Do not pretend estimates are measurements.

## Implementation Plan

List new files with responsibility and estimated lines. List modified files with exact change and small/medium/large magnitude. Order steps so each has an observable check and leaves the project runnable.

Define:

- a terminal-runnable minimal demo;
- 2-3 core unit behaviors at minimum;
- happy path and applicable empty, long-input, tool-failure, and legacy cases;
- integration, lint, format, type, and compatibility checks required by the project;
- how baseline failures will be distinguished from regressions.

Create a provisional interview outline, but label PR status, metrics, feedback, and outcomes as pending until evidence exists.

## Alignment Rule

Require maintainer alignment before core features, architecture/public API changes, new tools/integrations, or dependencies. A small bug, test, or docs change may record a waiver only when a clear open Issue and CONTRIBUTING policy already invite that work.

Draft an English comment of at most 150 words:

1. describe the observed problem objectively;
2. propose the direction without over-designing in public;
3. ask whether maintainers would accept it or have existing plans.

Do not claim the Issue or publish the draft without exact-target authorization. Record `required`, `waived(reason)`, `requested(url)`, `accepted(url)`, `redirected(url)`, or `rejected(url)`. Silence remains `requested`, not `accepted`.

Return to analysis/design after a redirect or rejection. Revalidate the Issue immediately before coding because another contributor may claim it.
