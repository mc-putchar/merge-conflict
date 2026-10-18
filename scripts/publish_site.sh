#!/usr/bin/env bash
# Publish artifacts/site to GitHub Pages on an orphan gh-pages branch.
# Usage: scripts/publish_site.sh [site-dir]   (default: artifacts/site)
# Requires: git, gh (authenticated). Runs real pushes — invoke explicitly.
set -euo pipefail

SITE_DIR="${1:-artifacts/site}"
BRANCH="gh-pages"

if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "error: $SITE_DIR/index.html missing - run 'uv run nemotron-challenge run site' first" >&2
  exit 1
fi

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

tmp=$(mktemp -d)
cleanup() {
  git worktree remove --force "$tmp/wt" 2>/dev/null || true
  rm -rf "$tmp"
}
trap cleanup EXIT

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git worktree add "$tmp/wt" "$BRANCH"
else
  git worktree add --orphan -b "$BRANCH" "$tmp/wt"
fi

# Replace branch contents with the built site
find "$tmp/wt" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$SITE_DIR"/. "$tmp/wt/"
touch "$tmp/wt/.nojekyll"

git -C "$tmp/wt" add -A
if git -C "$tmp/wt" diff --cached --quiet; then
  echo "site unchanged since last publish"
else
  git -C "$tmp/wt" commit -m "Publish challenge site"
fi
git -C "$tmp/wt" push -u origin "$BRANCH"

# Enable Pages on the gh-pages root (idempotent)
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api "repos/$repo/pages" --method POST \
  -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1 || \
gh api "repos/$repo/pages" --method PATCH \
  -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null

url="https://$(echo "$repo" | cut -d/ -f1).github.io/$(echo "$repo" | cut -d/ -f2)/"
echo "Published: $url"
