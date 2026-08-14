from __future__ import annotations

import argparse
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contribution_state


class ContributionStateTests(unittest.TestCase):
    def init_args(self, workspace: Path) -> argparse.Namespace:
        return argparse.Namespace(
            workspace=str(workspace),
            objective="Test a contribution",
            repo="owner/repo",
            local_path=None,
            tech_stack=["Python"],
            timebox_days=14,
        )

    def test_init_refuses_non_empty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw) / "session"
            workspace.mkdir()
            marker = workspace / "user-file.txt"
            marker.write_text("preserve me\n", encoding="utf-8")

            with self.assertRaises(contribution_state.StateError):
                contribution_state.init_workspace(self.init_args(workspace))
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")

    def test_workspace_cannot_be_equal_to_or_inside_target_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repository = Path(raw) / "repository"
            repository.mkdir()
            for workspace in (repository, repository / "contribution-session"):
                with self.subTest(workspace=workspace):
                    args = self.init_args(workspace)
                    args.local_path = str(repository)
                    with self.assertRaises(contribution_state.StateError):
                        contribution_state.init_workspace(args)

    def test_setting_target_local_path_enforces_workspace_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "session"
            contribution_state.init_workspace(self.init_args(workspace))

            with self.assertRaises(contribution_state.StateError):
                contribution_state.set_field(
                    argparse.Namespace(
                        workspace=str(workspace),
                        field="target.local_path",
                        value=str(root),
                    )
                )
            self.assertIsNone(
                contribution_state.load_state(workspace)["target"]["local_path"]
            )

    def test_write_state_refuses_state_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw) / "session"
            contribution_state.init_workspace(self.init_args(workspace))
            state = contribution_state.load_state(workspace)

            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(contribution_state.StateError):
                    contribution_state.write_state(workspace, state)

    def test_state_machine_blocks_skips_and_unfilled_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw) / "session"
            self.assertEqual(contribution_state.init_workspace(self.init_args(workspace)), 0)

            with self.assertRaises(contribution_state.StateError):
                contribution_state.advance(
                    argparse.Namespace(workspace=str(workspace), to="analysis")
                )

            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="discovery")
            )
            with self.assertRaises(contribution_state.StateError):
                contribution_state.advance(
                    argparse.Namespace(workspace=str(workspace), to="analysis")
                )

            state = contribution_state.load_state(workspace)
            shortlist = Path(state["artifacts"]["project_shortlist"])
            shortlist.write_text("# Filled shortlist\n", encoding="utf-8")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="analysis")
            )
            with self.assertRaises(contribution_state.StateError):
                contribution_state.advance(
                    argparse.Namespace(workspace=str(workspace), to="selection")
                )

    def test_unknown_state_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw) / "session"
            contribution_state.init_workspace(self.init_args(workspace))
            with self.assertRaises(contribution_state.StateError):
                contribution_state.set_field(
                    argparse.Namespace(
                        workspace=str(workspace),
                        field="target.not_a_field",
                        value="x",
                    )
                )

    def test_external_action_record_does_not_advance_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw) / "session"
            contribution_state.init_workspace(self.init_args(workspace))
            contribution_state.record_action(
                argparse.Namespace(
                    workspace=str(workspace),
                    kind="push",
                    target="owner/repo:feature",
                    authorization="user message 42",
                    status="authorized",
                    url=None,
                    detail="record only",
                )
            )
            state = contribution_state.load_state(workspace)
            self.assertEqual(state["external_actions"][0]["status"], "authorized")
            self.assertEqual(state["phase"], "intake")

    def test_follow_up_window_respects_activity_and_repeat_guard(self) -> None:
        state = contribution_state.template_state()
        state["pull_request"].update(
            {
                "state": "open",
                "created_at": "2026-08-01T00:00:00Z",
                "last_human_activity_at": "2026-08-07T00:00:00Z",
            }
        )
        before = contribution_state.follow_up_status(
            state,
            datetime(2026, 8, 13, tzinfo=timezone.utc),
            7,
            14,
        )
        self.assertFalse(before["eligible"])
        boundary = contribution_state.follow_up_status(
            state,
            datetime(2026, 8, 14, tzinfo=timezone.utc),
            7,
            14,
        )
        self.assertTrue(boundary["eligible"])

        state["pull_request"]["last_follow_up_at"] = "2026-08-14T00:00:00Z"
        repeated = contribution_state.follow_up_status(
            state,
            datetime(2026, 8, 20, tzinfo=timezone.utc),
            7,
            14,
        )
        self.assertFalse(repeated["eligible"])
        self.assertIn("already occurred", repeated["reason"])

        state["pull_request"]["state"] = "merged"
        merged = contribution_state.follow_up_status(
            state,
            datetime(2026, 8, 20, tzinfo=timezone.utc),
            7,
            14,
        )
        self.assertEqual(merged["decision"], "not-applicable")

    def test_complete_state_path_accepts_filled_bundled_templates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repository = root / "repo"
            workspace = root / "session"
            (repository / "src").mkdir(parents=True)
            (repository / "src" / "core.py").write_text(
                "def run():\n    return 'ok'\n",
                encoding="utf-8",
            )
            args = self.init_args(workspace)
            args.local_path = str(repository)
            contribution_state.init_workspace(args)

            state = contribution_state.load_state(workspace)

            def fill(key: str) -> Path:
                path = Path(state["artifacts"][key])
                text = path.read_text(encoding="utf-8")
                text = re.sub(r"\{\{REQUIRED:[^}]+\}\}", "verified value", text)
                path.write_text(text, encoding="utf-8")
                return path

            fill("project_shortlist")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="discovery")
            )
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="analysis")
            )

            analysis = fill("contribution_analysis")
            analysis_text = analysis.read_text(encoding="utf-8")
            analysis_text = re.sub(
                r"(?m)^\*\*Current state:\*\*.*$",
                "**Current state:** " + chr(96) + "src/core.py:run" + chr(96),
                analysis_text,
            )
            analysis_text = re.sub(
                r"(?m)^\*\*Impact:\*\*.*$",
                "**Impact:** low",
                analysis_text,
            )
            analysis.write_text(analysis_text, encoding="utf-8")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="selection")
            )

            state = contribution_state.load_state(workspace)
            state["target"]["direction"] = "Handle empty tool results"
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="design")
            )

            fill("solution_design")
            fill("maintainer_comment")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="alignment")
            )

            state = contribution_state.load_state(workspace)
            state["alignment"].update(
                {"status": "waived", "reason": "Narrow invited bug fix"}
            )
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="readiness")
            )

            state = contribution_state.load_state(workspace)
            evidence = str(Path(state["artifacts"]["implementation_report"]))
            state["baseline"].update(
                {
                    "commit": "abc123",
                    "command": "python -m unittest",
                    "exit_code": 0,
                    "result": "passed",
                    "evidence_path": evidence,
                }
            )
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="interface")
            )

            state = contribution_state.load_state(workspace)
            state["interface_checkpoint"].update(
                {
                    "status": "unchanged",
                    "reason": "Private implementation only",
                    "evidence_path": evidence,
                }
            )
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="implementation")
            )

            fill("implementation_report")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="verification")
            )

            state = contribution_state.load_state(workspace)
            state["verification"].update(
                {
                    "status": "passed",
                    "commands": [{"command": "python -m unittest", "exit_code": 0}],
                    "evidence_path": evidence,
                }
            )
            pr_body = fill("pr_body")
            pr_body.write_text(
                pr_body.read_text(encoding="utf-8").replace("- [ ]", "- [x]"),
                encoding="utf-8",
            )
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="pr")
            )
            self.assertEqual(
                contribution_state.load_state(workspace)["completion_state"],
                "pr-ready",
            )

            state = contribution_state.load_state(workspace)
            state["pull_request"].update(
                {
                    "url": "https://github.com/o/r/pull/1",
                    "state": "open",
                    "created_at": "2026-08-14T00:00:00Z",
                }
            )
            contribution_state.write_state(workspace, state)
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="review")
            )

            fill("review_log")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="narrative")
            )
            fill("interview_story")
            contribution_state.advance(
                argparse.Namespace(workspace=str(workspace), to="complete")
            )
            final_state = contribution_state.load_state(workspace)
            self.assertEqual(final_state["phase"], "complete")
            self.assertEqual(final_state["completion_state"], "narrative-complete")


if __name__ == "__main__":
    unittest.main()
