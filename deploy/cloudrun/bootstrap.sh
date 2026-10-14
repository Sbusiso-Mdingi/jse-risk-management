#!/usr/bin/env bash
set -euo pipefail
: "${GH_REPO:?set GH_REPO to owner/name}"
REF="${GH_REF:-main}"
install -m 600 /secrets/deploy_key /tmp/deploy_key
export GIT_SSH_COMMAND="ssh -i /tmp/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
work="$(mktemp -d)"
git clone --depth 1 --branch "$REF" "git@github.com:${GH_REPO}.git" "$work/repo"
cd "$work/repo"
exec bash deploy/cloudrun/pipeline.sh
