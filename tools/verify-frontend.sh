#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
expected_node="v$(tr -d '[:space:]' < "$repo_root/.node-version")"

if ! command -v node >/dev/null 2>&1; then
    printf 'Node is required to verify the frontend workspace.\n' >&2
    exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
    printf 'pnpm is required to verify the frontend workspace.\n' >&2
    exit 1
fi

actual_node=$(node --version)
if [ "$actual_node" != "$expected_node" ]; then
    printf 'Expected Node %s from .node-version, found %s.\n' "$expected_node" "$actual_node" >&2
    exit 1
fi

expected_pnpm=$(node -e "const fs = require('node:fs'); const data = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); process.stdout.write(data.packageManager.replace(/^pnpm@/, ''));" "$repo_root/package.json")
actual_pnpm=$(pnpm --version)
if [ "$actual_pnpm" != "$expected_pnpm" ]; then
    printf 'Expected pnpm %s from package.json, found %s.\n' "$expected_pnpm" "$actual_pnpm" >&2
    exit 1
fi

cd "$repo_root"
pnpm install --frozen-lockfile
pnpm run verify

printf 'Frontend workspace verification passed.\n'
