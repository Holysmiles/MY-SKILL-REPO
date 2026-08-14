#!/usr/bin/env python3
"""Collect read-only Git and contribution-policy preflight information.

Only plumbing and inspection commands are used.  Optional Git index writes are
disabled, no network operation is attempted, and remote URL credentials are
redacted before output.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
}

COMMON_DEFAULT_BRANCHES = ("main", "master", "trunk", "develop")
GIT_TIMEOUT_SECONDS = 30
REPOSITORY_ENVIRONMENT_KEYS = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
}


class PreflightError(RuntimeError):
    """Raised when a Git preflight cannot be collected."""


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").rstrip("\r\n")


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _repository_hint(path: Path) -> Path:
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        marker = candidate / ".git"
        if marker.exists() or marker.is_symlink():
            return candidate
    return resolved


def _resolve_git_executable(path: Path) -> Path:
    configured = os.environ.get("GIT_EXECUTABLE")
    if configured:
        candidate_text = configured
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            candidate_text = shutil.which(configured) or configured
    else:
        candidate_text = shutil.which("git")
    if not candidate_text:
        raise PreflightError("git executable was not found")
    try:
        executable = Path(candidate_text).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PreflightError(f"cannot resolve git executable: {exc}") from exc
    if not executable.is_file():
        raise PreflightError(f"git executable is not a file: {executable}")
    repository = _repository_hint(path)
    if _path_is_within(executable, repository):
        raise PreflightError(
            f"refusing to execute a Git program located inside the inspected repository: {executable}"
        )
    return executable


def _run_git(path: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    executable = _resolve_git_executable(path)
    command = [
        str(executable),
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-C",
        str(path),
        *arguments,
    ]
    environment = os.environ.copy()
    for key in REPOSITORY_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    environment.pop("GIT_CONFIG_COUNT", None)
    for key in list(environment):
        if key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            environment.pop(key, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_PAGER"] = "cat"
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise PreflightError("git executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(f"git {' '.join(arguments)} timed out after {GIT_TIMEOUT_SECONDS} seconds") from exc
    if check and completed.returncode != 0:
        detail = _decode(completed.stderr) or _decode(completed.stdout) or f"exit code {completed.returncode}"
        raise PreflightError(f"git {' '.join(arguments)} failed: {detail}")
    return completed


def _redact_remote_url(url: str) -> str:
    """Remove passwords and common secret query parameters from a remote URL."""

    if not url:
        return url
    if "://" not in url and "@" in url:
        userinfo, remainder = url.split("@", 1)
        if ":" in userinfo:
            return f"***:***@{remainder}"
        if userinfo.casefold() != "git":
            return f"***@{remainder}"
        return url
    try:
        split = urlsplit(url)
        hostname = split.hostname or ""
        port = split.port
        username = split.username
        password = split.password
    except ValueError:
        return "<redacted-invalid-url>" if "@" in url and "://" in url else url
    if not split.scheme or not split.netloc:
        return url

    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if port is not None:
        hostname = f"{hostname}:{port}"
    if username is not None:
        userinfo = "***:***@" if password is not None else "***@"
        netloc = userinfo + hostname
    else:
        netloc = hostname

    def sensitive_key(key: str) -> bool:
        folded = key.casefold()
        markers = ("token", "password", "secret", "signature", "credential", "api_key", "apikey")
        return (
            folded in SENSITIVE_QUERY_KEYS
            or folded.endswith("_key")
            or any(marker in folded for marker in markers)
        )

    query_items = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        redacted = "***" if sensitive_key(key) else value
        query_items.append((key, redacted))
    fragment = "***" if split.fragment else ""
    return urlunsplit((split.scheme, netloc, split.path, urlencode(query_items), fragment))


def _split_lines(completed: subprocess.CompletedProcess[bytes]) -> list[str]:
    return [line for line in (_decode(completed.stdout)).splitlines() if line]


def _remote_from_ref(ref: str, remote_names: list[str]) -> tuple[str | None, str | None]:
    for remote in sorted(remote_names, key=len, reverse=True):
        prefix = remote + "/"
        if ref.startswith(prefix):
            return remote, ref[len(prefix) :]
    return None, None


def _collect_remotes(root: Path) -> list[dict[str, Any]]:
    names = sorted(_split_lines(_run_git(root, "remote")), key=str.casefold)
    remotes: list[dict[str, Any]] = []
    for name in names:
        fetch = _run_git(root, "remote", "get-url", "--all", name, check=False)
        push = _run_git(root, "remote", "get-url", "--push", "--all", name, check=False)
        symbolic = _run_git(root, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{name}/HEAD", check=False)
        head_ref = _decode(symbolic.stdout) if symbolic.returncode == 0 else ""
        prefix = name + "/"
        remotes.append(
            {
                "name": name,
                "fetch_urls": [_redact_remote_url(value) for value in _split_lines(fetch)],
                "push_urls": [_redact_remote_url(value) for value in _split_lines(push)],
                "head_branch": head_ref[len(prefix) :] if head_ref.startswith(prefix) else None,
            }
        )
    return remotes


def _ref_exists(root: Path, ref: str) -> bool:
    result = _run_git(root, "show-ref", "--verify", "--quiet", ref, check=False)
    return result.returncode == 0


def _select_default_branch(
    root: Path,
    remotes: list[dict[str, Any]],
    current_branch: str | None,
) -> dict[str, Any] | None:
    by_name = {remote["name"]: remote for remote in remotes}
    ordered_names = [name for name in ("upstream", "origin") if name in by_name]
    ordered_names.extend(name for name in sorted(by_name, key=str.casefold) if name not in ordered_names)

    for remote_name in ordered_names:
        branch = by_name[remote_name]["head_branch"]
        if branch:
            return {
                "name": branch,
                "remote": remote_name,
                "ref": f"{remote_name}/{branch}",
                "source": "remote-head",
            }
    for remote_name in ordered_names:
        for branch in COMMON_DEFAULT_BRANCHES:
            if _ref_exists(root, f"refs/remotes/{remote_name}/{branch}"):
                return {
                    "name": branch,
                    "remote": remote_name,
                    "ref": f"{remote_name}/{branch}",
                    "source": "inferred-common-remote-branch",
                }

    local_branches = _split_lines(_run_git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads"))
    for branch in COMMON_DEFAULT_BRANCHES:
        if branch in local_branches:
            return {"name": branch, "remote": None, "ref": branch, "source": "common-local-branch"}
    if len(local_branches) == 1:
        branch = local_branches[0]
        return {"name": branch, "remote": None, "ref": branch, "source": "only-local-branch"}
    if not local_branches and current_branch:
        return {
            "name": current_branch,
            "remote": None,
            "ref": current_branch,
            "source": "unborn-current-branch",
        }
    if current_branch and current_branch in local_branches and not remotes:
        return {"name": current_branch, "remote": None, "ref": current_branch, "source": "current-local-branch"}
    return None


def _parse_status(raw: bytes) -> list[dict[str, Any]]:
    chunks = raw.split(b"\0")
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if not chunk:
            continue
        if len(chunk) < 3:
            entries.append({"code": "!!", "path": _decode(chunk), "original_path": None})
            continue
        code = chunk[:2].decode("ascii", errors="replace")
        path = chunk[3:].decode("utf-8", errors="replace")
        original_path = None
        if "R" in code or "C" in code:
            if index < len(chunks) and chunks[index]:
                original_path = chunks[index].decode("utf-8", errors="replace")
                index += 1
        entries.append({"code": code, "path": path, "original_path": original_path})
    return entries


def _working_tree(root: Path) -> dict[str, Any]:
    completed = _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    entries = _parse_status(completed.stdout)
    conflicts = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
    return {
        "clean": not entries,
        "dirty": bool(entries),
        "has_staged": any(entry["code"][0] not in {" ", "?", "!"} for entry in entries),
        "has_unstaged": any(entry["code"][1] not in {" ", "?", "!"} for entry in entries),
        "has_untracked": any(entry["code"] == "??" for entry in entries),
        "has_conflicts": any(entry["code"] in conflicts for entry in entries),
        "staged": sum(1 for entry in entries if entry["code"][0] not in {" ", "?", "!"}),
        "unstaged": sum(1 for entry in entries if entry["code"][1] not in {" ", "?", "!"}),
        "untracked": sum(1 for entry in entries if entry["code"] == "??"),
        "conflicted": sum(1 for entry in entries if entry["code"] in conflicts),
        "entries": entries,
    }


def _safe_files(directory: Path) -> list[Path]:
    if _path_is_link_like(directory) or not directory.is_dir():
        return []
    try:
        with os.scandir(directory) as iterator:
            files = [
                Path(entry.path)
                for entry in iterator
                if not _entry_is_link_like(entry) and entry.is_file(follow_symlinks=False)
            ]
    except OSError:
        return []
    return sorted(files, key=lambda path: path.name.casefold())


def _safe_directories(directory: Path) -> list[Path]:
    if _path_is_link_like(directory) or not directory.is_dir():
        return []
    try:
        with os.scandir(directory) as iterator:
            directories = [
                Path(entry.path)
                for entry in iterator
                if not _entry_is_link_like(entry) and entry.is_dir(follow_symlinks=False)
            ]
    except OSError:
        return []
    return sorted(directories, key=lambda path: path.name.casefold())


def _entry_is_link_like(entry: os.DirEntry[str]) -> bool:
    if entry.is_symlink() or os.path.ismount(entry.path):
        return True
    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _path_is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _relative_paths(paths: Iterable[Path], root: Path) -> list[str]:
    return sorted({path.relative_to(root).as_posix() for path in paths}, key=str.casefold)


def _discover_policies(root: Path) -> dict[str, list[str]]:
    search_roots: list[Path] = [root]
    root_directories = {path.name.casefold(): path for path in _safe_directories(root)}
    for name in (".github", "docs"):
        if name in root_directories:
            search_roots.append(root_directories[name])

    contributing: list[Path] = []
    security: list[Path] = []
    templates: list[Path] = []
    for directory in search_roots:
        for path in _safe_files(directory):
            lower = path.name.casefold()
            if lower == "contributing" or lower.startswith("contributing."):
                contributing.append(path)
            if lower == "security" or lower.startswith("security."):
                security.append(path)
            if lower == "pull_request_template.md":
                templates.append(path)
        for child in _safe_directories(directory):
            if child.name.casefold() == "pull_request_template":
                templates.extend(path for path in _safe_files(child) if path.suffix.casefold() == ".md")

    return {
        "pull_request_templates": _relative_paths(templates, root),
        "contributing": _relative_paths(contributing, root),
        "security": _relative_paths(security, root),
    }


def _display(value: object) -> str:
    """Escape control characters before rendering repository-controlled text."""

    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def collect_preflight(repository: str | os.PathLike[str] = ".") -> dict[str, Any]:
    """Collect local repository state without modifying Git or contacting remotes."""

    supplied = Path(repository).expanduser()
    try:
        supplied = supplied.resolve(strict=True)
    except OSError as exc:
        raise PreflightError(f"cannot resolve repository path: {exc}") from exc
    if not supplied.is_dir():
        raise PreflightError(f"repository path is not a directory: {supplied}")

    root_result = _run_git(supplied, "rev-parse", "--show-toplevel", check=False)
    if root_result.returncode != 0:
        detail = _decode(root_result.stderr) or "not a Git working tree"
        raise PreflightError(detail)
    root = Path(_decode(root_result.stdout)).resolve()
    inside = _run_git(root, "rev-parse", "--is-inside-work-tree", check=False)
    if inside.returncode != 0 or _decode(inside.stdout) != "true":
        raise PreflightError("bare repositories are not supported")

    warnings: list[str] = []
    branch_result = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    current_branch = _decode(branch_result.stdout) if branch_result.returncode == 0 else None
    detached = current_branch is None
    head_result = _run_git(root, "rev-parse", "--verify", "HEAD", check=False)
    head_commit = _decode(head_result.stdout) if head_result.returncode == 0 else None
    if head_commit is None:
        warnings.append("HEAD has no commit yet")

    remotes = _collect_remotes(root)
    remote_names = [remote["name"] for remote in remotes]
    default_branch = _select_default_branch(root, remotes, current_branch)
    if default_branch is None:
        warnings.append("default branch could not be determined from local Git metadata")

    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    upstream: dict[str, Any] | None = None
    if upstream_result.returncode == 0:
        upstream_ref = _decode(upstream_result.stdout)
        upstream_remote, upstream_branch = _remote_from_ref(upstream_ref, remote_names)
        ahead = behind = None
        counts = _run_git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}", check=False)
        if counts.returncode == 0:
            match = re.fullmatch(r"(\d+)\s+(\d+)", _decode(counts.stdout))
            if match:
                ahead, behind = (int(match.group(1)), int(match.group(2)))
        upstream = {
            "ref": upstream_ref,
            "remote": upstream_remote,
            "branch": upstream_branch,
            "ahead": ahead,
            "behind": behind,
        }
    elif current_branch:
        warnings.append(f"branch {current_branch} has no upstream")

    base: dict[str, str] | None = None
    if head_commit and default_branch:
        merge_base = _run_git(root, "merge-base", "HEAD", default_branch["ref"], check=False)
        if merge_base.returncode == 0:
            base = {"ref": default_branch["ref"], "commit": _decode(merge_base.stdout)}
        else:
            warnings.append(f"no merge base found between HEAD and {default_branch['ref']}")

    return {
        "schema_version": 1,
        "repository_root": str(root),
        "head": {"commit": head_commit, "branch": current_branch, "detached": detached},
        "default_branch": default_branch,
        "remotes": remotes,
        "upstream": upstream,
        "base": base,
        "working_tree": _working_tree(root),
        "policies": _discover_policies(root),
        "warnings": warnings,
    }


def _human_lines(result: dict[str, Any]) -> Iterable[str]:
    head = result["head"]
    working = result["working_tree"]
    default = result["default_branch"]
    upstream = result["upstream"]
    base = result["base"]
    yield "Git preflight"
    yield f"Repository root: {_display(result['repository_root'])}"
    yield f"HEAD: {_display(head['commit']) if head['commit'] else '(unborn)'}"
    yield f"Current branch: {_display(head['branch']) if head['branch'] else '(detached)'}"
    yield f"Default branch: {_display(default['ref']) if default else '(unknown)'}"
    yield f"Upstream: {_display(upstream['ref']) if upstream else '(none)'}"
    if upstream and upstream["ahead"] is not None:
        yield f"Ahead/behind upstream: {upstream['ahead']}/{upstream['behind']}"
    yield f"Base commit: {base['commit'] if base else '(unknown)'}"
    yield (
        "Working tree: "
        + (
            "clean"
            if working["clean"]
            else (
                f"dirty ({working['staged']} staged, {working['unstaged']} unstaged, "
                f"{working['untracked']} untracked, {working['conflicted']} conflicted)"
            )
        )
    )
    yield "Remotes:"
    if not result["remotes"]:
        yield "  (none)"
    for remote in result["remotes"]:
        fetch = ", ".join(remote["fetch_urls"]) or "(none)"
        push = ", ".join(remote["push_urls"]) or "(none)"
        yield (
            f"  {_display(remote['name'])}: fetch={_display(fetch)}; push={_display(push)}; "
            f"HEAD={_display(remote['head_branch']) if remote['head_branch'] else '(unknown)'}"
        )
    policies = result["policies"]
    yield f"PR templates: {', '.join(_display(value) for value in policies['pull_request_templates']) or '(none)'}"
    yield f"Contributing policy: {', '.join(_display(value) for value in policies['contributing']) or '(none)'}"
    yield f"Security policy: {', '.join(_display(value) for value in policies['security']) or '(none)'}"
    if working["entries"]:
        yield "Status entries:"
        for entry in working["entries"]:
            rename = f" <- {entry['original_path']}" if entry["original_path"] else ""
            yield f"  {entry['code']} {_display(entry['path'])}{_display(rename) if rename else ''}"
    for warning in result["warnings"]:
        yield f"Warning: {_display(warning)}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", default=".", help="path inside a Git working tree (default: .)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--format", choices=("human", "json"), default="human", help="output format")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_json = args.json or args.format == "json"
    try:
        result = collect_preflight(args.repository)
    except PreflightError as exc:
        if output_json:
            print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, ensure_ascii=True))
        else:
            print(f"Error: {_display(exc)}", file=sys.stderr)
        return 2
    if output_json:
        payload = dict(result)
        payload["ok"] = True
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    else:
        print("\n".join(_human_lines(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
