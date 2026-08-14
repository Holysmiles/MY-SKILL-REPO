# Discovery and Screening

## Inputs and Query

Use the user's stack, experience, preferred language/framework, contribution type, and timebox. When no project is supplied, start with a query equivalent to:

```text
topic:ai-agent stars:>1000 pushed:>YYYY-MM-DD archived:false
```

Calculate `YYYY-MM-DD` from the execution date, normally 60-90 days earlier. Broaden topic terms or lower stars only when the first pass produces too few suitable candidates, and disclose the changed query. A repository supplied by the user still receives the same health review.

## Evidence Window

Record the UTC collection time, query, pagination completeness, authentication mode, sample size, and API failures. Prefer GitHub API/connector data over search snippets. Distinguish absent data from zero. When data is incomplete because of permissions, rate limits, or sampling, mark the affected conclusion `unknown` or `low confidence`.

## Project Signals

Report each signal separately before making a recommendation:

| Signal | Default healthy indication | Required evidence |
|---|---|---|
| Agent relevance | Agent loop/tool use/planning is central | README plus core-module evidence |
| Popularity | Usually >=1,000 stars | Current stargazer count |
| Recent maintenance | Commit within 30 days | Latest non-bot commit timestamp/link |
| Issue flow | closed/open ratio >1 | Counts and denominator; `N/A` if open=0 |
| PR responsiveness | Human first response usually <14 days | Median/sample, dates, sample size |
| PR merge speed | Recent viable PRs merge promptly | Separate median/sample; never call it response time |
| Releases | Monthly or quarterly cadence | Recent release dates; explain projects without releases |
| Documentation | README and contribution path are usable | Files inspected and gaps |
| Fit | User can make a scoped change in 7-14 days | Language, setup, module size, candidate work |

Do not convert these signals into an unexplained score. Stars, release cadence, and ratios are heuristics; a library can be healthy without frequent releases, and popularity does not imply contributor support.

For PR response, use the earliest non-author, non-bot maintainer/reviewer comment, review, or requested-change event. Report merge latency separately as `merged_at - created_at`. If maintainer identity is uncertain, say so.

## Exclusion Rules

Exclude or strongly downgrade a repository when evidence shows:

- archived/read-only status or prolonged inactivity;
- unanswered Issues and a large stale PR backlog;
- no usable setup/contribution documentation;
- contribution policy forbids the proposed AI-assisted workflow;
- setup, architecture, or test cost exceeds the timebox;
- no realistic match to the user's stack;
- only broad architectural rewrites are available;
- unresolved license, security, or governance concerns.

Explain every exclusion. Do not infer inactivity solely from missing releases.

## Candidate Output

For every candidate include:

- repository and evidence links;
- Agent relevance and core stack;
- stars, latest commit, Issue ratio;
- PR first-response and merge-latency samples;
- release dates/cadence;
- docs/setup assessment;
- estimated onboarding and contribution effort;
- matching contribution types;
- risks, unknowns, confidence, and recommendation.

Select one only after comparing candidates against the user's goal. Preserve raw observations so another reviewer can reproduce the choice.
