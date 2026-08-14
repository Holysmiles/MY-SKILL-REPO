#!/usr/bin/env python3
"""Create a bounded, read-only inventory of a source repository.

The inventory deliberately uses names and directory metadata only.  It does not
open project files, follows no symlinks, and excludes common secret, generated,
vendor, and binary paths before they can enter an analysis context.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterable


DEFAULT_DEPTH = 3
MAX_DEPTH = 20
DEFAULT_MAX_ENTRIES = 10_000
MAX_ENTRIES = 100_000

SKIP_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".bzr",
    "node_modules",
    "vendor",
    "third_party",
    "build",
    "dist",
    "out",
    "target",
    "coverage",
    "htmlcov",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".cache",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "virtualenv",
    "env",
    "site-packages",
    "generated",
    "generated-code",
}

SECRET_DIRECTORY_NAMES = {
    ".aws",
    ".azure",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
    ".secrets",
    "credentials",
    "private",
    "secrets",
}

BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".db",
    ".dll",
    ".dmg",
    ".doc",
    ".docx",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".iso",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lib",
    ".mdb",
    ".npy",
    ".npz",
    ".mp3",
    ".mp4",
    ".mov",
    ".o",
    ".obj",
    ".onnx",
    ".otf",
    ".parquet",
    ".pb",
    ".pickle",
    ".pkl",
    ".pyc",
    ".pyd",
    ".pyo",
    ".safetensors",
    ".pdf",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tif",
    ".tiff",
    ".ttf",
    ".wav",
    ".wasm",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xz",
    ".zip",
}

CORE_DIRECTORY_NAMES = {
    "agent",
    "agents",
    "api",
    "backend",
    "cmd",
    "core",
    "internal",
    "lib",
    "packages",
    "pkg",
    "server",
    "src",
}

DOC_PREFIXES = (
    "readme",
    "contributing",
    "changelog",
    "history",
    "security",
    "code_of_conduct",
    "code-of-conduct",
    "support",
    "governance",
)

ENTRY_BASENAMES = {
    "__main__.py",
    "app.py",
    "cli.py",
    "main.py",
    "manage.py",
    "server.py",
    "app.js",
    "app.jsx",
    "app.mjs",
    "app.ts",
    "app.tsx",
    "cli.js",
    "cli.mjs",
    "cli.ts",
    "index.cjs",
    "index.js",
    "index.mjs",
    "index.ts",
    "index.tsx",
    "main.cjs",
    "main.go",
    "main.java",
    "main.js",
    "main.mjs",
    "main.rs",
    "main.ts",
    "main.tsx",
    "program.cs",
    "server.js",
    "server.ts",
}

STYLE_CONFIG_EXACT = {
    ".editorconfig",
    ".flake8",
    ".stylelintrc",
    ".stylelintrc.json",
    ".stylelintrc.js",
    ".stylelintrc.yml",
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.js",
    ".prettierrc.yml",
    "biome.json",
    "black.toml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.ts",
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    "setup.cfg",
    "tox.ini",
    "tsconfig.json",
}

TEST_CONFIG_EXACT = {
    "jest.config.js",
    "jest.config.cjs",
    "jest.config.mjs",
    "jest.config.ts",
    "karma.conf.js",
    "playwright.config.js",
    "playwright.config.ts",
    "pytest.ini",
    "tox.ini",
    "vitest.config.js",
    "vitest.config.ts",
    "vitest.config.mjs",
    "cypress.config.js",
    "cypress.config.ts",
}

TEST_DIRECTORY_NAMES = {
    "test",
    "tests",
    "spec",
    "specs",
    "__tests__",
    "e2e",
    "integration-tests",
}


class InventoryError(ValueError):
    """Raised when the requested inventory cannot be collected safely."""


def _relative(path: Path, root: Path) -> str:
    """Return a stable, POSIX-style path relative to *root*."""

    relative = path.relative_to(root)
    return relative.as_posix() if relative.parts else "."


def _is_template_secret_name(name: str) -> bool:
    return any(token in name for token in ("example", "sample", "template"))


def _secret_reason(name: str, is_directory: bool) -> str | None:
    lower = name.casefold()
    if is_directory:
        return "secret-directory" if lower in SECRET_DIRECTORY_NAMES else None

    if lower in {".git-credentials", ".netrc", "_netrc", ".pypirc", ".npmrc"}:
        return "secret-file"
    if lower.startswith(".env") and not _is_template_secret_name(lower):
        return "secret-file"
    if lower in {
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials.json",
        "credentials.yml",
        "credentials.yaml",
        "client_secret.json",
        "client-secrets.json",
        "token.json",
        "secrets.json",
        "secrets.yml",
        "secrets.yaml",
    }:
        return "secret-file"
    if lower.startswith("service-account") and Path(lower).suffix in {".json", ".yaml", ".yml"}:
        return "secret-file"
    if Path(lower).suffix in {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}:
        return "secret-file"
    return None


def _binary_reason(name: str) -> str | None:
    return "binary-file" if Path(name.casefold()).suffix in BINARY_SUFFIXES else None


def _is_link_like(entry: os.DirEntry[str]) -> bool:
    """Detect symlinks, mount points, and Windows reparse points."""

    if entry.is_symlink() or os.path.ismount(entry.path):
        return True
    attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _is_link_like_root(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _is_nested_repository(path: Path) -> bool:
    """Recognize submodules and nested worktrees without opening .git."""

    try:
        os.lstat(path / ".git")
    except OSError:
        return False
    return True


def _is_doc(path: str) -> bool:
    name = Path(path).name.casefold()
    if any(name == prefix or name.startswith(prefix + ".") or name.startswith(prefix + "-") for prefix in DOC_PREFIXES):
        return True
    parts = Path(path).parts
    return bool(parts and parts[0].casefold() in {"doc", "docs", "documentation"}) and Path(path).suffix.casefold() in {
        ".adoc",
        ".md",
        ".mdx",
        ".rst",
        ".txt",
    }


def _is_entry(path: str) -> bool:
    parsed = Path(path)
    name = parsed.name.casefold()
    if name not in ENTRY_BASENAMES:
        return False
    excluded_parts = {"doc", "docs", "documentation", "example", "examples", "test", "tests", "spec", "specs"}
    return not any(part.casefold() in excluded_parts for part in parsed.parts[:-1])


def _is_style_config(path: str) -> bool:
    name = Path(path).name.casefold()
    if name in {value.casefold() for value in STYLE_CONFIG_EXACT}:
        return True
    return name.startswith((".eslintrc", ".prettierrc", "stylelint.config", "eslint.config"))


def _is_test_config(path: str) -> bool:
    name = Path(path).name.casefold()
    if name in {value.casefold() for value in TEST_CONFIG_EXACT}:
        return True
    return name.startswith(("jest.config", "vitest.config", "playwright.config", "cypress.config"))


def _is_test_root(path: str, kind: str) -> bool:
    return kind == "directory" and Path(path).name.casefold() in TEST_DIRECTORY_NAMES


def _empty_result(root: Path, depth: int, max_entries: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "root": str(root),
        "max_depth": depth,
        "max_entries": max_entries,
        "entries": [],
        "detected": {
            "documentation": [],
            "entry_points": [],
            "style_configs": [],
            "test_configs": [],
            "test_roots": [],
            "core_directories": [],
            "nested_repositories": [],
        },
        "summary": {
            "files": 0,
            "directories": 0,
            "encountered": 0,
            "skipped": 0,
            "skipped_by_reason": {},
            "depth_limited_directories": 0,
            "truncated": False,
        },
        "warnings": [],
    }


def _record_skip(result: dict[str, Any], reason: str) -> None:
    summary = result["summary"]
    summary["skipped"] += 1
    by_reason = summary["skipped_by_reason"]
    by_reason[reason] = by_reason.get(reason, 0) + 1


def _display(value: object) -> str:
    """Escape control characters before rendering untrusted path text."""

    return json.dumps(str(value), ensure_ascii=True)[1:-1]


def inventory_repository(
    repository: str | os.PathLike[str] = ".",
    *,
    max_depth: int = DEFAULT_DEPTH,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict[str, Any]:
    """Return a bounded inventory without reading repository file contents."""

    if not isinstance(max_depth, int) or not 0 <= max_depth <= MAX_DEPTH:
        raise InventoryError(f"max_depth must be between 0 and {MAX_DEPTH}")
    if not isinstance(max_entries, int) or not 1 <= max_entries <= MAX_ENTRIES:
        raise InventoryError(f"max_entries must be between 1 and {MAX_ENTRIES}")

    supplied = Path(repository).expanduser()
    if _is_link_like_root(supplied):
        raise InventoryError("repository root must not be a symlink")
    try:
        root = supplied.resolve(strict=True)
    except OSError as exc:
        raise InventoryError(f"cannot resolve repository path: {exc}") from exc
    if not root.is_dir():
        raise InventoryError(f"repository path is not a directory: {root}")

    result = _empty_result(root, max_depth, max_entries)
    state = {"stop": False}

    def add_entry(path: Path, kind: str, depth: int) -> None:
        relative = _relative(path, root)
        result["entries"].append({"path": relative, "kind": kind, "depth": depth})
        if kind == "file":
            result["summary"]["files"] += 1
            if _is_doc(relative):
                result["detected"]["documentation"].append(relative)
            if _is_entry(relative):
                result["detected"]["entry_points"].append(relative)
            if _is_style_config(relative):
                result["detected"]["style_configs"].append(relative)
            if _is_test_config(relative):
                result["detected"]["test_configs"].append(relative)
        else:
            result["summary"]["directories"] += 1
            if _is_test_root(relative, kind):
                result["detected"]["test_roots"].append(relative)
            if depth == 1 and path.name.casefold() in CORE_DIRECTORY_NAMES:
                result["detected"]["core_directories"].append(relative)

    def walk(directory: Path, depth: int) -> None:
        if state["stop"] or depth >= max_depth:
            if depth >= max_depth:
                result["summary"]["depth_limited_directories"] += 1
            return
        try:
            with os.scandir(directory) as iterator:
                children: list[os.DirEntry[str]] = []
                for child in iterator:
                    if result["summary"]["encountered"] >= max_entries:
                        result["summary"]["truncated"] = True
                        state["stop"] = True
                        break
                    result["summary"]["encountered"] += 1
                    children.append(child)
        except OSError as exc:
            result["warnings"].append(f"could not read {_relative(directory, root)}: {exc}")
            return

        children.sort(key=lambda item: item.name.casefold())
        for child in children:
            child_path = Path(child.path)
            relative = _relative(child_path, root)
            try:
                if _is_link_like(child):
                    _record_skip(result, "symlink")
                    continue
                is_directory = child.is_dir(follow_symlinks=False)
                if is_directory and child.name.casefold() in SKIP_DIRECTORY_NAMES:
                    _record_skip(result, "excluded-directory")
                    continue
                secret_reason = _secret_reason(child.name, is_directory)
                if secret_reason:
                    _record_skip(result, secret_reason)
                    continue
                if not is_directory:
                    if child.is_file(follow_symlinks=False):
                        binary_reason = _binary_reason(child.name)
                        if binary_reason:
                            _record_skip(result, binary_reason)
                            continue
                        add_entry(child_path, "file", depth + 1)
                    else:
                        _record_skip(result, "special-file")
                    continue
                add_entry(child_path, "directory", depth + 1)
                if _is_nested_repository(child_path):
                    result["detected"]["nested_repositories"].append(relative)
                    _record_skip(result, "nested-repository")
                    continue
                if depth + 1 < max_depth and not state["stop"]:
                    walk(child_path, depth + 1)
                else:
                    result["summary"]["depth_limited_directories"] += 1
            except OSError as exc:
                _record_skip(result, "unreadable")
                result["warnings"].append(f"could not inspect {relative}: {exc}")

    walk(root, 0)
    for values in result["detected"].values():
        values.sort(key=str.casefold)
    result["entries"].sort(key=lambda item: (item["path"].casefold(), item["kind"]))
    return result


def _human_lines(result: dict[str, Any]) -> Iterable[str]:
    summary = result["summary"]
    yield "Repository inventory"
    yield f"Root: {_display(result['root'])}"
    yield f"Depth: {result['max_depth']} (encountered {summary['encountered']} entries)"
    yield ""
    yield "Tree:"
    for entry in result["entries"]:
        indent = "  " * max(0, entry["depth"] - 1)
        marker = "[D]" if entry["kind"] == "directory" else "[F]"
        yield f"{indent}{marker} {_display(entry['path'])}"
    yield ""
    yield (
        "Summary: "
        f"{summary['files']} files, {summary['directories']} directories, "
        f"{summary['skipped']} skipped"
        + (" (truncated)" if summary["truncated"] else "")
    )
    detected = result["detected"]
    labels = (
        ("Documentation", "documentation"),
        ("Entry points", "entry_points"),
        ("Style configs", "style_configs"),
        ("Test configs", "test_configs"),
        ("Test roots", "test_roots"),
        ("Core directories", "core_directories"),
        ("Nested repositories", "nested_repositories"),
    )
    for label, key in labels:
        values = detected[key]
        yield f"{label}: {', '.join(_display(value) for value in values) if values else '(none)'}"
    if summary["skipped_by_reason"]:
        pairs = ", ".join(f"{key}={value}" for key, value in sorted(summary["skipped_by_reason"].items()))
        yield f"Skipped by reason: {pairs}"
    for warning in result["warnings"]:
        yield f"Warning: {_display(warning)}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", default=".", help="repository directory (default: .)")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help=f"maximum depth (default: {DEFAULT_DEPTH})")
    parser.add_argument(
        "--max-entries",
        type=int,
        default=DEFAULT_MAX_ENTRIES,
        help=f"maximum entries inspected (default: {DEFAULT_MAX_ENTRIES})",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--format", choices=("human", "json"), default="human", help="output format")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_json = args.json or args.format == "json"
    try:
        result = inventory_repository(args.repository, max_depth=args.depth, max_entries=args.max_entries)
    except InventoryError as exc:
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
