#!/usr/bin/env bash
# Image entrypoint. The code lives on GitHub; this clones it fresh each run and
# hands off to the in-repo pipeline, so an ordinary code push changes behaviour
# with no image rebuild. Baked into the container; not run from the clone.
set -euo pipefail

: "${GH_REPO:?set GH_REPO to owner/name}"
: "${GH_TOKEN:?GH_TOKEN must be mounted from Secret Manager}"
REF="${GH_REF:-main}"

work="$(mktemp -d)"
# Token only in the clone URL for this one call; origin is reset to a clean URL
# immediately and a credential helper supplies the token for the later push.
git clone --depth 1 --branch "$REF" \
  "https://x-access-token:${GH_TOKEN}@github.com/${GH_REPO}.git" "$work/repo"
cd "$work/repo"
git remote set-url origin "https://github.com/${GH_REPO}.git"

exec bash deploy/cloudrun/pipeline.sh
