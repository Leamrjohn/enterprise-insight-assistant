#!/usr/bin/env bash
# E4: run import-linter (rules in backend/.importlinter).  Run from backend/.
#
# app/modules and app/utils are namespace packages (no __init__.py), which
# grimp cannot see.  Adding the files for real changes how ruff sorts `app`
# imports in about 100 files, so they exist only while this runs and are
# removed again (docs/worklog.md, E4: pending decision).
set -euo pipefail
created=()
for package in app/modules app/utils; do
  if [ ! -e "$package/__init__.py" ]; then
    touch "$package/__init__.py"
    created+=("$package/__init__.py")
  fi
done
cleanup() { if [ ${#created[@]} -gt 0 ]; then rm -f "${created[@]}"; fi; }
trap cleanup EXIT
lint-imports --no-cache
