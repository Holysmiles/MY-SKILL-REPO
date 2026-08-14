#!/usr/bin/env python3
"""Manage an evidence-gated AI Agent open-source contribution workspace."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASES = (
    "intake",
    "discovery",
    "analysis",
    "selection",
    "design",
    "alignment",
    "readiness",
    "interface",
    "implementation",
    "verification",
    "pr",
    "review",
    "narrative",
    "complete",
)

ARTIFACT_FILES = {
    "project_shortlist": "project-shortlist.md",
    "contribution_analysis": "contribution-analysis.md",
    "solution_design": "solution-design.md",
    "maintainer_comment": "maintainer-comment.txt",
    "implementation_report": "implementation-report.md",
    "pr_body": "pr-body.md",
    "follow_up_comment": "follow-up-comment.txt",
    "review_log": "review-log.md",
    "interview_story": "interview-story.md",
    "action_checklists": "action-checklists.md",
}


class StateError(RuntimeError):
    """Raised when state or a phase transition is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def state_path(workspace: Path) -> Path:
    return workspace.resolve() / "state.json"


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def normalize_target_local_path(workspace: Path, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StateError("target.local_path must be a non-empty path string or null")
    repository = Path(value).expanduser().resolve()
    resolved_workspace = workspace.expanduser().resolve()
    if path_is_within(resolved_workspace, repository):
        raise StateError(
            "contribution workspace must not be equal to or inside the target repository"
        )
    return str(repository)


def load_state(workspace: Path) -> dict[str, Any]:
    path = state_path(workspace)
    if not path.is_file():
        raise StateError(f"State file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Cannot read valid state from {path}: {exc}") from exc
    if data.get("schema_version") != 1 or data.get("phase") not in PHASES:
        raise StateError(f"Unsupported or invalid state file: {path}")
    return data


def write_state(workspace: Path, state: dict[str, Any]) -> None:
    path = state_path(workspace)
    if path.is_symlink():
        raise StateError(f"Refusing to write state through a symlink: {path}")
    state["updated_at"] = utc_now()
    serialized = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=".state-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(serialized)
            temporary = Path(handle.name)
        if path.is_symlink():
            raise StateError(f"Refusing to write state through a symlink: {path}")
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def template_state() -> dict[str, Any]:
    path = skill_root() / "assets" / "templates" / "contribution-state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Cannot load bundled state template {path}: {exc}") from exc


def init_workspace(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    if workspace.exists():
        if not workspace.is_dir():
            raise StateError(f"Contribution workspace is not a directory: {workspace}")
        try:
            next(workspace.iterdir())
        except StopIteration:
            pass
        else:
            raise StateError(f"Refusing to initialize a non-empty workspace: {workspace}")

    local_path = normalize_target_local_path(workspace, args.local_path)
    path = state_path(workspace)

    workspace.mkdir(parents=True, exist_ok=True)
    artifacts_dir = workspace / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    state = copy.deepcopy(template_state())
    state["created_at"] = utc_now()
    state["updated_at"] = state["created_at"]
    state["profile"]["objective"] = args.objective
    state["profile"]["tech_stack"] = args.tech_stack or []
    state["profile"]["timebox_days"] = args.timebox_days
    state["target"]["repository"] = args.repo
    state["target"]["local_path"] = local_path

    templates = skill_root() / "assets" / "templates"
    for key, filename in ARTIFACT_FILES.items():
        source = templates / filename
        destination = artifacts_dir / filename
        if not source.is_file():
            raise StateError(f"Bundled artifact template is missing: {source}")
        shutil.copyfile(source, destination)
        state["artifacts"][key] = str(destination)

    state["history"].append(
        {
            "at": utc_now(),
            "event": "initialized",
            "phase": "intake",
            "detail": "Contribution workspace created from bundled templates.",
        }
    )
    write_state(workspace, state)
    print(path)
    return 0


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def set_nested(state: dict[str, Any], field: str, value: Any) -> None:
    parts = field.split(".")
    if not parts or any(not part for part in parts):
        raise StateError(f"Invalid field path: {field!r}")
    cursor: dict[str, Any] = state
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            raise StateError(f"Field prefix is not an object: {part!r}")
        cursor = next_value
    leaf = parts[-1]
    if leaf not in cursor:
        raise StateError(f"Unknown field: {field}")
    cursor[leaf] = value


def set_field(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    state = load_state(workspace)
    value = parse_value(args.value)
    if args.field == "target.local_path":
        value = normalize_target_local_path(workspace, value)
    set_nested(state, args.field, value)
    state["history"].append(
        {
            "at": utc_now(),
            "event": "field-set",
            "phase": state["phase"],
            "detail": {"field": args.field},
        }
    )
    write_state(workspace, state)
    return show_state(argparse.Namespace(workspace=args.workspace, compact=False))


def record_action(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    state = load_state(workspace)
    record = {
        "at": utc_now(),
        "kind": args.kind,
        "target": args.target,
        "authorization": args.authorization,
        "status": args.status,
        "url": args.url,
        "detail": args.detail,
    }
    state["external_actions"].append(record)
    state["history"].append(
        {
            "at": record["at"],
            "event": "external-action-recorded",
            "phase": state["phase"],
            "detail": {"kind": args.kind, "status": args.status},
        }
    )
    write_state(workspace, state)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def parse_utc(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateError(f"Invalid ISO timestamp: {raw!r}") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def follow_up_status(
    state: dict[str, Any], at: datetime, minimum_days: int, preferred_days: int
) -> dict[str, Any]:
    pull_request = state["pull_request"]
    pr_state = str(pull_request.get("state") or "").casefold()
    result: dict[str, Any] = {
        "eligible": False,
        "decision": "unknown",
        "pull_request_state": pr_state,
        "policy_must_be_checked": True,
    }
    if pr_state in {"not-created", "draft-only", "closed", "merged"}:
        result["decision"] = "not-applicable"
        result["reason"] = f"PR state is {pr_state or 'unknown'}"
        return result
    reference_raw = (
        pull_request.get("last_human_activity_at") or pull_request.get("created_at")
    )
    if not reference_raw:
        result["reason"] = "PR creation or last human activity timestamp is missing"
        return result
    reference = parse_utc(str(reference_raw))
    if at < reference:
        result["reason"] = "evaluation time precedes the recorded activity"
        return result
    elapsed_days = (at - reference).total_seconds() / 86400
    result["days_since_human_activity"] = round(elapsed_days, 2)

    previous_raw = pull_request.get("last_follow_up_at")
    if previous_raw:
        previous = parse_utc(str(previous_raw))
        if previous >= reference:
            result["decision"] = "wait"
            result["reason"] = "a follow-up already occurred after the latest human activity"
            return result
    if elapsed_days < minimum_days:
        result["decision"] = "wait"
        result["reason"] = f"minimum quiet period is {minimum_days} days"
        return result
    result["eligible"] = True
    result["decision"] = "eligible"
    result["reason"] = (
        f"quiet period reached; the usual preferred window is "
        f"{minimum_days}-{preferred_days} days"
    )
    result["beyond_preferred_window"] = elapsed_days > preferred_days
    return result


def check_follow_up(args: argparse.Namespace) -> int:
    state = load_state(Path(args.workspace))
    if args.at:
        try:
            at_date = datetime.strptime(args.at, "%Y-%m-%d").date()
        except ValueError as exc:
            raise StateError("--at must use YYYY-MM-DD") from exc
        at = datetime.combine(at_date, datetime.min.time(), tzinfo=timezone.utc)
    else:
        at = datetime.now(timezone.utc)
    result = follow_up_status(state, at, args.min_days, args.preferred_days)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["eligible"] else 2


def show_state(args: argparse.Namespace) -> int:
    state = load_state(Path(args.workspace))
    if getattr(args, "compact", False):
        summary = {
            "phase": state["phase"],
            "completion_state": state["completion_state"],
            "target": state["target"],
            "alignment": state["alignment"]["status"],
            "baseline": state["baseline"]["result"],
            "interface": state["interface_checkpoint"]["status"],
            "verification": state["verification"]["status"],
            "pull_request": state["pull_request"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def artifact_ready(state: dict[str, Any], key: str) -> tuple[bool, str]:
    raw = state.get("artifacts", {}).get(key)
    if not raw:
        return False, f"artifact path not recorded: {key}"
    path = Path(raw)
    if not path.is_file():
        return False, f"artifact does not exist: {path}"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"artifact is unreadable: {path}: {exc}"
    if not content.strip():
        return False, f"artifact is empty: {path}"
    if "{{REQUIRED:" in content:
        return False, f"artifact still has required placeholders: {path}"
    return True, str(path)


def phase_requirements(state: dict[str, Any], destination: str) -> list[str]:
    errors: list[str] = []

    def require_value(path: str, value: Any) -> None:
        if not nonempty(value):
            errors.append(f"missing state value: {path}")

    def require_artifact(key: str) -> None:
        ready, detail = artifact_ready(state, key)
        if not ready:
            errors.append(detail)

    def require_validated_artifact(key: str) -> None:
        before = len(errors)
        require_artifact(key)
        if len(errors) != before:
            return
        try:
            from validate_evidence import (
                validate_analysis,
                validate_design,
                validate_implementation,
                validate_interview,
                validate_pr,
            )
        except ImportError as exc:
            errors.append(f"cannot load bundled artifact validator: {exc}")
            return
        path = Path(state["artifacts"][key])
        if key == "contribution_analysis":
            local_path = state["target"].get("local_path")
            repo = Path(local_path).resolve() if local_path and Path(local_path).is_dir() else None
            result = validate_analysis(path, repo)
        elif key == "solution_design":
            comment = Path(state["artifacts"]["maintainer_comment"])
            result = validate_design(path, comment)
        elif key == "implementation_report":
            result = validate_implementation(path)
        elif key == "pr_body":
            result = validate_pr(path)
        elif key == "interview_story":
            result = validate_interview(path)
        else:
            return
        errors.extend(f"{key}: {error}" for error in result.errors)

    if destination == "discovery":
        require_value("profile.objective", state["profile"]["objective"])
        if not state["profile"]["tech_stack"]:
            errors.append("profile.tech_stack must record the user's stack or ['unspecified']")
    elif destination == "analysis":
        require_value("target.repository", state["target"]["repository"])
        require_artifact("project_shortlist")
    elif destination == "selection":
        require_validated_artifact("contribution_analysis")
    elif destination == "design":
        if not (state["target"]["issue_url"] or state["target"]["direction"]):
            errors.append("select target.issue_url or target.direction")
    elif destination == "alignment":
        require_validated_artifact("solution_design")
    elif destination == "readiness":
        alignment = state["alignment"]
        if alignment["status"] not in {"accepted", "waived"}:
            errors.append("alignment.status must be 'accepted' or 'waived'")
        if alignment["status"] == "accepted":
            require_value("alignment.evidence_url", alignment["evidence_url"])
        if alignment["status"] == "waived":
            require_value("alignment.reason", alignment["reason"])
        require_value("target.local_path", state["target"]["local_path"])
    elif destination == "interface":
        baseline = state["baseline"]
        for key in ("commit", "command", "exit_code", "result", "evidence_path"):
            require_value(f"baseline.{key}", baseline[key])
    elif destination == "implementation":
        checkpoint = state["interface_checkpoint"]
        if checkpoint["status"] not in {"approved", "unchanged", "not-applicable"}:
            errors.append(
                "interface_checkpoint.status must be approved, unchanged, or not-applicable"
            )
        require_value("interface_checkpoint.reason", checkpoint["reason"])
        require_value("interface_checkpoint.evidence_path", checkpoint["evidence_path"])
    elif destination == "verification":
        require_validated_artifact("implementation_report")
    elif destination == "pr":
        verification = state["verification"]
        if verification["status"] != "passed":
            errors.append("verification.status must be 'passed'")
        if not verification["commands"]:
            errors.append("verification.commands must contain real command results")
        require_value("verification.evidence_path", verification["evidence_path"])
        require_validated_artifact("pr_body")
    elif destination == "review":
        pull_request = state["pull_request"]
        require_value("pull_request.url", pull_request["url"])
        if pull_request["state"] in {"not-created", "draft-only"}:
            errors.append("pull_request.state must describe an actual remote PR")
    elif destination == "narrative":
        require_artifact("review_log")
    elif destination == "complete":
        require_validated_artifact("interview_story")
        require_artifact("action_checklists")
    return errors


def advance(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    state = load_state(workspace)
    current_index = PHASES.index(state["phase"])
    if current_index == len(PHASES) - 1:
        raise StateError("Workflow is already complete")
    expected = PHASES[current_index + 1]
    destination = args.to or expected
    if destination != expected:
        raise StateError(
            f"Cannot skip or reverse phases: current={state['phase']}, next={expected}, "
            f"requested={destination}"
        )
    errors = phase_requirements(state, destination)
    if errors:
        joined = "\n- ".join(errors)
        raise StateError(f"Gate for {destination!r} failed:\n- {joined}")

    previous = state["phase"]
    state["phase"] = destination
    completion_by_phase = {
        "selection": "analyzed",
        "alignment": "designed",
        "interface": "implementation-ready",
        "pr": "pr-ready",
        "review": "pr-open",
        "complete": "narrative-complete",
    }
    if destination in completion_by_phase:
        state["completion_state"] = completion_by_phase[destination]
    state["history"].append(
        {
            "at": utc_now(),
            "event": "phase-advanced",
            "phase": destination,
            "detail": {"from": previous, "to": destination},
        }
    )
    write_state(workspace, state)
    print(f"{previous} -> {destination}")
    return 0


def check(args: argparse.Namespace) -> int:
    state = load_state(Path(args.workspace))
    index = PHASES.index(state["phase"])
    if index == len(PHASES) - 1:
        print("complete")
        return 0
    destination = PHASES[index + 1]
    errors = phase_requirements(state, destination)
    result = {
        "current_phase": state["phase"],
        "next_phase": destination,
        "ready": not errors,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and enforce an evidence-gated contribution workflow."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a contribution workspace")
    init_parser.add_argument("workspace")
    init_parser.add_argument("--objective", default="Complete a reviewable AI Agent OSS contribution")
    init_parser.add_argument("--repo")
    init_parser.add_argument("--local-path")
    init_parser.add_argument("--tech-stack", action="append", default=[])
    init_parser.add_argument("--timebox-days", type=int, default=14)
    init_parser.set_defaults(func=init_workspace)

    show_parser = subparsers.add_parser("show", help="print current state")
    show_parser.add_argument("workspace")
    show_parser.add_argument("--compact", action="store_true")
    show_parser.set_defaults(func=show_state)

    set_parser = subparsers.add_parser("set", help="set an existing dotted state field")
    set_parser.add_argument("workspace")
    set_parser.add_argument("field")
    set_parser.add_argument("value", help="JSON value when parseable, otherwise a string")
    set_parser.set_defaults(func=set_field)

    action_parser = subparsers.add_parser(
        "record-action", help="record authorization/result; never performs the action"
    )
    action_parser.add_argument("workspace")
    action_parser.add_argument("--kind", required=True)
    action_parser.add_argument("--target", required=True)
    action_parser.add_argument("--authorization", required=True)
    action_parser.add_argument(
        "--status", required=True, choices=("authorized", "performed", "failed", "revoked")
    )
    action_parser.add_argument("--url")
    action_parser.add_argument("--detail")
    action_parser.set_defaults(func=record_action)

    advance_parser = subparsers.add_parser("advance", help="advance exactly one gated phase")
    advance_parser.add_argument("workspace")
    advance_parser.add_argument("--to", choices=PHASES)
    advance_parser.set_defaults(func=advance)

    check_parser = subparsers.add_parser("check", help="check readiness for the next phase")
    check_parser.add_argument("workspace")
    check_parser.set_defaults(func=check)

    follow_up_parser = subparsers.add_parser(
        "follow-up", help="check the 7-14 day follow-up window without publishing"
    )
    follow_up_parser.add_argument("workspace")
    follow_up_parser.add_argument("--at", help="fixed UTC date in YYYY-MM-DD form")
    follow_up_parser.add_argument("--min-days", type=int, default=7)
    follow_up_parser.add_argument("--preferred-days", type=int, default=14)
    follow_up_parser.set_defaults(func=check_follow_up)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "timebox_days", 1) < 1:
        parser.error("--timebox-days must be positive")
    if hasattr(args, "min_days"):
        if args.min_days < 1 or args.preferred_days < args.min_days:
            parser.error("follow-up days must satisfy 1 <= min-days <= preferred-days")
    try:
        return int(args.func(args))
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
