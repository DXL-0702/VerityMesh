#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
service_root="$repo_root/services/platform-api"

if [ -n "${JAVA_HOME:-}" ]; then
    java_command="$JAVA_HOME/bin/java"
else
    java_command=$(command -v java || true)
fi

if [ -z "$java_command" ] || [ ! -x "$java_command" ]; then
    printf 'Java 21 is required to verify platform-api.\n' >&2
    exit 1
fi

java_specification_version=$(
    "$java_command" -XshowSettings:properties -version 2>&1 \
        | awk -F'= ' '/java.specification.version/ { print $2; exit }'
)

if [ "$java_specification_version" != "21" ]; then
    printf 'Java 21 is required; found Java %s at %s.\n' \
        "$java_specification_version" "$java_command" >&2
    exit 1
fi

(
    cd "$service_root"
    ./mvnw --batch-mode --no-transfer-progress clean verify
)

printf 'Java platform API verification passed.\n'
