from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillStructureTests(unittest.TestCase):
    def test_skill_frontmatter_links_and_size(self) -> None:
        path = ROOT / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 500)
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        self.assertIsNotNone(match)
        keys = {
            line.split(":", 1)[0].strip()
            for line in match.group(1).splitlines()
            if ":" in line
        }
        self.assertEqual(keys, {"name", "description"})

        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        self.assertTrue(links)
        for relative in links:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_all_workflow_gates_and_labels_are_present(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for gate in range(11):
            self.assertIn(f"## Gate {gate}:", text)
        for label in (
            "good first issue",
            "help wanted",
            "bug",
            "documentation",
            "enhancement",
        ):
            self.assertIn(label, text)
        for dimension in (
            "task planning",
            "multi-Agent collaboration",
            "context management",
            "human-in-the-loop",
            "evaluation",
            "tool retrieval/routing",
            "streaming/intermediate-state visibility",
        ):
            self.assertIn(dimension, text)

    def test_scripts_templates_and_metadata_exist(self) -> None:
        for name in (
            "github_snapshot.py",
            "repo_inventory.py",
            "git_preflight.py",
            "contribution_state.py",
            "validate_evidence.py",
        ):
            self.assertTrue((ROOT / "scripts" / name).is_file(), name)
        for name in (
            "contribution-state.json",
            "project-shortlist.md",
            "contribution-analysis.md",
            "solution-design.md",
            "maintainer-comment.txt",
            "implementation-report.md",
            "pr-body.md",
            "follow-up-comment.txt",
            "review-log.md",
            "interview-story.md",
            "action-checklists.md",
        ):
            self.assertTrue((ROOT / "assets" / "templates" / name).is_file(), name)
        json.loads(
            (ROOT / "assets" / "templates" / "contribution-state.json").read_text(
                encoding="utf-8"
            )
        )

        metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$contribute-agent-oss", metadata)
        short = re.search(r'short_description:\s*"([^"]+)"', metadata)
        self.assertIsNotNone(short)
        self.assertGreaterEqual(len(short.group(1)), 25)
        self.assertLessEqual(len(short.group(1)), 64)


if __name__ == "__main__":
    unittest.main()
