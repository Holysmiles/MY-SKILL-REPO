from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import git_preflight  # noqa: E402


def run_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(arguments)} failed: {completed.stderr}")
    return completed.stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitPreflightTests(unittest.TestCase):
    def make_repository(self, root: Path, name: str = "repository") -> Path:
        repository = root / name
        repository.mkdir()
        run_git(repository, "init")
        run_git(repository, "symbolic-ref", "HEAD", "refs/heads/main")
        run_git(repository, "config", "user.name", "Preflight Test")
        run_git(repository, "config", "user.email", "preflight@example.invalid")

        (repository / "tracked.txt").write_text("initial\n", encoding="utf-8")
        (repository / "CONTRIBUTING.md").write_text("rules\n", encoding="utf-8")
        (repository / "SECURITY.md").write_text("policy\n", encoding="utf-8")
        templates = repository / ".github" / "PULL_REQUEST_TEMPLATE"
        templates.mkdir(parents=True)
        (templates / "bug.md").write_text("template\n", encoding="utf-8")
        run_git(repository, "add", ".")
        run_git(repository, "commit", "-m", "initial")

        secret_url = "https://contributor:password@example.invalid/project.git?token=query-secret"
        run_git(repository, "remote", "add", "origin", secret_url)
        head = run_git(repository, "rev-parse", "HEAD")
        run_git(repository, "update-ref", "refs/remotes/origin/main", head)
        run_git(repository, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        run_git(repository, "config", "branch.main.remote", "origin")
        run_git(repository, "config", "branch.main.merge", "refs/heads/main")
        return repository

    def test_collects_git_state_policies_and_does_not_write_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repository / "staged.txt").write_text("staged\n", encoding="utf-8")
            run_git(repository, "add", "staged.txt")
            (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")

            index_path = Path(run_git(repository, "rev-parse", "--git-path", "index"))
            if not index_path.is_absolute():
                index_path = repository / index_path
            index_before = index_path.read_bytes()
            head_before = run_git(repository, "rev-parse", "HEAD")

            with mock.patch.dict("os.environ", {"GIT_DIR": str(repository / "does-not-exist")}, clear=False):
                result = git_preflight.collect_preflight(repository)

            self.assertEqual(index_path.read_bytes(), index_before)
            self.assertEqual(run_git(repository, "rev-parse", "HEAD"), head_before)
            self.assertEqual(Path(result["repository_root"]), repository.resolve())
            self.assertEqual(result["head"]["branch"], "main")
            self.assertFalse(result["head"]["detached"])
            self.assertEqual(result["default_branch"]["ref"], "origin/main")
            self.assertEqual(result["default_branch"]["source"], "remote-head")
            self.assertEqual(result["upstream"]["ref"], "origin/main")
            self.assertEqual(result["upstream"]["ahead"], 0)
            self.assertEqual(result["upstream"]["behind"], 0)
            self.assertEqual(result["base"]["commit"], head_before)

            working = result["working_tree"]
            self.assertTrue(working["dirty"])
            self.assertGreaterEqual(working["staged"], 1)
            self.assertGreaterEqual(working["unstaged"], 1)
            self.assertEqual(working["untracked"], 1)
            self.assertIn("CONTRIBUTING.md", result["policies"]["contributing"])
            self.assertIn("SECURITY.md", result["policies"]["security"])
            self.assertIn(
                ".github/PULL_REQUEST_TEMPLATE/bug.md",
                result["policies"]["pull_request_templates"],
            )
            remote_text = json.dumps(result["remotes"])
            self.assertNotIn("password", remote_text)
            self.assertNotIn("query-secret", remote_text)
            self.assertIn("***", remote_text)

    def test_detached_head_and_local_default_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            run_git(repository, "remote", "remove", "origin")
            run_git(repository, "checkout", "--detach")

            result = git_preflight.collect_preflight(repository)

            self.assertTrue(result["head"]["detached"])
            self.assertIsNone(result["head"]["branch"])
            self.assertEqual(result["default_branch"]["ref"], "main")
            self.assertIsNone(result["upstream"])
            self.assertIsNotNone(result["base"])

    def test_upstream_remote_is_preferred_for_fork_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary), "repo with 空格")
            run_git(repository, "remote", "add", "upstream", "git@github.com:canonical/project.git")
            head = run_git(repository, "rev-parse", "HEAD")
            run_git(repository, "update-ref", "refs/remotes/upstream/main", head)
            run_git(repository, "symbolic-ref", "refs/remotes/upstream/HEAD", "refs/remotes/upstream/main")

            result = git_preflight.collect_preflight(repository)

            self.assertEqual(Path(result["repository_root"]), repository.resolve())
            self.assertEqual(result["default_branch"]["remote"], "upstream")
            self.assertEqual(result["default_branch"]["ref"], "upstream/main")
            self.assertEqual(result["upstream"]["ref"], "origin/main")
            self.assertEqual(result["base"]["commit"], head)

    def test_unborn_repository_reports_current_default_without_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "empty"
            repository.mkdir()
            run_git(repository, "init")
            run_git(repository, "symbolic-ref", "HEAD", "refs/heads/main")

            result = git_preflight.collect_preflight(repository)

            self.assertEqual(result["head"], {"commit": None, "branch": "main", "detached": False})
            self.assertEqual(result["default_branch"]["source"], "unborn-current-branch")
            self.assertIsNone(result["base"])

    def test_status_parser_handles_rename_and_untracked_paths(self) -> None:
        entries = git_preflight._parse_status(b"R  renamed file.py\0old file.py\0?? odd name.txt\0")
        self.assertEqual(
            entries,
            [
                {"code": "R ", "path": "renamed file.py", "original_path": "old file.py"},
                {"code": "??", "path": "odd name.txt", "original_path": None},
            ],
        )

    def test_remote_url_redaction_covers_http_and_scp_forms(self) -> None:
        http_url = (
            "https://oauth:top-secret@example.invalid/repo.git?access_token=also-secret&view=1"
            "#X-Amz-Signature=fragment-secret"
        )
        redacted_http = git_preflight._redact_remote_url(http_url)
        self.assertNotIn("top-secret", redacted_http)
        self.assertNotIn("also-secret", redacted_http)
        self.assertNotIn("fragment-secret", redacted_http)
        self.assertIn("view=1", redacted_http)
        self.assertEqual(
            git_preflight._redact_remote_url("oauth2:private@gitlab.example:group/repo.git"),
            "***:***@gitlab.example:group/repo.git",
        )
        self.assertEqual(
            git_preflight._redact_remote_url("git@github.com:owner/repo.git"),
            "git@github.com:owner/repo.git",
        )

    def test_repository_local_git_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            fake_git = repository / "git.exe"
            fake_git.write_bytes(b"not an executable")

            with mock.patch.dict(
                "os.environ", {"GIT_EXECUTABLE": str(fake_git)}, clear=False
            ):
                with self.assertRaises(git_preflight.PreflightError) as caught:
                    git_preflight.collect_preflight(repository)
            self.assertIn("inside the inspected repository", str(caught.exception))

    def test_json_cli_and_non_repository_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_repository(root)
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "git_preflight.py"), str(repository), "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["ok"])

            non_repository = root / "not-a-repository"
            non_repository.mkdir()
            failed = subprocess.run(
                [sys.executable, str(SCRIPTS / "git_preflight.py"), str(non_repository), "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertFalse(json.loads(failed.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
