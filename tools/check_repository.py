#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_RELATIVE = Path("docs/architecture.md")
ARCHITECTURE = ROOT / ARCHITECTURE_RELATIVE
REQUIRED_PATHS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path(".github/workflows/verify.yml"),
    Path(".java-version"),
    Path(".node-version"),
    Path(".npmrc"),
    Path(".python-version"),
    Path("package.json"),
    Path("pnpm-workspace.yaml"),
    Path("pnpm-lock.yaml"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("tsconfig.base.json"),
    Path("eslint.config.mjs"),
    Path("prettier.config.mjs"),
    Path("apps/portal-web/package.json"),
    Path("apps/portal-web/README.md"),
    Path("services/platform-api/README.md"),
    Path("services/platform-api/.mvn/wrapper/maven-wrapper.properties"),
    Path("services/platform-api/mvnw"),
    Path("services/platform-api/mvnw.cmd"),
    Path("services/platform-api/pom.xml"),
    Path("services/platform-api/src/main/java/com/veritymesh/platform/PlatformApiApplication.java"),
    Path("services/platform-api/src/main/resources/application.properties"),
    Path("services/platform-api/src/test/java/com/veritymesh/platform/PlatformApiToolchainTests.java"),
    Path("services/assistant-runtime/pyproject.toml"),
    Path("services/assistant-runtime/README.md"),
    Path("services/batch-worker/pyproject.toml"),
    Path("services/batch-worker/README.md"),
    Path("packages/assistant-ui/package.json"),
    Path("packages/assistant-ui/README.md"),
    Path("packages/typescript-client/package.json"),
    Path("packages/typescript-client/README.md"),
    Path("contracts/README.md"),
    Path("contracts/internal/v1/project-execution-context.schema.json"),
    Path("contracts/internal/v1/examples/project-execution-context.valid.json"),
    Path("infra/README.md"),
    Path("tests/README.md"),
    Path("docs/README.md"),
    Path("docs/tech-plan.md"),
    ARCHITECTURE_RELATIVE,
    Path("docs/adr/README.md"),
    Path("docs/implementation-designs/README.md"),
    Path("docs/technology-selection/technology-selection.md"),
    Path("docs/poc-reports/README.md"),
    Path("docs/runbooks/README.md"),
    Path("tools/verify-repository.sh"),
    Path("tools/verify-frontend.sh"),
    Path("tools/verify-java.sh"),
    Path("tools/verify-python.sh"),
)
LEGACY_DOCUMENT_PATHS = (
    Path("architecture.md"),
    Path("tech-plan.md"),
    Path("adr"),
    Path("implementation-designs"),
    Path("technology-selection"),
    Path("poc-reports"),
    Path("runbooks"),
)
FORBIDDEN_BUILD_PATHS = (
    Path(".mvn"),
    Path("gradle"),
    Path("gradlew"),
    Path("gradlew.bat"),
    Path("mvnw"),
    Path("mvnw.cmd"),
    Path("pom.xml"),
    Path("build.gradle"),
    Path("build.gradle.kts"),
    Path("settings.gradle"),
    Path("settings.gradle.kts"),
    Path("services/platform-api/gradle"),
    Path("services/platform-api/gradlew"),
    Path("services/platform-api/gradlew.bat"),
    Path("services/platform-api/build.gradle"),
    Path("services/platform-api/build.gradle.kts"),
    Path("services/platform-api/settings.gradle"),
    Path("services/platform-api/settings.gradle.kts"),
)
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
    paths = {ROOT / line for line in result.stdout.splitlines() if line}
    return sorted(path for path in paths if path.is_file())


def check_repository_layout() -> list[str]:
    failures = [
        f"missing required repository path: {path.as_posix()}"
        for path in REQUIRED_PATHS
        if not (ROOT / path).exists()
    ]
    failures.extend(
        f"legacy documentation path must move under docs/: {path.as_posix()}"
        for path in LEGACY_DOCUMENT_PATHS
        if (ROOT / path).exists()
    )
    failures.extend(
        f"unsupported root or Gradle build path: {path.as_posix()}"
        for path in FORBIDDEN_BUILD_PATHS
        if (ROOT / path).exists()
    )

    wrapper = ROOT / "services/platform-api/mvnw"
    if wrapper.exists() and not wrapper.stat().st_mode & 0o111:
        failures.append("services/platform-api/mvnw must be executable")

    java_version = ROOT / ".java-version"
    if java_version.exists() and java_version.read_text(encoding="utf-8").strip() != "21.0.12":
        failures.append(".java-version must pin the accepted 21.0.12 baseline")

    return failures


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
    architecture_label = ARCHITECTURE_RELATIVE.as_posix()
    if not ARCHITECTURE.is_file():
        return [f"{architecture_label}: file does not exist"], 0, 0

    content = ARCHITECTURE.read_text(encoding="utf-8")
    blocks = list(MERMAID_BLOCK.finditer(content))
    if len(blocks) != 1:
        return [f"{architecture_label}: expected one Mermaid block, found {len(blocks)}"], 0, 0

    body = blocks[0].group("body")
    if "React" in body:
        failures.append(
            f"{architecture_label}: React is outside the frozen first-stage boundary"
        )

    declarations: dict[str, int] = defaultdict(int)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    edge_count = 0

    for line_number, line in enumerate(body.splitlines(), start=1):
        declaration = NODE_DECLARATION.match(line)
        if declaration:
            declarations[declaration.group(1)] += 1

        if "---" in line and "-->" not in line:
            failures.append(
                f"{architecture_label} Mermaid line {line_number}: undirected edge is forbidden"
            )

        if "-->" not in line and "-.->" not in line:
            continue
        edge = DIRECTED_EDGE.match(line)
        if edge is None:
            failures.append(
                f"{architecture_label} Mermaid line {line_number}: unsupported edge syntax"
            )
            continue
        source, target = edge.groups()
        outgoing[source].add(target)
        incoming[target].add(source)
        edge_count += 1

    duplicates = sorted(node for node, count in declarations.items() if count > 1)
    if duplicates:
        failures.append(
            f"{architecture_label}: duplicate node declarations: {', '.join(duplicates)}"
        )

    referenced = set(outgoing) | set(incoming)
    missing = sorted(referenced - set(declarations))
    if missing:
        failures.append(
            f"{architecture_label}: undeclared edge endpoints: {', '.join(missing)}"
        )

    for required in ("user", "userResult"):
        if required not in declarations:
            failures.append(f"{architecture_label}: missing required flow endpoint {required}")

    if "user" in declarations:
        unreachable = sorted(set(declarations) - walk("user", outgoing))
        if unreachable:
            failures.append(
                f"{architecture_label}: unreachable from user: {', '.join(unreachable)}"
            )

    if "userResult" in declarations:
        cannot_finish = sorted(set(declarations) - walk("userResult", incoming))
        if cannot_finish:
            failures.append(
                f"{architecture_label}: cannot reach userResult: {', '.join(cannot_finish)}"
            )

    return failures, len(declarations), edge_count


def main() -> int:
    if sys.version_info < (3, 11):
        print("repository checks require Python 3.11 or newer", file=sys.stderr)
        return 1

    markdown_files = repository_markdown_files()
    failures = check_repository_layout()
    failures.extend(check_markdown_links(markdown_files))
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
