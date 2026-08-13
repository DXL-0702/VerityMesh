#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$repo_root/infra/local/compose.yaml"

if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker CLI is required for local integration verification.\n' >&2
    exit 1
fi

docker compose -f "$compose_file" config --quiet

if ! docker info >/dev/null 2>&1; then
    printf 'Docker CLI is available, but the Docker daemon is not reachable.\n' >&2
    printf 'Start the local Docker/OrbStack daemon, then rerun this script.\n' >&2
    exit 2
fi

compose() {
    docker compose -f "$compose_file" "$@"
}

wait_for_health() {
    service=$1
    attempts=60
    container_id=''
    while [ "$attempts" -gt 0 ]; do
        container_id=$(compose ps -q "$service")
        if [ -n "$container_id" ]; then
            health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
            if [ "$health" = healthy ]; then
                return 0
            fi
        fi
        attempts=$((attempts - 1))
        sleep 2
    done
    printf 'Service %s did not become healthy.\n' "$service" >&2
    compose ps >&2
    return 1
}

compose up -d mysql postgres kafka redis-online redis-celery elasticsearch object-storage

for service in mysql postgres kafka redis-online redis-celery elasticsearch object-storage; do
    wait_for_health "$service"
done

compose run --rm platform-api-migration
compose run --rm batch-worker-migration

# A second execution proves that the jobs are restartable and idempotent.
compose run --rm platform-api-migration
compose run --rm batch-worker-migration

mysql_container=$(compose ps -q mysql)
postgres_container=$(compose ps -q postgres)

docker exec "$mysql_container" mysql \
    --protocol=tcp -h 127.0.0.1 -u veritymesh_app -pveritymesh-app-local \
    -e 'SELECT COUNT(*) AS projects FROM veritymesh.projects;' >/dev/null

if docker exec "$mysql_container" mysql \
    --protocol=tcp -h 127.0.0.1 -u veritymesh_app -pveritymesh-app-local \
    -e 'CREATE TABLE veritymesh._local_app_ddl_probe (id INT);' >/dev/null 2>&1; then
    printf 'MySQL application identity unexpectedly has DDL privileges.\n' >&2
    exit 1
fi

docker exec -e PGPASSWORD=veritymesh-app-local "$postgres_container" psql \
    -h 127.0.0.1 -U veritymesh_app -d veritymesh -v ON_ERROR_STOP=1 \
    -w \
    -c 'SELECT COUNT(*) AS projection_builds FROM projection_builds;' >/dev/null

if docker exec -e PGPASSWORD=veritymesh-app-local "$postgres_container" psql \
    -h 127.0.0.1 -U veritymesh_app -d veritymesh -v ON_ERROR_STOP=1 \
    -w \
    -c 'CREATE TABLE public._local_app_ddl_probe (id integer);' >/dev/null 2>&1; then
    printf 'PostgreSQL application identity unexpectedly has DDL privileges.\n' >&2
    exit 1
fi

printf 'Local integration environment and independent migration jobs passed.\n'
