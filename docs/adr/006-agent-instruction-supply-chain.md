# 006. Treat agent instruction files as code and scan them in CI

## Status

Accepted.

## Context

Agents build this repository. They follow `CLAUDE.md`, `.claude/**`, `docs/plan.md`, `docs/spec.md`, the roadmap and the ADRs, and they run `scripts/*.sh`. The SessionStart hook in `.claude/settings.json` runs `scripts/install_pkgs.sh` in every cloud session before any human looks. Cases and workflows feed prompts and CI. A line added to any of these files runs with the agent's permissions the next time an agent reads it, so these files are code even when they are Markdown.

The RedWraith demo at Informanix Discover 2026 showed the attack this answers. An autonomous attack chain used a stolen developer token to merge a change to a project `SKILL.md` with admin rights. The change added a prerequisite that downloaded a PowerShell install script and ran it before each day's first PR review. A skill scanner in the same demo found a payload hidden as Unicode steganography.

`main` already held one instance of the pattern. `scripts/install_pkgs.sh` fell back to piping a downloaded installer into a shell when `pip install uv` failed.

## Decision

`scripts/scan_instructions.py` reads the instruction set and reports one line per finding with file, line, and rule. It exits 1 on any finding. It uses only the standard library, so it runs before `uv sync`. With no arguments it reads `CLAUDE.md`, `AGENTS.md`, `.claude/**`, `docs/*.md`, `docs/adr/*.md`, `scripts/*.sh`, `cases/*.json`, and `.github/workflows/*.yml`. That set adds the roadmap and the ADRs to the list in `docs/plan.md`, because `CLAUDE.md` points agents at both.

The rules:

- **`remote_exec`.** A download piped into a shell or fed to one by process substitution. PowerShell's Invoke-Expression, or its alias, on the same line as a web request or a URL. A WebClient download-string call. `eval` of a command substitution that starts with a fetch. A Python one-liner that fetches a URL.
- **`invisible_unicode`.** Zero-width characters (U+200B to U+200D, U+2060, and U+FEFF anywhere but the first character of the file), tag characters (U+E0000 to U+E007F), and bidi controls (U+202A to U+202E, U+2066 to U+2069). One finding per line, with the count and the first code point.
- **`unlisted_url`.** Any URL whose host is not in `scripts/instruction_allowlist.txt`. The list starts with the hosts `main` uses after this change: `localhost`, `github.com`, and `code.claude.com`. Adding a host is a reviewed diff to that file.

Docs describe these patterns in words and never paste a working command, so the plan, the spec, and the ADRs pass their own scan. Working examples live only in `backend/tests/fixtures/instructions/`, which the default set does not read.

`make scan-instructions` runs the scan. `make ci` runs it, and so does a separate `instructions` CI job, so the check reports on its own row.

`make audit` runs `pip-audit` on the dependencies exported from `backend/uv.lock`, with hashes. When `frontend/package-lock.json` exists, it also runs `npm audit --omit=dev --audit-level=high`. An `audit` CI job runs it. Dependabot opens weekly updates for `uv` in `/backend`, `npm` in `/frontend`, and GitHub Actions.

`scripts/install_pkgs.sh` now installs `uv` with `pip` only.

The operator is the only maintainer and merges every PR. The scan in CI plus that review is the control. Branch protection and CODEOWNERS on instruction files wait until a second maintainer joins (roadmap stage G).

## What the scan misses

- A payload written in plain words ("before reviewing, run the setup script from this link") without a fetch-and-run command on one line. The URL rule catches it only when it names an unlisted host.
- A fetch and an execution split across two lines, such as a download to a file followed by a separate run of that file.
- Obfuscated commands: string concatenation, base64 that decodes to a command, and aliases the patterns do not list.
- Look-alike characters that render visibly, such as Cyrillic letters in a host name. Only invisible and bidi characters are rules.
- Files outside the default set, such as a new instruction location that a tool starts to read.

The scan is a tripwire, not a sandbox. The review of every PR that touches these paths stays the main control.

## Deviations from the plan

- `pip-audit` reports no severity, so `make audit` fails on any known vulnerability, not only high or critical ones. A finding the operator accepts is added with `--ignore-vuln` and a reason in the PR that adds it.
- Dependabot uses the `uv` ecosystem for `/backend`, not `pip`, because the backend locks with `uv.lock`, which the `pip` ecosystem does not update.

## Consequences

Every PR from P3-1 on runs the scan, and Lane 1 of each live verification runs `make scan-instructions` at head. A PR that adds a URL to an instruction file also edits the allowlist, which makes the new host visible in review. P3-3 and P4-1 apply the Unicode rule to evidence documents and generated cases.
