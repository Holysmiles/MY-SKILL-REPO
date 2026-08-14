# Interview Narrative

## Two-Pass Drafting

Create a provisional outline during design to expose weak reasoning, but keep future outcomes marked `pending`. Update it after implementation and whenever PR/review state changes. Never convert an intention into a result.

## Evidence-Backed Structure

### Context

Explain what the project solves in the Agent ecosystem, why it fit the user's goal, and the specific Issue or architecture gap found. Cite repository and analysis evidence.

### Contribution

Use one sentence:

```text
I implemented/improved/introduced <capability> in <module/call chain>, affecting <concrete path or user scenario>.
```

### Process

Describe 3-5 decisions rather than a file-edit chronology. Include target selection, the smallest integration point, design alternatives, compatibility tradeoffs, implementation sequencing, and validation strategy.

### Result

State the exact PR state and URL: draft, open, review requested, changes requested, approved, closed, or merged. Describe observable behavior. Include only reproducible metrics with command/data/source and baseline. Quote maintainer feedback verbatim with a link. Otherwise say `not measured` or `no maintainer feedback yet`.

### Challenges

For 1-2 real technical obstacles, cover:

- concrete symptom;
- investigation and evidence;
- root cause;
- chosen resolution and alternatives;
- resulting behavior.

Avoid vague claims such as "there were some problems."

### Reflection

Explain what should change next time across:

- technical design or validation;
- maintainer communication and PR splitting;
- scope that was unnecessary or a boundary that was missed.

### Capabilities

Map 2-3 demonstrated abilities to evidence, such as codebase comprehension, Agent architecture reasoning, design tradeoffs, testing, delivery, or maintainer collaboration.

## Truthfulness Checks

Reject or mark unknown:

- `merged` without GitHub merge evidence;
- performance/token/coverage percentages without reproducible before/after data;
- maintainer praise without an exact quote/link;
- team ownership when the contributor acted alone;
- test claims without commands and results;
- impact that depends on an unreleased or unmerged change.

Keep the narrative useful when a PR is still pending: focus on defensible decisions, implementation evidence, and what review could still change.
