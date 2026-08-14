from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_snapshot


class PaginationClient(github_snapshot.GitHubClient):
    def __init__(self) -> None:
        super().__init__(token=None, api_url="https://invalid.example")
        self.pages: list[int] = []

    def get(self, path: str, params: dict | None = None) -> github_snapshot.Response:
        assert params is not None
        page = int(params["page"])
        per_page = int(params["per_page"])
        self.pages.append(page)
        start = (page - 1) * 100
        data = [{"id": index} for index in range(start, start + per_page)]
        return github_snapshot.Response({"items": data}, {})


class IssueClient:
    def __init__(self, issues: list[dict], comments: dict[int, list[dict]]) -> None:
        self.issues = issues
        self.comments = comments

    def get_all(
        self,
        path: str,
        params: dict | None = None,
        limit: int = 100,
        item_key: str | None = None,
    ) -> list[dict]:
        if path.endswith("/issues"):
            return self.issues[:limit]
        number = int(path.split("/")[-2])
        return self.comments.get(number, [])[:limit]


class CountClient:
    def __init__(self, open_count: int, closed_count: int) -> None:
        self.values = {"open": open_count, "closed": closed_count}

    def get(self, path: str, params: dict | None = None) -> github_snapshot.Response:
        assert params is not None
        state = "open" if "state:open" in params["q"] else "closed"
        return github_snapshot.Response({"total_count": self.values[state]}, {})


class GitHubSnapshotTests(unittest.TestCase):
    def test_calendar_month_subtraction_handles_month_end(self) -> None:
        self.assertEqual(
            github_snapshot.subtract_months(date(2026, 5, 31), 3),
            date(2026, 2, 28),
        )
        self.assertEqual(
            github_snapshot.subtract_months(date(2024, 5, 31), 3),
            date(2024, 2, 29),
        )

    def test_default_query_uses_injected_current_date(self) -> None:
        args = argparse.Namespace(query=None, topic="ai-agent", min_stars=1000, months=3)
        query = github_snapshot.build_search_query(args, date(2026, 8, 14))
        self.assertIn("pushed:>2026-05-14", query)
        self.assertNotIn("2026-04-01", query)

    def test_repository_parser_accepts_https_and_ssh(self) -> None:
        self.assertEqual(
            github_snapshot.parse_repo("https://github.com/owner/repo.git"),
            "owner/repo",
        )
        self.assertEqual(
            github_snapshot.parse_repo("git@github.com:owner/repo.git"),
            "owner/repo",
        )

    def test_pagination_reads_requested_limit(self) -> None:
        client = PaginationClient()
        items = client.get_all("/search/repositories", limit=150, item_key="items")
        self.assertEqual(len(items), 150)
        self.assertEqual(client.pages, [1, 2])

    def test_rate_limit_error_is_actionable_without_token_output(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.github.com/test",
            403,
            "forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "12345"},
            io.BytesIO(b'{"message":"API rate limit exceeded"}'),
        )
        client = github_snapshot.GitHubClient(token="super-secret")
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(github_snapshot.GitHubError) as caught:
                client.get("/test")
        message = str(caught.exception)
        self.assertIn("rate limit", message.lower())
        self.assertNotIn("super-secret", message)

    def test_token_environment_is_restricted_to_github_names(self) -> None:
        with self.assertRaises(github_snapshot.GitHubError):
            github_snapshot.token_from_environment("AWS_SECRET_ACCESS_KEY")
        with mock.patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "primary", "GH_TOKEN": "fallback"},
            clear=True,
        ):
            self.assertEqual(
                github_snapshot.token_from_environment("GH_TOKEN"),
                ("fallback", "GH_TOKEN"),
            )

    def test_token_api_host_requires_https_and_explicit_enterprise_trust(self) -> None:
        github_snapshot.GitHubClient(token="secret")
        with self.assertRaises(github_snapshot.GitHubError):
            github_snapshot.GitHubClient(
                token="secret", api_url="https://ghe.example.invalid/api/v3"
            )
        client = github_snapshot.GitHubClient(
            token="secret",
            api_url="https://ghe.example.invalid:8443/api/v3",
            allow_token_host="ghe.example.invalid:8443",
        )
        self.assertEqual(client.api_url, "https://ghe.example.invalid:8443/api/v3")
        with self.assertRaises(github_snapshot.GitHubError):
            github_snapshot.GitHubClient(
                token="secret",
                api_url="https://ghe.example.invalid:8443/api/v3",
                allow_token_host="ghe.example.invalid",
            )
        with self.assertRaises(github_snapshot.GitHubError):
            github_snapshot.GitHubClient(
                token="secret",
                api_url="http://api.github.com",
            )

    def test_api_url_rejects_credentials_query_and_fragment(self) -> None:
        invalid = (
            "https://user:password@api.github.com",
            "https://api.github.com?redirect=https://evil.invalid",
            "https://api.github.com#fragment",
        )
        for api_url in invalid:
            with self.subTest(api_url=api_url):
                with self.assertRaises(github_snapshot.GitHubError):
                    github_snapshot.GitHubClient(token=None, api_url=api_url)

    def test_token_is_never_sent_to_an_absolute_cross_origin_url(self) -> None:
        client = github_snapshot.GitHubClient(token="secret")
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(github_snapshot.GitHubError):
                client.get("https://evil.invalid/collect")
        urlopen.assert_not_called()

    def test_token_header_is_not_copied_to_redirects(self) -> None:
        client = github_snapshot.GitHubClient(token="secret")
        captured: list[object] = []

        def reject_network(request: object, timeout: float) -> None:
            captured.append(request)
            raise urllib.error.URLError("offline")

        with mock.patch("urllib.request.urlopen", side_effect=reject_network):
            with self.assertRaises(github_snapshot.GitHubError):
                client.get("/test")

        request = captured[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        redirected = urllib.request.HTTPRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://evil.invalid/collect",
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))

    def test_output_requires_force_and_refuses_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "snapshot.json"
            output.write_text("original\n", encoding="utf-8")
            with self.assertRaises(github_snapshot.GitHubError):
                github_snapshot.write_output({"value": 1}, str(output))
            self.assertEqual(output.read_text(encoding="utf-8"), "original\n")

            with mock.patch("builtins.print"):
                github_snapshot.write_output({"value": 2}, str(output), force=True)
            self.assertIn('"value": 2', output.read_text(encoding="utf-8"))

            symlink_output = Path(temporary) / "linked.json"
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(github_snapshot.GitHubError):
                    github_snapshot.write_output({"value": 3}, str(symlink_output))

    def test_zero_open_issues_has_no_ratio(self) -> None:
        counts = github_snapshot.issue_counts(CountClient(0, 20), "owner/repo")
        self.assertIsNone(counts["closed_open_ratio"])
        self.assertIn("N/A", counts["ratio_note"])

    def test_commit_recency_uses_thirty_day_window(self) -> None:
        recent = github_snapshot.annotate_commit_recency(
            {"committed_at": "2026-07-15T00:00:00Z"},
            date(2026, 8, 14),
        )
        self.assertTrue(recent["within_recent_window"])
        stale = github_snapshot.annotate_commit_recency(
            {"committed_at": "2026-07-14T00:00:00Z"},
            date(2026, 8, 14),
        )
        self.assertFalse(stale["within_recent_window"])

    def test_claim_classifier_ignores_bots_and_marks_negation_ambiguous(self) -> None:
        claimed = github_snapshot.classify_claim(
            {
                "body": "I'll take this and work on it.",
                "user": {"login": "alice", "type": "User"},
            }
        )
        self.assertEqual(claimed["status"], "claimed")
        ambiguous = github_snapshot.classify_claim(
            {
                "body": "I'll take this, but I am no longer working on it.",
                "user": {"login": "alice", "type": "User"},
            }
        )
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertIsNone(
            github_snapshot.classify_claim(
                {
                    "body": "I'll take this.",
                    "user": {"login": "ci-bot", "type": "Bot"},
                }
            )
        )

    def test_issue_prefilter_includes_sixtieth_day_boundary(self) -> None:
        issues = [
            {
                "number": 1,
                "title": "Boundary issue",
                "html_url": "https://github.com/o/r/issues/1",
                "state": "open",
                "created_at": "2026-05-01T00:00:00Z",
                "updated_at": "2026-06-15T00:00:00Z",
                "labels": [{"name": "documentation"}],
                "assignee": None,
                "assignees": [],
                "comments": 0,
                "body": "Expected behavior and reproduction are present.",
            },
            {
                "number": 2,
                "title": "Assigned",
                "state": "open",
                "updated_at": "2026-08-01T00:00:00Z",
                "labels": [{"name": "bug"}],
                "assignee": {"login": "alice"},
                "assignees": [{"login": "alice"}],
                "comments": 0,
            },
            {
                "number": 3,
                "title": "Claimed",
                "state": "open",
                "updated_at": "2026-08-01T00:00:00Z",
                "labels": [{"name": "help wanted"}],
                "assignee": None,
                "assignees": [],
                "comments": 1,
            },
            {
                "number": 4,
                "title": "Wrong label",
                "state": "open",
                "updated_at": "2026-08-01T00:00:00Z",
                "labels": [{"name": "question"}],
                "assignee": None,
                "assignees": [],
                "comments": 0,
            },
        ]
        comments = {
            3: [
                {
                    "body": "I'm working on this.",
                    "user": {"login": "bob", "type": "User"},
                    "created_at": "2026-08-02T00:00:00Z",
                }
            ]
        }
        result = github_snapshot.issue_candidates(
            IssueClient(issues, comments),
            "o/r",
            date(2026, 8, 14),
            60,
            {label.casefold() for label in github_snapshot.DEFAULT_LABELS},
            100,
        )
        self.assertEqual(
            [item["number"] for item in result["api_prefilter_candidates"]],
            [1],
        )
        rejected = {
            item["number"]: item["rejection_reasons"]
            for item in result["rejected_by_deterministic_prefilter"]
        }
        self.assertIn("assigned", rejected[2])
        self.assertIn("claim phrase detected", rejected[3])
        self.assertIn("no target label", rejected[4])


if __name__ == "__main__":
    unittest.main()
