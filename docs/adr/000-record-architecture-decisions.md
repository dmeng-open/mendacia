# 000. Record architecture decisions

## Status

Accepted.

## Context

Design decisions made while building Mendacia need a durable, reviewable record, so later contributors and agents can see why the code is shaped as it is.

## Decision

Each design decision gets one Markdown file in `docs/adr/`, named `NNN-short-title.md`, with Status, Context, Decision, and Consequences sections. A decision that changes an earlier one supersedes it in a new record and updates the old record's status.

## Consequences

Changing the `Case` schema after Phase 1, adding a model-boundary rule, or any other cross-cutting choice ships with an ADR in the same PR.
