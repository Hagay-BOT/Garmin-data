#!/usr/bin/env bash
# git_sync.sh — robust commit + push for all coach workflows.
#
# Usage:  scripts/git_sync.sh "commit message" file1 [file2 ...]
#
# Replaces the fragile per-workflow pattern that caused state loss:
#   * `git add a b c` is ATOMIC — one missing path aborts the whole add, so
#     nothing gets staged and the run's state/reports never persist.
#   * unconditional `git pull --rebase` fails with "cannot pull with rebase:
#     you have unstaged changes" when files were modified but not staged.
#   * `git push || true` hides real failures, so lost state looks like success.
#
# This script:
#   1. stages ONLY existing paths (missing file ≠ fatal).
#   2. commits ONLY if something is actually staged.
#   3. pulls --rebase --autostash (survives stray unstaged changes), then pushes,
#      retrying on the inevitable race between concurrent workflows.
#   4. exits non-zero if it ultimately cannot push — failures stay VISIBLE.
set -uo pipefail

MSG="${1:?git_sync: commit message required}"
shift || true

git config user.name  "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

staged=0
for f in "$@"; do
  if [ -e "$f" ]; then
    git add "$f" && staged=1
  fi
done

if [ "$staged" -eq 0 ] || git diff --staged --quiet; then
  echo "git_sync: no changes to commit"
  exit 0
fi

git commit -m "$MSG"

for attempt in 1 2 3 4 5; do
  # -X theirs auto-resolves CONTENT conflicts in favor of our just-committed
  # version. These workflows only commit GENERATED/state files (data.json,
  # reports, *_state.json) — both sides are valid Garmin snapshots, so taking
  # ours lets the rebase COMPLETE instead of halting on a conflict (the failure
  # mode that broke update.yml: same conflict retried 5× → exit 1).
  if git pull --rebase --autostash -X theirs origin main && git push origin main; then
    echo "git_sync: pushed on attempt $attempt"
    exit 0
  fi
  echo "git_sync: attempt $attempt failed (likely a concurrent push) — retrying"
  git rebase --abort 2>/dev/null || true
  sleep $((attempt * 3))
done

echo "git_sync: FAILED to push after 5 attempts" >&2
exit 1
