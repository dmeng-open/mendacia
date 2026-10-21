#!/bin/bash
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then exit 0; fi
cd "$CLAUDE_PROJECT_DIR" || exit 1
[ -f package-lock.json ] && npm ci
service postgresql start || true
exit 0