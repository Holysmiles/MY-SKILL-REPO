from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import repo_inventory  # noqa: E402


class RepositoryInventoryTests(unittest.TestCase):
    def test_windows_reparse_points_are_treated_as_links(self) -> None:
        fake_entry = mock.Mock()
        fake_entry.is_symlink.return_value = False
        fake_entry.path = "not-a-mount"
        fake_entry.stat.return_value = SimpleNamespace(st_file_attributes=0x400)
        with (
            mock.patch.object(repo_inventory.os.path, "ismount", return_value=False),
            mock.patch.object(repo_inventory.stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400, create=True),
        ):
            self.assertTrue(repo_inventory._is_link_like(fake_entry))

    def test_detects_expected_files_and_skips_unsafe_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_main.py").write_text("pass\n", encoding="utf-8")
            (root / "README.md").write_text("readme\n", encoding="utf-8")
            (root / "CONTRIBUTING.md").write_text("rules\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
            (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=do-not-report\n", encoding="utf-8")
            (root / "archive.zip").write_bytes(b"not really a zip")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "index.js").write_text("secret\n", encoding="utf-8")
            (root / "build").mkdir()
            (root / "build" / "main.py").write_text("generated\n", encoding="utf-8")

            with mock.patch("builtins.open", side_effect=AssertionError("inventory opened a file")):
                result = repo_inventory.inventory_repository(root, max_depth=3)

            paths = {entry["path"] for entry in result["entries"]}
            self.assertIn("src/main.py", paths)
            self.assertIn("docs/guide.md", paths)
            self.assertNotIn(".env", paths)
            self.assertNotIn("archive.zip", paths)
            self.assertFalse(any(path.startswith("node_modules") for path in paths))
            self.assertFalse(any(path.startswith("build") for path in paths))
            self.assertTrue(all("\\" not in path for path in paths))

            detected = result["detected"]
            self.assertEqual(detected["entry_points"], ["src/main.py"])
            self.assertIn("README.md", detected["documentation"])
            self.assertIn("CONTRIBUTING.md", detected["documentation"])
            self.assertEqual(detected["style_configs"], ["pyproject.toml"])
            self.assertEqual(detected["test_configs"], ["pytest.ini"])
            self.assertEqual(detected["test_roots"], ["tests"])
            self.assertEqual(detected["core_directories"], ["src"])
            self.assertEqual(result["summary"]["skipped_by_reason"]["secret-file"], 1)
            self.assertEqual(result["summary"]["skipped_by_reason"]["binary-file"], 1)

    def test_depth_and_entry_limits_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a" / "b").mkdir(parents=True)
            (root / "a" / "b" / "too_deep.py").write_text("pass\n", encoding="utf-8")
            (root / "top.py").write_text("pass\n", encoding="utf-8")

            depth_limited = repo_inventory.inventory_repository(root, max_depth=2)
            paths = {entry["path"] for entry in depth_limited["entries"]}
            self.assertEqual(paths, {"a", "a/b", "top.py"})
            self.assertGreaterEqual(depth_limited["summary"]["depth_limited_directories"], 1)

            entry_limited = repo_inventory.inventory_repository(root, max_depth=3, max_entries=1)
            self.assertTrue(entry_limited["summary"]["truncated"])
            self.assertEqual(entry_limited["summary"]["encountered"], 1)
            self.assertEqual(len(entry_limited["entries"]), 1)

    def test_nested_repository_is_listed_but_not_traversed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "packages" / "external-agent"
            nested.mkdir(parents=True)
            (nested / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
            (nested / "main.py").write_text("do not inventory\n", encoding="utf-8")

            result = repo_inventory.inventory_repository(root, max_depth=3)

            paths = {entry["path"] for entry in result["entries"]}
            self.assertIn("packages/external-agent", paths)
            self.assertNotIn("packages/external-agent/main.py", paths)
            self.assertEqual(result["detected"]["nested_repositories"], ["packages/external-agent"])
            self.assertEqual(result["summary"]["skipped_by_reason"]["nested-repository"], 1)

    def test_symlinks_are_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(temporary)
            root = outer / "repo"
            external = outer / "external"
            root.mkdir()
            external.mkdir()
            (external / "main.py").write_text("should not appear\n", encoding="utf-8")
            try:
                (root / "linked").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            result = repo_inventory.inventory_repository(root)
            self.assertEqual(result["entries"], [])
            self.assertEqual(result["summary"]["skipped_by_reason"]["symlink"], 1)

    def test_json_cli_and_invalid_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "repo_inventory.py"), temporary, "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["ok"])

            missing = subprocess.run(
                [sys.executable, str(SCRIPTS / "repo_inventory.py"), str(Path(temporary) / "missing"), "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(missing.returncode, 2)
            self.assertFalse(json.loads(missing.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
