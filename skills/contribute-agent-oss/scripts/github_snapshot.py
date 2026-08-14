#!/usr/bin/env python3
"""Collect read-only, timestamped GitHub evidence for contribution screening."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_LABELS = {
    "good first issue",
    "help wanted",
    "bug",
    "documentation",
    "enhancement",
}

ALLOWED_TOKEN_ENVS = ("GITHUB_TOKEN", "GH_TOKEN")
DEFAULT_API_HOST = "api.github.com"

CLAIM_PATTERNS = (
    re.compile(
        r"\b(?:i(?:'|’)ll|i\s+will|i(?:'|’)m|i\s+am)\s+"
        r"(?:take|pick(?:ing)?\s+up|work(?:ing)?\s+on|handle|implement|fix|address)"
        r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:assign|please\s+assign)\s+(?:this\s+)?(?:issue\s+)?to\s+me\b",
        re.IGNORECASE,
    ),
)
NEGATION_PATTERNS = (
    re.compile(
        r"\b(?:not|no\s+longer|stopped|cannot|can't|won't|unable\s+to)\b.{0,35}"
        r"\b(?:work|working|take|handle|implement|fix|address)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:unassign|release)\s+me\b", re.IGNORECASE),
)


class GitHubError(RuntimeError):
    """An actionable GitHub read failure."""


def normalize_allowed_token_host(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        raise GitHubError("--allow-token-host must not be empty")
    parsed = urllib.parse.urlsplit(f"//{value}")
    try:
        parsed.port
    except ValueError as exc:
        raise GitHubError(f"invalid --allow-token-host: {raw!r}") from exc
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise GitHubError(
            "--allow-token-host must be an exact host or host:port without a scheme or path"
        )
    return parsed.netloc.casefold()


def validate_api_url(
    raw: str,
    token: str | None,
    allow_token_host: str | None = None,
) -> str:
    value = raw.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise GitHubError(f"invalid GitHub API URL: {raw!r}") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise GitHubError("--api-url must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise GitHubError("--api-url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise GitHubError("--api-url must not contain a query or fragment")

    allowed = normalize_allowed_token_host(allow_token_host)
    if token:
        if parsed.scheme.casefold() != "https":
            raise GitHubError("refusing to send a token over a non-HTTPS API URL")
        authority = parsed.netloc.casefold()
        is_default = parsed.hostname.casefold() == DEFAULT_API_HOST and port in (None, 443)
        if not is_default and authority != allowed:
            raise GitHubError(
                "refusing to send a token to an untrusted API host; "
                "pass the exact GitHub Enterprise host with --allow-token-host"
            )
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_today(raw: str | None) -> date:
    if raw is None:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--today must use YYYY-MM-DD") from exc


def subtract_months(value: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be non-negative")
    absolute = value.year * 12 + (value.month - 1) - months
    year, month_zero = divmod(absolute, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_repo(raw: str) -> str:
    value = raw.strip().rstrip("/")
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if value.endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts):
        raise argparse.ArgumentTypeError(
            f"repository must be owner/name or a GitHub URL, got {raw!r}"
        )
    return "/".join(parts)


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hours_between(start: str | None, end: str | None) -> float | None:
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)
    if not start_dt or not end_dt or end_dt < start_dt:
        return None
    return round((end_dt - start_dt).total_seconds() / 3600, 2)


def median_or_none(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return round(float(statistics.median(usable)), 2) if usable else None


@dataclass
class Response:
    data: Any
    headers: dict[str, str]


class GitHubClient:
    """Minimal GET-only GitHub REST client with pagination."""

    def __init__(
        self,
        token: str | None,
        api_url: str = "https://api.github.com",
        timeout: float = 20,
        allow_token_host: str | None = None,
    ) -> None:
        self.token = token
        self.api_url = validate_api_url(api_url, token, allow_token_host)
        parsed = urllib.parse.urlsplit(self.api_url)
        self._api_origin = (parsed.scheme.casefold(), parsed.netloc.casefold())
        self.timeout = timeout
        self.requests = 0

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base = path
        else:
            base = f"{self.api_url}/{path.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode(
                {key: value for key, value in params.items() if value is not None}
            )
            separator = "&" if "?" in base else "?"
            return f"{base}{separator}{query}"
        return base

    def get(self, path: str, params: dict[str, Any] | None = None) -> Response:
        url = self._url(path, params)
        parsed = urllib.parse.urlsplit(url)
        request_origin = (parsed.scheme.casefold(), parsed.netloc.casefold())
        if self.token and request_origin != self._api_origin:
            raise GitHubError("refusing to send a token outside the configured API origin")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "contribute-agent-oss-readonly-snapshot",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        request = urllib.request.Request(url, headers=headers, method="GET")
        if self.token:
            request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
                self.requests += 1
                try:
                    data = json.loads(payload.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise GitHubError(f"GitHub returned invalid JSON for {url}") from exc
                return Response(
                    data=data,
                    headers={key.lower(): value for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            self.requests += 1
            error_headers = exc.headers or {}
            remaining = error_headers.get("X-RateLimit-Remaining")
            reset = error_headers.get("X-RateLimit-Reset")
            try:
                detail = exc.read().decode("utf-8", errors="replace")
                message = json.loads(detail).get("message", detail)
            except (json.JSONDecodeError, AttributeError):
                message = str(exc)
            rate = f"; rate remaining={remaining}, reset={reset}" if remaining is not None else ""
            raise GitHubError(f"GitHub GET {url} failed ({exc.code}): {message}{rate}") from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"Cannot reach GitHub for GET {url}: {exc.reason}") from exc

    def get_all(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        limit: int = 100,
        item_key: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        page = 1
        collected: list[dict[str, Any]] = []
        while len(collected) < limit:
            page_params = dict(params or {})
            page_params["per_page"] = min(100, limit - len(collected))
            page_params["page"] = page
            response = self.get(path, page_params)
            raw = response.data.get(item_key, []) if item_key else response.data
            if not isinstance(raw, list):
                raise GitHubError(f"Expected a list from {path}, got {type(raw).__name__}")
            batch = [item for item in raw if isinstance(item, dict)]
            collected.extend(batch)
            if len(batch) < page_params["per_page"]:
                break
            page += 1
        return collected[:limit]


def token_from_environment(name: str) -> tuple[str | None, str]:
    if name not in ALLOWED_TOKEN_ENVS:
        raise GitHubError(
            f"--token-env must be one of: {', '.join(ALLOWED_TOKEN_ENVS)}"
        )
    if os.environ.get(name):
        return os.environ[name], name
    fallback = "GH_TOKEN" if name == "GITHUB_TOKEN" else "GITHUB_TOKEN"
    if os.environ.get(fallback):
        return os.environ[fallback], fallback
    return None, "anonymous"


def label_names(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels") or []
    names: list[str] = []
    for label in labels:
        if isinstance(label, dict) and isinstance(label.get("name"), str):
            names.append(label["name"])
        elif isinstance(label, str):
            names.append(label)
    return names


def classify_claim(comment: dict[str, Any]) -> dict[str, Any] | None:
    user = comment.get("user") or {}
    if str(user.get("type", "")).casefold() == "bot":
        return None
    body = str(comment.get("body") or "")
    positive = any(pattern.search(body) for pattern in CLAIM_PATTERNS)
    negative = any(pattern.search(body) for pattern in NEGATION_PATTERNS)
    if not positive and not negative:
        return None
    if positive and not negative:
        status = "claimed"
    elif positive and negative:
        status = "ambiguous"
    else:
        status = "retracted-or-ambiguous"
    compact = re.sub(r"\s+", " ", body).strip()
    return {
        "status": status,
        "author": user.get("login"),
        "url": comment.get("html_url"),
        "created_at": comment.get("created_at"),
        "excerpt": compact[:240],
    }


def inspect_claims(comments: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [match for comment in comments if (match := classify_claim(comment))]
    active_claims = [match for match in matches if match["status"] == "claimed"]
    ambiguous = [match for match in matches if match["status"] != "claimed"]
    if active_claims and ambiguous:
        status = "manual-review"
    elif active_claims:
        status = "claimed"
    elif ambiguous:
        status = "manual-review"
    else:
        status = "none-detected"
    return {
        "status": status,
        "matches": matches,
        "note": "Heuristic prefilter only; review semantics, linked PRs, and later comments.",
    }


def normalize_search_repo(repo: dict[str, Any]) -> dict[str, Any]:
    owner = repo.get("owner") or {}
    license_data = repo.get("license") or {}
    return {
        "full_name": repo.get("full_name"),
        "url": repo.get("html_url"),
        "description": repo.get("description"),
        "owner_type": owner.get("type"),
        "stars": repo.get("stargazers_count"),
        "forks": repo.get("forks_count"),
        "open_issues_count_including_prs": repo.get("open_issues_count"),
        "language": repo.get("language"),
        "topics": repo.get("topics") or [],
        "archived": repo.get("archived"),
        "disabled": repo.get("disabled"),
        "pushed_at": repo.get("pushed_at"),
        "updated_at": repo.get("updated_at"),
        "default_branch": repo.get("default_branch"),
        "size_kb": repo.get("size"),
        "license": license_data.get("spdx_id"),
    }


def build_search_query(args: argparse.Namespace, today: date) -> str:
    if args.query:
        return args.query
    pushed_after = subtract_months(today, args.months).isoformat()
    return (
        f"topic:{args.topic} stars:>{args.min_stars} "
        f"pushed:>{pushed_after} archived:false"
    )


def search_snapshot(client: GitHubClient, args: argparse.Namespace) -> dict[str, Any]:
    today = parse_today(args.today)
    query = build_search_query(args, today)
    items = client.get_all(
        "/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc"},
        limit=args.limit,
        item_key="items",
    )
    return {
        "schema_version": 1,
        "kind": "repository-search",
        "collected_at": utc_now(),
        "effective_today": today.isoformat(),
        "query": query,
        "authentication": args.auth_label,
        "pagination": {"requested_limit": args.limit, "returned": len(items)},
        "repositories": [normalize_search_repo(item) for item in items],
        "limitations": [
            "Search results are discovery signals, not a health assessment.",
            "Inspect shortlisted repositories separately for Issue and PR evidence.",
        ],
        "request_count": client.requests,
    }


def issue_counts(client: GitHubClient, repo: str) -> dict[str, Any]:
    counts: dict[str, int | float | None] = {}
    for state in ("open", "closed"):
        response = client.get(
            "/search/issues",
            {"q": f"repo:{repo} type:issue state:{state}", "per_page": 1},
        )
        total = response.data.get("total_count") if isinstance(response.data, dict) else None
        counts[state] = int(total) if isinstance(total, int) else None
    open_count = counts["open"]
    closed_count = counts["closed"]
    counts["closed_open_ratio"] = (
        round(float(closed_count) / float(open_count), 3)
        if isinstance(open_count, int)
        and open_count > 0
        and isinstance(closed_count, int)
        else None
    )
    counts["ratio_note"] = (
        "N/A because open Issues are zero"
        if open_count == 0
        else "closed/open Issue count ratio, not a closure percentage"
    )
    return counts


def latest_commit(client: GitHubClient, repo: str) -> dict[str, Any] | None:
    commits = client.get_all(f"/repos/{repo}/commits", limit=1)
    if not commits:
        return None
    commit = commits[0]
    nested = commit.get("commit") or {}
    author = nested.get("author") or {}
    committer = nested.get("committer") or {}
    return {
        "sha": commit.get("sha"),
        "url": commit.get("html_url"),
        "authored_at": author.get("date"),
        "committed_at": committer.get("date"),
        "author_login": (commit.get("author") or {}).get("login"),
    }


def annotate_commit_recency(
    commit: dict[str, Any] | None, today: date, window_days: int = 30
) -> dict[str, Any] | None:
    if commit is None:
        return None
    result = dict(commit)
    timestamp = parse_timestamp(commit.get("committed_at") or commit.get("authored_at"))
    if timestamp is None:
        result["days_before_effective_today"] = None
        result["within_recent_window"] = None
        return result
    delta = (
        datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timestamp
    ).total_seconds() / 86400
    result["days_before_effective_today"] = round(delta, 2)
    result["recent_window_days"] = window_days
    result["within_recent_window"] = 0 <= delta <= window_days
    if delta < 0:
        result["recency_note"] = "commit timestamp is after the effective snapshot date"
    return result


def release_summary(releases: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [
        {
            "tag": release.get("tag_name"),
            "url": release.get("html_url"),
            "published_at": release.get("published_at"),
            "draft": release.get("draft"),
            "prerelease": release.get("prerelease"),
        }
        for release in releases
        if not release.get("draft")
    ]
    dates = [
        value
        for release in normalized
        if (value := parse_timestamp(release.get("published_at")))
    ]
    dates.sort(reverse=True)
    intervals = [
        round((dates[index] - dates[index + 1]).total_seconds() / 86400, 2)
        for index in range(len(dates) - 1)
    ]
    return {
        "recent": normalized,
        "median_interval_days": median_or_none(intervals),
        "note": "Missing releases do not by themselves prove inactivity.",
    }


def human_event(
    event: dict[str, Any], author_login: str | None, time_field: str
) -> tuple[datetime, dict[str, Any]] | None:
    user = event.get("user") or {}
    login = user.get("login")
    if not login or login == author_login or str(user.get("type", "")).casefold() == "bot":
        return None
    timestamp = parse_timestamp(event.get(time_field))
    if not timestamp:
        return None
    return timestamp, {
        "author": login,
        "url": event.get("html_url"),
        "at": timestamp.isoformat(),
    }


def pull_request_sample(
    client: GitHubClient, repo: str, limit: int
) -> dict[str, Any]:
    pulls = client.get_all(
        f"/repos/{repo}/pulls",
        params={"state": "closed", "sort": "updated", "direction": "desc"},
        limit=limit,
    )
    samples: list[dict[str, Any]] = []
    for pull in pulls:
        number = pull.get("number")
        author_login = (pull.get("user") or {}).get("login")
        comments = client.get_all(f"/repos/{repo}/issues/{number}/comments", limit=100)
        reviews = client.get_all(f"/repos/{repo}/pulls/{number}/reviews", limit=100)
        events: list[tuple[datetime, dict[str, Any]]] = []
        for comment in comments:
            event = human_event(comment, author_login, "created_at")
            if event:
                events.append(event)
        for review in reviews:
            event = human_event(review, author_login, "submitted_at")
            if event:
                events.append(event)
        events.sort(key=lambda item: item[0])
        first = events[0][1] if events else None
        samples.append(
            {
                "number": number,
                "url": pull.get("html_url"),
                "author": author_login,
                "created_at": pull.get("created_at"),
                "merged_at": pull.get("merged_at"),
                "closed_at": pull.get("closed_at"),
                "first_non_author_human_event": first,
                "first_response_hours": hours_between(
                    pull.get("created_at"), first.get("at") if first else None
                ),
                "merge_hours": hours_between(
                    pull.get("created_at"), pull.get("merged_at")
                ),
                "response_limitation": (
                    "Non-author human event; maintainer role is not proven by REST fields."
                ),
            }
        )
    return {
        "sample_size": len(samples),
        "with_human_response": sum(
            sample["first_response_hours"] is not None for sample in samples
        ),
        "merged": sum(sample["merged_at"] is not None for sample in samples),
        "median_first_response_hours": median_or_none(
            sample["first_response_hours"] for sample in samples
        ),
        "median_merge_hours": median_or_none(sample["merge_hours"] for sample in samples),
        "samples": samples,
    }


def issue_candidates(
    client: GitHubClient,
    repo: str,
    today: date,
    activity_days: int,
    labels: set[str],
    limit: int,
) -> dict[str, Any]:
    cutoff = datetime.combine(
        today - timedelta(days=activity_days), datetime.min.time(), tzinfo=timezone.utc
    )
    issues = client.get_all(
        f"/repos/{repo}/issues",
        params={
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "since": cutoff.isoformat(),
        },
        limit=limit,
    )
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for issue in issues:
        reasons: list[str] = []
        if "pull_request" in issue:
            continue
        names = label_names(issue)
        matched = sorted({name for name in names if name.casefold() in labels})
        if not matched:
            reasons.append("no target label")
        if issue.get("state") != "open":
            reasons.append("not open")
        updated = parse_timestamp(issue.get("updated_at"))
        if not updated or updated < cutoff:
            reasons.append("not active within the inclusive cutoff")
        if issue.get("assignee") or issue.get("assignees"):
            reasons.append("assigned")
        claims = {
            "status": "not-checked",
            "matches": [],
            "note": "Comments were not fetched because an earlier deterministic filter failed.",
        }
        if not reasons:
            comments = (
                client.get_all(
                    f"/repos/{repo}/issues/{issue.get('number')}/comments", limit=100
                )
                if int(issue.get("comments") or 0) > 0
                else []
            )
            claims = inspect_claims(comments)
            if claims["status"] == "claimed":
                reasons.append("claim phrase detected")
            elif claims["status"] == "manual-review":
                reasons.append("claim status requires manual review")
        item = {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "labels": names,
            "matched_labels": matched,
            "assignees": [
                user.get("login")
                for user in issue.get("assignees") or []
                if isinstance(user, dict)
            ],
            "comment_count": issue.get("comments"),
            "claim_prefilter": claims,
            "semantic_review_required": [
                "description clarity and expected behavior/reproduction",
                "linked PRs or non-English/implicit claims",
                "estimated 1-3-file scope",
                "repository-wide architecture risk",
            ],
            "body_excerpt": re.sub(r"\s+", " ", str(issue.get("body") or "")).strip()[:500],
        }
        if reasons:
            item["rejection_reasons"] = reasons
            rejected.append(item)
        else:
            accepted.append(item)
    return {
        "activity_cutoff_inclusive": cutoff.isoformat(),
        "target_labels": sorted(labels),
        "api_prefilter_candidates": accepted,
        "rejected_by_deterministic_prefilter": rejected,
        "note": "Every accepted item still requires semantic and source-scope review.",
    }


def inspect_snapshot(client: GitHubClient, args: argparse.Namespace) -> dict[str, Any]:
    repo = parse_repo(args.repo)
    today = parse_today(args.today)
    repository = client.get(f"/repos/{repo}").data
    if not isinstance(repository, dict):
        raise GitHubError(f"Repository response for {repo} is not an object")
    releases = client.get_all(f"/repos/{repo}/releases", limit=args.release_sample)
    commit = annotate_commit_recency(latest_commit(client, repo), today)
    snapshot = {
        "schema_version": 1,
        "kind": "repository-inspection",
        "collected_at": utc_now(),
        "effective_today": today.isoformat(),
        "authentication": args.auth_label,
        "repository": normalize_search_repo(repository),
        "latest_commit": commit,
        "issues": issue_counts(client, repo),
        "releases": release_summary(releases),
        "pull_requests": pull_request_sample(client, repo, args.pr_sample),
        "issue_screen": issue_candidates(
            client,
            repo,
            today,
            args.issue_days,
            {label.casefold() for label in args.label},
            args.issue_limit,
        ),
        "limitations": [
            "Issue clarity and change scope require source-aware semantic review.",
            "Claim matching is a heuristic and linked work must be rechecked.",
            "PR first response is the earliest non-author human event; maintainer role may be unknown.",
            "Samples and rate limits may not represent the repository's entire history.",
        ],
    }
    snapshot["request_count"] = client.requests
    return snapshot


def write_output(
    payload: dict[str, Any], output: str | None, force: bool = False
) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = Path(os.path.abspath(Path(output).expanduser()))
        if path.is_symlink():
            raise GitHubError(f"refusing to write through an output symlink: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            raise GitHubError(f"refusing to overwrite existing output without --force: {path}")
        if path.is_symlink():
            raise GitHubError(f"refusing to write through an output symlink: {path}")
        mode = "w" if force else "x"
        try:
            with path.open(mode, encoding="utf-8", newline="") as handle:
                handle.write(serialized)
        except FileExistsError as exc:
            raise GitHubError(
                f"refusing to overwrite existing output without --force: {path}"
            ) from exc
        print(path)
    else:
        print(serialized, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read GitHub REST data and emit reproducible JSON evidence. Uses GET only."
    )
    parser.add_argument("--api-url", default="https://api.github.com")
    parser.add_argument("--token-env", choices=ALLOWED_TOKEN_ENVS, default="GITHUB_TOKEN")
    parser.add_argument(
        "--allow-token-host",
        help="exact trusted GitHub Enterprise host or host:port for token use",
    )
    parser.add_argument("--timeout", type=float, default=20)
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="discover candidate repositories")
    search.add_argument("--query")
    search.add_argument("--topic", default="ai-agent")
    search.add_argument("--min-stars", type=int, default=1000)
    search.add_argument("--months", type=int, choices=(2, 3), default=3)
    search.add_argument("--today", help="fixed UTC date for reproducibility")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--output")
    search.add_argument("--force", action="store_true")

    inspect = subparsers.add_parser("inspect", help="inspect one repository")
    inspect.add_argument("repo")
    inspect.add_argument("--today", help="fixed UTC date for reproducibility")
    inspect.add_argument("--issue-days", type=int, default=60)
    inspect.add_argument("--issue-limit", type=int, default=50)
    inspect.add_argument("--pr-sample", type=int, default=10)
    inspect.add_argument("--release-sample", type=int, default=20)
    inspect.add_argument("--label", action="append", default=sorted(DEFAULT_LABELS))
    inspect.add_argument("--output")
    inspect.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be positive")
    for field in ("issue_days", "issue_limit", "pr_sample", "release_sample"):
        if hasattr(args, field) and getattr(args, field) < 1:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    try:
        token, auth_label = token_from_environment(args.token_env)
        args.auth_label = auth_label
        client = GitHubClient(
            token=token,
            api_url=args.api_url,
            timeout=args.timeout,
            allow_token_host=args.allow_token_host,
        )
        if args.command == "search":
            payload = search_snapshot(client, args)
        else:
            payload = inspect_snapshot(client, args)
        write_output(payload, args.output, args.force)
        return 0
    except (GitHubError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
