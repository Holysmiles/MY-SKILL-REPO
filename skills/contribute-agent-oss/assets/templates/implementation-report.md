# Implementation Report

## Readiness

- Repository/HEAD/base/head: {{REQUIRED:git_context}}
- Existing worktree changes preserved: {{REQUIRED:evidence_or_clean}}
- Policies/configs read: {{REQUIRED:paths}}
- Target files read before editing: {{REQUIRED:paths}}
- Baseline command/exit/result: {{REQUIRED:evidence}}
- Alignment evidence or waiver: {{REQUIRED:evidence}}

## Interface Checkpoint

- Status: {{REQUIRED:unchanged_confirmed_or_approved}}
- Interfaces/signatures: {{REQUIRED:value_or_none}}
- Integration points: {{REQUIRED:path_symbols}}
- Dependencies/conflicts/deviations: {{REQUIRED:value_or_none}}

## File Changes

| File | Operation | Behavior | Design deviation |
|---|---|---|---|
| {{REQUIRED:path}} | {{REQUIRED:add_modify_delete}} | {{REQUIRED:change}} | {{REQUIRED:value_or_none}} |

## Integration

- Legacy calls: {{REQUIRED:evidence}}
- New trigger path: {{REQUIRED:evidence}}
- Error branches: {{REQUIRED:evidence}}
- Public API/backward compatibility: {{REQUIRED:evidence}}

## Verification

| Type | Command | Exit | Observed result | Baseline comparison |
|---|---|---:|---|---|
| Happy path | {{REQUIRED:command}} | {{REQUIRED:exit}} | {{REQUIRED:result}} | {{REQUIRED:comparison}} |
| Empty input | {{REQUIRED:command_or_na_reason}} | {{REQUIRED:exit_or_na}} | {{REQUIRED:result}} | {{REQUIRED:comparison_or_na}} |
| Long input | {{REQUIRED:command_or_na_reason}} | {{REQUIRED:exit_or_na}} | {{REQUIRED:result}} | {{REQUIRED:comparison_or_na}} |
| Tool failure | {{REQUIRED:command_or_na_reason}} | {{REQUIRED:exit_or_na}} | {{REQUIRED:result}} | {{REQUIRED:comparison_or_na}} |
| Legacy compatibility | {{REQUIRED:command}} | {{REQUIRED:exit}} | {{REQUIRED:result}} | {{REQUIRED:comparison}} |

## Demo

- Command: {{REQUIRED:command}}
- Exit code: {{REQUIRED:exit}}
- Key output: {{REQUIRED:output}}

## Diff and Risk Review

- Diff stat: {{REQUIRED:value}}
- Unexpected/generated/lock/dependency changes: {{REQUIRED:none_or_list}}
- Secret/PII scan: {{REQUIRED:method_and_result}}
- Unverified items: {{REQUIRED:none_or_list}}
- Remaining risks: {{REQUIRED:none_or_list}}

## Commit Plan

1. `{{REQUIRED:type_scope_description}}` - {{REQUIRED:files_and_reason}}
2. `{{OPTIONAL:type_scope_description}}` - {{OPTIONAL:files_and_reason}}
3. `{{OPTIONAL:type_scope_description}}` - {{OPTIONAL:files_and_reason}}
4. `{{OPTIONAL:type_scope_description}}` - {{OPTIONAL:files_and_reason}}
