#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "architecture.md"
MARKDOWN_LINK = re.compile(
    r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+['\"][^)]*['\"])?\)"
)
MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(?P<body>.*?)\n```", re.DOTALL)
NODE_DECLARATION = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*(?=\[|\{|\()")
DIRECTED_EDGE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:-->|-\.->)"
    r"(?:\|.*\|)?\s*([A-Za-z][A-Za-z0-9_]*)\s*$"
)


def repository_markdown_files() -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def local_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.startswith("#"):
        return None

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    return unquote(parsed.path) if parsed.path else None


def check_markdown_links(files: list[Path]) -> list[str]:
    failures: list[str] = []
    for markdown_file in files:
        content = markdown_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in MARKDOWN_LINK.finditer(line):
                target = local_link_target(match.group("target"))
                if target is None:
                    continue
                candidate = (
                    ROOT / target.lstrip("/")
                    if target.startswith("/")
                    else markdown_file.parent / target
                )
                if not candidate.exists():
                    relative_file = markdown_file.relative_to(ROOT)
                    failures.append(f"{relative_file}:{line_number}: missing link target {target}")
    return failures


def walk(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, set()):
            if target not in visited:
                visited.add(target)
                queue.append(target)
    return visited


def check_architecture() -> tuple[list[str], int, int]:
    failures: list[str] = []
    content = ARCHITECTURE.read_text(encoding="utf-8")
    blocks = list(MERMAID_BLOCK.finditer(content))
    if len(blocks) != 1:
        return [f"architecture.md: expected one Mermaid block, found {len(blocks)}"], 0, 0

    body = blocks[0].group("body")
    if "React" in body:
        failures.append("architecture.md: React is outside the frozen first-stage boundary")

    declarations: dict[str, int] = defaultdict(int)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    edge_count = 0

    for line_number, line in enumerate(body.splitlines(), start=1):
        declaration = NODE_DECLARATION.match(line)
        if declaration:
            declarations[declaration.group(1)] += 1

        if "---" in line and "-->" not in line:
            failures.append(f"architecture.md Mermaid line {line_number}: undirected edge is forbidden")

        if "-->" not in line and "-.->" not in line:
            continue
        edge = DIRECTED_EDGE.match(line)
        if edge is None:
            failures.append(f"architecture.md Mermaid line {line_number}: unsupported edge syntax")
            continue
        source, target = edge.groups()
        outgoing[source].add(target)
        incoming[target].add(source)
        edge_count += 1

    duplicates = sorted(node for node, count in declarations.items() if count > 1)
    if duplicates:
        failures.append(f"architecture.md: duplicate node declarations: {', '.join(duplicates)}")

    referenced = set(outgoing) | set(incoming)
    missing = sorted(referenced - set(declarations))
    if missing:
        failures.append(f"architecture.md: undeclared edge endpoints: {', '.join(missing)}")

    for required in ("user", "userResult"):
        if required not in declarations:
            failures.append(f"architecture.md: missing required flow endpoint {required}")

    if "user" in declarations:
        unreachable = sorted(set(declarations) - walk("user", outgoing))
        if unreachable:
            failures.append(f"architecture.md: unreachable from user: {', '.join(unreachable)}")

    if "userResult" in declarations:
        cannot_finish = sorted(set(declarations) - walk("userResult", incoming))
        if cannot_finish:
            failures.append(
                f"architecture.md: cannot reach userResult: {', '.join(cannot_finish)}"
            )

    return failures, len(declarations), edge_count


def main() -> int:
    if sys.version_info < (3, 11):
        print("repository checks require Python 3.11 or newer", file=sys.stderr)
        return 1

    markdown_files = repository_markdown_files()
    failures = check_markdown_links(markdown_files)
    architecture_failures, node_count, edge_count = check_architecture()
    failures.extend(architecture_failures)

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1

    print(
        f"Repository docs verified: {len(markdown_files)} Markdown files; "
        f"architecture has {node_count} nodes and {edge_count} directed edges."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
