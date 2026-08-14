#!/usr/bin/env python3
"""Validate contribution artifacts without inventing or changing evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


REQUIRED_PLACEHOLDER = "{{REQUIRED:"
ARCHITECTURE_DIMENSIONS = (
    "Task Planning",
    "Multi-Agent Collaboration",
    "Context Management",
    "Human-in-the-Loop",
    "Evaluation",
    "Tool Retrieval and Routing",
    "Streaming and Intermediate State",
)
ARCHITECTURE_FIELDS = (
    "Current state",
    "Gap",
    "Impact",
    "Improvement",
    "Change scope",
    "Interview angle",
)


@dataclass
class Result:
    artifact: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def read_text(path: Path, result: Result) -> str:
    if not path.is_file():
        result.errors.append(f"file does not exist: {path}")
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result.errors.append(f"cannot read UTF-8 file {path}: {exc}")
        return ""
    if not text.strip():
        result.errors.append(f"file is empty: {path}")
    return text


def check_placeholders(text: str, result: Result) -> None:
    count = text.count(REQUIRED_PLACEHOLDER)
    if count:
        result.errors.append(f"{count} required template placeholder(s) remain")


def require_headings(text: str, headings: tuple[str, ...], result: Result) -> None:
    for heading in headings:
        if not re.search(rf"(?m)^#+\s+{re.escape(heading)}\s*$", text):
            result.errors.append(f"missing heading: {heading}")


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", text
    )
    return match.group(1) if match else ""


def validate_path_symbol_evidence(
    dimension_text: str, dimension: str, repo: Path | None, result: Result
) -> None:
    current = re.search(
        r"(?m)^\*\*Current state:\*\*\s*(.+?)(?:\s{2,}|$)", dimension_text
    )
    if not current:
        return
    value = current.group(1)
    evidence = re.findall(r"`([^`\r\n]+):([A-Za-z_$][\w.$<>-]*)`", value)
    if not evidence:
        result.errors.append(
            f"{dimension}: Current state needs backticked path:symbol evidence"
        )
        return
    if repo is None:
        return
    for raw_path, symbol in evidence:
        candidate = (repo / raw_path).resolve()
        try:
            candidate.relative_to(repo)
        except ValueError:
            result.errors.append(f"{dimension}: evidence path escapes repository: {raw_path}")
            continue
        if not candidate.is_file():
            result.errors.append(f"{dimension}: evidence path does not exist: {raw_path}")
            continue
        try:
            if candidate.stat().st_size > 2_000_000:
                result.warnings.append(
                    f"{dimension}: symbol not inspected in file larger than 2 MB: {raw_path}"
                )
                continue
            source = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.errors.append(f"{dimension}: cannot read evidence path {raw_path}: {exc}")
            continue
        simple_symbol = re.sub(r"[^A-Za-z0-9_$-]", "", symbol.split(".")[-1])
        found = bool(symbol and symbol in source)
        if simple_symbol and not found:
            found = bool(re.search(rf"\b{re.escape(simple_symbol)}\b", source))
        if not found:
            result.errors.append(
                f"{dimension}: symbol {symbol!r} was not found in {raw_path}"
            )


def validate_analysis(path: Path, repo: Path | None = None) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    require_headings(
        text,
        (
            "Evidence Scope",
            "Repository Tree (Depth 3)",
            "Agent Core",
            "Issue Candidates",
            "Rejected Issues",
            "Ranked Contribution Directions",
        )
        + ARCHITECTURE_DIMENSIONS,
        result,
    )

    for dimension in ARCHITECTURE_DIMENSIONS:
        body = section(text, dimension)
        if not body:
            continue
        for field_name in ARCHITECTURE_FIELDS:
            if not re.search(
                rf"(?m)^\*\*{re.escape(field_name)}:\*\*\s*\S", body
            ):
                result.errors.append(f"{dimension}: missing or empty field {field_name}")
        impact = re.search(r"(?mi)^\*\*Impact:\*\*\s*(high|medium|low)\b", body)
        if not impact:
            result.errors.append(f"{dimension}: Impact must be high, medium, or low")
        validate_path_symbol_evidence(body, dimension, repo, result)

    rank_numbers = {
        int(value)
        for value in re.findall(r"(?m)^###\s+Rank\s+([1-9][0-9]*)\b", text)
    }
    if 1 not in rank_numbers:
        result.errors.append("missing Rank 1 (use a documented no-viable-direction result)")
    if rank_numbers and max(rank_numbers) > 3:
        result.errors.append("more than three ranked directions are present")
    if "Collected at (UTC)" not in text or "Repository/commit" not in text:
        result.errors.append("evidence timestamp and repository commit are required")
    return result


def english_word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b", text))


def validate_design(path: Path, comment: Path | None = None) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    require_headings(
        text,
        (
            "Context Refresh",
            "Problem Boundary",
            "Comparison",
            "File Plan",
            "Ordered Steps",
            "Verification Plan",
            "Alignment",
            "Provisional Interview Outline",
        ),
        result,
    )
    solution_count = len(
        re.findall(r"(?m)^##\s+Solution\s+[12]:\s+\S", text)
    )
    optional_third = re.search(r"(?ms)^## Solution 3.*?(?=^## |\Z)", text)
    if optional_third and "{{OPTIONAL:" not in optional_third.group(0):
        solution_count += 1
    if solution_count not in {2, 3}:
        result.errors.append(
            f"expected 2-3 completed solutions, found {solution_count}"
        )
    for dimension in (
        "Implementation complexity",
        "Intrusion",
        "Extensibility",
        "PR acceptance difficulty",
        "Interview value",
    ):
        if dimension not in text:
            result.errors.append(f"comparison matrix missing: {dimension}")
    boundary = section(text, "Problem Boundary")
    non_goal_block = re.search(
        r"(?ms)^\*\*Out of scope:\*\*\s*(.*?)^\*\*Success criteria:\*\*",
        boundary,
    )
    non_goals = (
        re.findall(r"(?m)^-\s+(?!\s*$).+", non_goal_block.group(1))
        if non_goal_block
        else []
    )
    if len(non_goals) < 2:
        result.errors.append("problem boundary needs at least two explicit non-goals")

    if comment:
        comment_result = validate_comment(comment)
        result.errors.extend(f"maintainer comment: {e}" for e in comment_result.errors)
        result.warnings.extend(f"maintainer comment: {w}" for w in comment_result.warnings)
    else:
        result.warnings.append("maintainer comment was not supplied for word-count validation")
    return result


def validate_comment(path: Path) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    words = english_word_count(text)
    if words > 150:
        result.errors.append(f"maintainer comment has {words} English words; maximum is 150")
    if words < 15:
        result.warnings.append(f"maintainer comment is unusually short ({words} words)")
    if not re.search(r"(?i)would|interested|accept|plan|align", text):
        result.errors.append("maintainer comment does not ask for acceptance/alignment")
    return result


def validate_implementation(path: Path) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    require_headings(
        text,
        (
            "Readiness",
            "Interface Checkpoint",
            "File Changes",
            "Integration",
            "Verification",
            "Demo",
            "Diff and Risk Review",
            "Commit Plan",
        ),
        result,
    )
    for behavior in (
        "Happy path",
        "Empty input",
        "Long input",
        "Tool failure",
        "Legacy compatibility",
    ):
        if behavior not in text:
            result.errors.append(f"verification matrix missing: {behavior}")
    if not re.search(r"(?i)baseline", text):
        result.errors.append("baseline evidence is missing")
    return result


def validate_pr(path: Path) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    require_headings(
        text,
        (
            "Problem",
            "Solution",
            "Changes",
            "Testing",
            "Notes for Reviewer",
            "Backward Compatibility",
            "Screenshots / Demo",
            "Checklist",
        ),
        result,
    )
    checked = len(re.findall(r"(?mi)^- \[x\]", text))
    unchecked = len(re.findall(r"(?m)^- \[ \]", text))
    if unchecked:
        result.errors.append(
            f"{unchecked} checklist item(s) remain unchecked; verify them or replace "
            "inapplicable items with an explicit N/A explanation"
        )
    checklist = section(text.replace("### ", "## "), "Checklist")
    if not checked and not re.search(r"(?i)\bN/?A\b|not applicable", checklist):
        result.errors.append("PR checklist has no verified item or explicit N/A")
    return result


def validate_interview(path: Path) -> Result:
    result = Result(str(path))
    text = read_text(path, result)
    if not text:
        return result
    check_placeholders(text, result)
    require_headings(
        text,
        (
            "Evidence Status",
            "Context",
            "Contribution",
            "Process",
            "Result",
            "Challenges",
            "Reflection",
            "Demonstrated Capabilities",
        ),
        result,
    )
    if re.search(r"(?i)\bmerged\b", text) and not re.search(
        r"https://github\.com/[^\s)]+/pull/\d+", text
    ):
        result.errors.append("a merged claim requires a GitHub PR URL")
    if re.search(r"\b\d+(?:\.\d+)?%", text) and not re.search(
        r"(?i)source|command|baseline|measured|benchmark|coverage", text
    ):
        result.errors.append("percentage metrics require a reproducible source/baseline")
    return result


VALIDATORS: dict[str, Callable[[Path], Result]] = {
    "analysis": validate_analysis,
    "implementation": validate_implementation,
    "pr": validate_pr,
    "interview": validate_interview,
    "comment": validate_comment,
}


def emit(results: list[Result]) -> int:
    payload = {
        "valid": all(result.valid for result in results),
        "results": [
            {
                "artifact": result.artifact,
                "valid": result.valid,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["valid"] else 2


def run(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    if args.kind == "analysis":
        repo = Path(args.repo).resolve() if args.repo else None
        return emit([validate_analysis(path, repo)])
    if args.kind == "design":
        comment = Path(args.comment).resolve() if args.comment else None
        return emit([validate_design(path, comment)])
    return emit([VALIDATORS[args.kind](path)])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate evidence structure without changing source artifacts."
    )
    subparsers = parser.add_subparsers(dest="kind", required=True)
    for kind in ("analysis", "implementation", "pr", "interview", "comment"):
        sub = subparsers.add_parser(kind)
        sub.add_argument("path")
        if kind == "analysis":
            sub.add_argument("--repo", help="verify referenced relative paths")
        sub.set_defaults(func=run)
    design = subparsers.add_parser("design")
    design.add_argument("path")
    design.add_argument("--comment", help="validate the maintainer comment and 150-word limit")
    design.set_defaults(func=run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
