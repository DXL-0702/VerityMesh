#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/veritymesh-verify.XXXXXX")

cleanup() {
    rm -rf "$temp_dir"
}
trap cleanup EXIT HUP INT TERM

if ! command -v uv >/dev/null 2>&1; then
    printf 'uv is required to verify this repository.\n' >&2
    exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
export UV_NO_PROGRESS=1

uv run --no-project --offline --no-cache \
    python3 "$repo_root/tools/check_repository.py"

uv run --frozen --directory "$repo_root/services/batch-worker" \
    alembic upgrade head --sql >/dev/null

uv run --frozen --directory "$repo_root" \
    pytest services/batch-worker/tests/test_source_revision_contract.py -q

(
    cd "$repo_root/tools/text-retrieval-poc"
    PYTHONPATH=src uv run --no-project --offline --no-cache \
        python3 -m unittest discover -s tests -v
)

uv run --no-project --offline --no-cache \
    python3 "$repo_root/tools/text-retrieval-poc/run_poc.py" local-validate \
    --output "$temp_dir/text-retrieval-local-contract"

printf 'Repository verification passed.\n'
