from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_evidence


def valid_analysis() -> str:
    tick = chr(96)
    sections = [
        "# Contribution Analysis",
        "## Evidence Scope",
        "- Repository/commit: owner/repo@abc",
        "- Collected at (UTC): 2026-08-14T00:00:00Z",
        "## Repository Tree (Depth 3)",
        "src/core.py",
        "## Agent Core",
        f"- Agent loop: {tick}src/core.py:run{tick}",
        "## Issue Candidates",
        "None found after applying all filters.",
        "## Rejected Issues",
        "None.",
    ]
    for dimension in validate_evidence.ARCHITECTURE_DIMENSIONS:
        sections.extend(
            [
                f"## {dimension}",
                f"**Current state:** {tick}src/core.py:run{tick} is the inspected call chain.",
                "**Gap:** No gap found in the inspected scope.",
                "**Impact:** low",
                "**Improvement:** Keep current behavior.",
                "**Change scope:** 0 files, high confidence.",
                "**Interview angle:** Evidence-based architecture analysis.",
            ]
        )
    sections.extend(
        [
            "## Ranked Contribution Directions",
            "### Rank 1",
            "- One sentence: No viable direction was found.",
        ]
    )
    return "\n\n".join(sections) + "\n"


def valid_interview(extra: str = "") -> str:
    headings = (
        "Evidence Status",
        "Context",
        "Contribution",
        "Process",
        "Result",
        "Challenges",
        "Reflection",
        "Demonstrated Capabilities",
    )
    text = "# Interview Narrative\n\n" + "\n\n".join(
        f"## {heading}\n\nVerified content." for heading in headings
    )
    return text + "\n" + extra


def valid_design() -> str:
    return """# Solution Design

## Context Refresh

Repository and files were refreshed.

## Problem Boundary

**Core problem:** The router mishandles empty tool results.
**Out of scope:**
- Redesigning the Agent loop.
- Adding a new dependency.
**Success criteria:**
- Existing calls remain compatible.
- Empty results are handled deterministically.
**Constraints:** Python 3.11 and a small compatible change.

## Solution 1: Guard at the router

**Approach:** Add a focused guard.
**Abstractions:** Existing function only.
**Data flow:** result -> guard -> normalized result.
**Integration points:** src/router.py.
**Key signature/pseudocode:** normalize(result).
**Advantages:** Small and compatible.
**Risks:** Router-specific behavior.
**Fit:** Narrow bug fix.

## Solution 2: Normalize in the tool adapter

**Approach:** Normalize each tool response.
**Abstractions:** Adapter helper.
**Data flow:** tool -> adapter -> router.
**Integration points:** src/tools.py.
**Key signature/pseudocode:** adapt(result).
**Advantages:** Central tool contract.
**Risks:** Wider integration surface.
**Fit:** Multiple tool backends.

## Solution 3 (optional)

{{OPTIONAL:unused}}

## Comparison

| Dimension | Solution 1 | Solution 2 | Solution 3 |
|---|---|---|---|
| Implementation complexity | low | medium | |
| Intrusion | low | medium | |
| Extensibility | medium | high | |
| PR acceptance difficulty | low | medium | |
| Interview value | medium | high | |

**Recommendation and rationale:** Solution 1 matches the scoped Issue.

## File Plan

Modify src/router.py and its test.

## Ordered Steps

1. Add a failing test.
2. Add the guard.
3. Run compatibility tests.

## Verification Plan

Run unit tests, an empty-result case, and a legacy call.

## Alignment

The open bug Issue waives a separate core-feature discussion.

## Provisional Interview Outline

Explain the compatibility decision; results remain pending.
"""


def valid_implementation() -> str:
    headings = (
        "Readiness",
        "Interface Checkpoint",
        "File Changes",
        "Integration",
        "Verification",
        "Demo",
        "Diff and Risk Review",
        "Commit Plan",
    )
    text = "# Implementation Report\n\n" + "\n\n".join(
        f"## {heading}\n\nBaseline and verified evidence." for heading in headings
    )
    return text + "\nHappy path\nEmpty input\nLong input\nTool failure\nLegacy compatibility\n"


def valid_pr() -> str:
    headings = (
        "Problem",
        "Solution",
        "Changes",
        "Testing",
        "Notes for Reviewer",
        "Backward Compatibility",
        "Screenshots / Demo",
        "Checklist",
    )
    return "# PR\n\n" + "\n\n".join(
        f"### {heading}\n\nVerified content." for heading in headings
    ) + "\n\n- [x] Verified applicable checks.\n"


class EvidenceValidatorTests(unittest.TestCase):
    def test_analysis_requires_all_dimensions_and_real_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "src").mkdir()
            (repo / "src" / "core.py").write_text("def run():\n    pass\n", encoding="utf-8")
            report = repo / "analysis.md"
            report.write_text(valid_analysis(), encoding="utf-8")
            result = validate_evidence.validate_analysis(report, repo)
            self.assertTrue(result.valid, result.errors)

            report.write_text(
                valid_analysis().replace("## Evaluation", "## Missing Evaluation", 1),
                encoding="utf-8",
            )
            result = validate_evidence.validate_analysis(report, repo)
            self.assertFalse(result.valid)
            self.assertTrue(any("Evaluation" in error for error in result.errors))

    def test_analysis_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "src").mkdir()
            (repo / "src" / "core.py").write_text("def run():\n    pass\n", encoding="utf-8")
            report = repo / "analysis.md"
            report.write_text(
                valid_analysis().replace("src/core.py:run", "../outside.py:run"),
                encoding="utf-8",
            )
            result = validate_evidence.validate_analysis(report, repo)
            self.assertFalse(result.valid)
            self.assertTrue(any("escapes repository" in error for error in result.errors))

    def test_analysis_rejects_missing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "src").mkdir()
            (repo / "src" / "core.py").write_text("def other():\n    pass\n", encoding="utf-8")
            report = repo / "analysis.md"
            report.write_text(valid_analysis(), encoding="utf-8")
            result = validate_evidence.validate_analysis(report, repo)
            self.assertFalse(result.valid)
            self.assertTrue(any("symbol 'run'" in error for error in result.errors))

    def test_comment_word_limit_and_alignment_question(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "comment.txt"
            path.write_text(
                "Hi maintainers, I found a reproducible failure in the tool router. "
                "I propose a backward-compatible guard and focused tests. "
                "Would you be interested in accepting this direction? Thanks!",
                encoding="utf-8",
            )
            self.assertTrue(validate_evidence.validate_comment(path).valid)
            path.write_text("Would you accept " + "word " * 151, encoding="utf-8")
            result = validate_evidence.validate_comment(path)
            self.assertFalse(result.valid)
            self.assertTrue(any("maximum is 150" in error for error in result.errors))

    def test_design_implementation_and_pr_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            design = root / "design.md"
            comment = root / "comment.txt"
            implementation = root / "implementation.md"
            pr = root / "pr.md"
            design.write_text(valid_design(), encoding="utf-8")
            comment.write_text(
                "Hi maintainers, I found a reproducible empty-result failure. "
                "I propose a backward-compatible guard and focused tests. "
                "Would you be interested in accepting this direction? Thanks!",
                encoding="utf-8",
            )
            implementation.write_text(valid_implementation(), encoding="utf-8")
            pr.write_text(valid_pr(), encoding="utf-8")
            self.assertTrue(
                validate_evidence.validate_design(design, comment).valid,
                validate_evidence.validate_design(design, comment).errors,
            )
            self.assertTrue(validate_evidence.validate_implementation(implementation).valid)
            self.assertTrue(validate_evidence.validate_pr(pr).valid)

            design.write_text(
                valid_design().replace(
                    "- Redesigning the Agent loop.\n- Adding a new dependency.\n",
                    "",
                ),
                encoding="utf-8",
            )
            self.assertFalse(validate_evidence.validate_design(design, comment).valid)

            pr.write_text(valid_pr().replace("[x]", "[ ]"), encoding="utf-8")
            self.assertFalse(validate_evidence.validate_pr(pr).valid)

    def test_interview_rejects_unlinked_merged_claim(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "story.md"
            path.write_text(valid_interview("The PR was merged.\n"), encoding="utf-8")
            result = validate_evidence.validate_interview(path)
            self.assertFalse(result.valid)
            self.assertTrue(any("GitHub PR URL" in error for error in result.errors))

    def test_interview_allows_truthful_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "story.md"
            path.write_text(
                valid_interview("The PR is pending and no metric was measured.\n"),
                encoding="utf-8",
            )
            result = validate_evidence.validate_interview(path)
            self.assertTrue(result.valid, result.errors)


if __name__ == "__main__":
    unittest.main()
