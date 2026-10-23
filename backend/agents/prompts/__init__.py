from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template

DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    sections: dict[str, Template]

    def render(self, section: str, **values: object) -> str:
        return self.sections[section].substitute(values)


@cache
def load(name: str) -> Prompt:
    header, _, body = (DIR / f"{name}.txt").read_text().partition("\n")
    key, _, version = header.partition(":")
    if key != "prompt_version" or not version.strip():
        raise ValueError(f"{name}.txt must start with 'prompt_version: <version>'")
    sections: dict[str, list[str]] = {}
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("@@ "):
            lines = sections.setdefault(line[3:].strip(), [])
        else:
            lines.append(line)
    templates = {k: Template("\n".join(v).strip("\n")) for k, v in sections.items()}
    return Prompt(name, version.strip(), templates)
