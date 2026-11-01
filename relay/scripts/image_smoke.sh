#!/usr/bin/env bash
# Smoke-run the relay image (relay-server task 5.3; design.md "RelayImage and
# RelayWorkflow"; Requirements 9.1, 9.11).
#
#     relay/scripts/image_smoke.sh sqlite|postgres|derived
#
# The image is $FITDOCS_RELAY_IMAGE (default fitdocs-relay:ci), built first with
# `docker build -t fitdocs-relay:ci relay`. Each run migrates, serves detached,
# probes /livez and /readyz, stops the container with SIGTERM (it must exit 0)
# and scans the container's log for the planted secrets. `postgres` starts a
# throwaway PostgreSQL on a private network; `derived` builds a derived image
# by the documented steps and checks the wrapper's route under /x/smoke/.
# Nothing is pushed and nothing logs in to a registry.
set -euo pipefail

MODE="${1:-}"
IMAGE="${FITDOCS_RELAY_IMAGE:-fitdocs-relay:ci}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE_EXTENSION="$HERE/../tests/smoke_extension"

POSTGRES_IMAGE="postgres:17@sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f"
UV_IMAGE="ghcr.io/astral-sh/uv:0.11.24@sha256:99ea34acedc870ba4ad11a1f540a1c04267c9f30aadc465a94406f52dfda2c36"
ENVIRONMENT_PATH="/opt/fitdocs-relay"
USER_ID="10001"
PORT="8080"
EXTENSION_REFERENCE="fitdocs_relay_smoke:EXTENSION"

case "$MODE" in
  sqlite | postgres | derived) ;;
  *)
    echo "usage: image_smoke.sh sqlite|postgres|derived" >&2
    exit 2
    ;;
esac

SUFFIX="$$-$RANDOM"
NAME="fitdocs-relay-smoke-$MODE-$SUFFIX"
DERIVED_TAG="fitdocs-relay-derived:smoke-$SUFFIX"
VOLUME="$NAME-data"
NETWORK="$NAME-net"
PG_NAME="$NAME-pg"
SERVE_NAME="$NAME-serve"

fail() {
  echo "image_smoke[$MODE]: $*" >&2
  exit 1
}

cleanup() {
  docker rm -f "$SERVE_NAME" "$PG_NAME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  docker image rm "$DERIVED_TAG" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# The planted secrets: random per run, handed to the container by variable name
# so they never appear on a command line.
FITDOCS_RELAY_TOKEN_PEPPER="$(docker run --rm "$IMAGE" new-pepper)"
[ "${#FITDOCS_RELAY_TOKEN_PEPPER}" -ge 43 ] || fail "new-pepper printed a short pepper"
DATABASE_PASSWORD="smoke-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
export FITDOCS_RELAY_TOKEN_PEPPER DATABASE_PASSWORD

contains() { # haystack needle
  [[ "$1" == *"$2"* ]]
}
contains "x${DATABASE_PASSWORD}y" "$DATABASE_PASSWORD" || fail "the scan cannot find a planted value"

scan_for_secrets() { # description text
  local planted
  for planted in "$FITDOCS_RELAY_TOKEN_PEPPER" "$DATABASE_PASSWORD"; do
    if contains "$2" "$planted"; then
      fail "a planted secret appears in the $1"
    fi
  done
}

docker network create "$NETWORK" >/dev/null
docker volume create "$VOLUME" >/dev/null

RUN_IMAGE="$IMAGE"
RUN_ARGS=(--network "$NETWORK" -e FITDOCS_RELAY_TOKEN_PEPPER)

case "$MODE" in
  sqlite | derived)
    RUN_ARGS+=(-v "$VOLUME:/data" -e "FITDOCS_RELAY_DATABASE_URL=sqlite:///smoke.db")
    ;;
  postgres)
    FITDOCS_RELAY_DATABASE_PASSWORD="$DATABASE_PASSWORD"
    export FITDOCS_RELAY_DATABASE_PASSWORD
    POSTGRES_PASSWORD="$DATABASE_PASSWORD"
    export POSTGRES_PASSWORD
    docker run -d --name "$PG_NAME" --network "$NETWORK" -e POSTGRES_PASSWORD "$POSTGRES_IMAGE" >/dev/null
    ready=0
    for _ in $(seq 1 60); do
      # TCP, not the socket: the image's initialisation server listens on the
      # socket only, so this answers once the real server is up.
      if docker exec "$PG_NAME" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; then
        ready=1
        break
      fi
      sleep 1
    done
    [ "$ready" = 1 ] || fail "the PostgreSQL container did not become ready"
    RUN_ARGS+=(
      -e FITDOCS_RELAY_DATABASE_PASSWORD
      -e "FITDOCS_RELAY_DATABASE_URL=postgresql://postgres@$PG_NAME:5432/postgres"
    )
    ;;
esac

if [ "$MODE" = derived ]; then
  # The documented derived-image steps: start from the relay image, as root
  # copy in uv and install the wrapper into the relay's environment, return to
  # the non-root user, and leave the entrypoint and command alone.
  docker build -q -t "$DERIVED_TAG" -f - "$SMOKE_EXTENSION" <<DOCKERFILE >/dev/null
FROM $IMAGE
USER root
COPY --from=$UV_IMAGE /uv /bin/uv
COPY . /tmp/wrapper
RUN uv pip install --python $ENVIRONMENT_PATH/bin/python /tmp/wrapper
USER $USER_ID
DOCKERFILE
  RUN_IMAGE="$DERIVED_TAG"
  RUN_ARGS+=(-e "FITDOCS_RELAY_EXTENSIONS=$EXTENSION_REFERENCE")
  derived_user="$(docker image inspect --format '{{.Config.User}}' "$RUN_IMAGE")"
  [ "$derived_user" = "$USER_ID" ] || fail "the derived image runs as '$derived_user'"
fi

if [ "$MODE" = sqlite ]; then
  # The licence directory lists every installed distribution.
  listed="$(docker run --rm --entrypoint ls "$IMAGE" /usr/share/licenses/fitdocs-relay)"
  for dist in fitdocs-relay starlette uvicorn psycopg; do
    printf '%s\n' "$listed" | grep -q "^$dist-" || fail "no licence directory for $dist"
  done
fi

migrate_out="$(docker run --rm "${RUN_ARGS[@]}" "$RUN_IMAGE" migrate 2>&1)" || fail "migrate failed"
scan_for_secrets "migrate output" "$migrate_out"
printf '%s\n' "$migrate_out" | grep -q '^schema ' || fail "migrate printed no schema line: $migrate_out"

docker run -d --name "$SERVE_NAME" -p "127.0.0.1::$PORT" "${RUN_ARGS[@]}" "$RUN_IMAGE" >/dev/null
HOST_PORT="$(docker port "$SERVE_NAME" "$PORT/tcp" | head -n 1 | sed 's/.*://')"
[ -n "$HOST_PORT" ] || fail "no published port"
BASE="http://127.0.0.1:$HOST_PORT"

status_of() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BASE$1" || true
}

wait_for() { # path expected-status
  for _ in $(seq 1 60); do
    [ "$(status_of "$1")" = "$2" ] && return 0
    sleep 0.5
  done
  docker logs "$SERVE_NAME" >&2 || true
  fail "$1 did not answer $2 (last: $(status_of "$1"))"
}

wait_for /livez 200
wait_for /readyz 200
[ "$(status_of /no-such-route)" != 200 ] || fail "an unknown path answered 200"

if [ "$MODE" = derived ]; then
  body="$(curl -s --max-time 5 "$BASE/x/smoke/ping")"
  [ "$body" = "smoke extension answers" ] || fail "the extension route answered '$body'"
fi

docker kill --signal=SIGTERM "$SERVE_NAME" >/dev/null
exit_code="$(docker wait "$SERVE_NAME")"
[ "$exit_code" = 0 ] || fail "SIGTERM ended the container with exit code $exit_code"

LOGS="$(docker logs "$SERVE_NAME" 2>&1)"
[ -n "$LOGS" ] || fail "the container logged nothing, so the secret scan would be vacuous"
scan_for_secrets "container log" "$LOGS"

echo "image_smoke[$MODE]: ok"
