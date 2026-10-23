"""Scan the files agents read as instructions for remote execution, hidden Unicode, and unlisted URLs.

Usage: scan_instructions.py [path ...]
With no paths it scans the default instruction set from the repository root.
"""

import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = Path(__file__).with_name("instruction_allowlist.txt")

DEFAULT_GLOBS = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/**/*",
    "docs/*.md",
    "docs/adr/*.md",
    "scripts/*.sh",
    "cases/*.json",
    ".github/workflows/*.yml",
    "backend/agents/prompts/*.txt",
)

_FETCH = r"(curl|wget)\b"
_SHELL = r"(sudo\s+)?(ba|z|da|k)?sh\b"
_PS_FETCH = r"(iwr|irm|invoke-webrequest|invoke-restmethod|downloadstring|https?://)"

REMOTE_EXEC = (
    re.compile(rf"{_FETCH}[^|\n]*\|\s*{_SHELL}"),
    re.compile(rf"{_SHELL}\s+<\(\s*{_FETCH}"),
    re.compile(rf"\b(iex|invoke-expression)\b.*{_PS_FETCH}", re.IGNORECASE),
    re.compile(rf"{_PS_FETCH}.*\|\s*(iex|invoke-expression)\b", re.IGNORECASE),
    re.compile(r"\.downloadstring\s*\(", re.IGNORECASE),
    re.compile(rf"\beval\b.*(\$\(|`)\s*{_FETCH}"),
    re.compile(r"\bpython3?\s+-c\b.*(urllib|urlopen|requests\.get|https?://)"),
)

INVISIBLE = re.compile("[​-‍⁠﻿‪-‮⁦-⁩\U000e0000-\U000e007f]")

URL = re.compile(r"https?://([A-Za-z0-9.-]+)")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def allowed_hosts(path: Path = ALLOWLIST) -> frozenset[str]:
    lines = (line.split("#", 1)[0].strip() for line in path.read_text().splitlines())
    return frozenset(line.lower() for line in lines if line)


def default_paths(root: Path = ROOT) -> list[Path]:
    found = {p for pattern in DEFAULT_GLOBS for p in root.glob(pattern) if p.is_file()}
    return sorted(found)


def scan_text(name: str, text: str, hosts: frozenset[str]) -> Iterator[Finding]:
    for number, line in enumerate(text.splitlines(), start=1):
        if any(pattern.search(line) for pattern in REMOTE_EXEC):
            yield Finding(name, number, "remote_exec", line.strip()[:120])
        body = line[1:] if number == 1 and line.startswith("﻿") else line
        hidden = INVISIBLE.findall(body)
        if hidden:
            detail = f"{len(hidden)} hidden, first U+{ord(hidden[0]):04X}"
            yield Finding(name, number, "invisible_unicode", detail)
        for host in URL.findall(line):
            if host.lower() not in hosts:
                yield Finding(name, number, "unlisted_url", host)


def scan(paths: Iterable[Path], hosts: frozenset[str] | None = None) -> list[Finding]:
    hosts = allowed_hosts() if hosts is None else hosts
    findings: list[Finding] = []
    for path in paths:
        name = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        findings += scan_text(name, path.read_text(encoding="utf-8"), hosts)
    return findings


def main(argv: list[str]) -> int:
    paths = [Path(arg).resolve() for arg in argv] or default_paths()
    findings = scan(paths)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL {len(findings)} findings in {len(paths)} files")
        return 1
    print(f"OK 0 findings in {len(paths)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
