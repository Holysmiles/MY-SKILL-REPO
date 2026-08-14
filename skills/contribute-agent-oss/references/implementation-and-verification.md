# Implementation and Verification

## Readiness Snapshot

Before editing, capture:

- repository path, HEAD, current/default/base branches, remotes, upstream/fork relationship, submodules/LFS;
- dirty, staged, and untracked paths without modifying them;
- target files and their current symbols/call chain;
- runtime and dependency manifests;
- formatter, linter, type checker, test runner, coverage, commit, DCO/CLA, and AI-use rules;
- README quickstart/test commands and their likely side effects.

Do not execute an unreviewed repository command merely because documentation says to. Installation hooks, build tasks, tests, and demos may access the network, credentials, external services, GPUs, or paid APIs. Obtain the needed permission and use an isolated environment.

Run the narrowest safe baseline that establishes current behavior. Record the exact command, environment-relevant versions, UTC time, exit code, and failure summary. Keep pre-existing failures separate from regressions.

## Worktree Integrity

Preserve user changes and concurrent edits. Never use destructive reset, clean, checkout/restore, or force-push. Inspect overlapping changes immediately before each edit and adapt to them. Keep analysis workspaces outside the repository and stage only exact intended files.

If a dirty worktree overlaps target files, either isolate the contribution safely in an authorized worktree/branch or stop for direction. Do not attribute pre-existing changes to the contribution.

## Interface Checkpoint

Define signatures and contracts before core logic. Keep the project runnable by choosing one:

- an unconnected interface declaration;
- a backward-compatible default implementation;
- a test-first contract that does not change runtime paths.

Avoid a reachable `pass` or `NotImplementedError`. Report interfaces, data flow, integration points, missing dependencies, conflicts, and design deviations. Pause when the interface is public, adds a new abstraction, or the user requested staged approval.

Stop for user choice when:

- planned file or behavior scope expands materially;
- compatibility cannot be preserved;
- two designs have a meaningful product/maintenance tradeoff;
- a new third-party dependency is required.

Adapt pseudocode, add obvious error handling, and fit tests to repository structure without pausing, but disclose the deviation.

## Incremental Implementation

Implement one independently verifiable behavior at a time:

1. core logic;
2. error handling;
3. existing-call-chain integration;
4. tests and demo;
5. documentation required by project policy.

Prefer existing abstractions, dependencies, naming, typing, comments, and error models. Extend before altering public behavior. Keep unrelated refactors out of the diff. After each step run a focused check and record the result.

For every changed file report what changed and why any design deviation was needed. Verify old calls, the new trigger path, and errors during integration.

## Verification Matrix

Cover only applicable behaviors, and state `not applicable` with a reason instead of inventing a test:

| Behavior | Evidence |
|---|---|
| Happy path | Targeted unit/integration test and demo |
| Empty input | Defined validation/default behavior |
| Long input | Boundary/token/size behavior |
| Tool failure | Error propagation, retry, or fallback |
| Legacy usage | Existing tests or explicit compatibility test |

Run the repository's relevant unit/integration suite, formatter/linter, type checker, and a minimal terminal demo. Capture command, exit code, key output, counts, and duration when available. Never report a test as passing if it was skipped, blocked, or not run.

Compare post-change results with baseline. Inspect `git diff --check`, diff stats, unexpected generated files, lockfile/dependency changes, debug output, secrets, and personal paths.

## Delivery Report

Include:

- file-by-file add/modify/delete summary;
- behavior and compatibility evidence;
- baseline versus post-change commands/results;
- demo command/output;
- unverified items and environmental blockers;
- design deviations and risks;
- 2-4 single-purpose commits using project convention (the repository's squash/commit policy wins).
