"""Static conformance for the relay image (relay-server task 5.3; design.md
"RelayImage and RelayWorkflow"; Requirements 9.1, 9.11).

The Dockerfile is parsed, never built here: each rule of the image is a finding
function over its text; the real file yields no findings and the mutated copies
named in the tests yield the message of the rule they break. The smoke
script's code from `set -euo pipefail` to its end is pinned as one literal, and
the licence script by fixtures. The
built image itself is exercised only by `scripts/image_smoke.sh`, in CI and by
hand.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import PathDistribution, distributions
from pathlib import Path

import pytest

from fitdocs_relay.contract import (
    ENV_DATABASE_URL,
    ENV_HOST,
    ENVIRONMENT,
    IMAGE_DEFAULT_COMMAND,
    IMAGE_ENTRYPOINT,
    IMAGE_ENVIRONMENT,
    IMAGE_PORT,
    IMAGE_USER_ID,
)

RELAY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = RELAY_ROOT.parent
DOCKERFILE = RELAY_ROOT / "Dockerfile"
DOCKERIGNORE = RELAY_ROOT / ".dockerignore"
SMOKE_SCRIPT = RELAY_ROOT / "scripts" / "image_smoke.sh"
LICENCE_SCRIPT = RELAY_ROOT / "scripts" / "collect_licences.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "relay.yml"

LICENCE_DIRECTORY = "/usr/share/licenses/fitdocs-relay"
DATA_DIRECTORY = "/data"
PYTHON_BASE = "python:3.12-slim-bookworm"
UV_IMAGE = "ghcr.io/astral-sh/uv"
DIGEST_VALUE = r"[0-9a-f]{64}"
DIGEST = r"@sha256:" + DIGEST_VALUE


@dataclass(frozen=True)
class Instruction:
    stage: int
    keyword: str
    argument: str


def parse(text: str) -> list[Instruction]:
    """The Dockerfile's instructions, comments dropped and continuations joined."""
    logical: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        logical.append((pending + line).strip())
        pending = ""
    assert not pending, "the file ends inside a continuation"
    found: list[Instruction] = []
    stage = -1
    for entry in logical:
        keyword, _, argument = entry.partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            stage += 1
        found.append(Instruction(stage, keyword, argument.strip()))
    return found


def _env_pairs(argument: str) -> dict[str, str]:
    """`ENV` arguments in the `KEY=value KEY2=value2` form (the only one used)."""
    pairs: dict[str, str] = {}
    for token in argument.split():
        key, separator, value = token.partition("=")
        if separator:
            pairs[key] = value
    return pairs


def _json_list(argument: str) -> list[str] | None:
    try:
        value = json.loads(argument)
    except json.JSONDecodeError:
        return None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None


_SECRET_WORDS = re.compile(
    r"(secret|password|passwd|token|pepper|key|credential)", re.I
)
_DATABASE_FILE = re.compile(r"\.(db|sqlite3?)(-wal|-shm)?\b|\.serve-lock", re.I)


def findings(text: str) -> list[str]:
    """Every way `text` departs from the image's rules; empty when it conforms."""
    problems: list[str] = []
    instructions = parse(text)
    if not instructions:
        return ["the Dockerfile has no instructions"]
    froms = [i for i in instructions if i.keyword == "FROM"]
    if len(froms) != 2:
        problems.append(f"expected two stages, found {len(froms)}")
        return problems
    for stage in froms:
        image = stage.argument.split()[0]
        if not re.fullmatch(re.escape(PYTHON_BASE) + DIGEST, image):
            problems.append(
                f"stage {stage.stage} base {image!r} is not the slim Python by digest"
            )
    build = [i for i in instructions if i.stage == 0]
    runtime = [i for i in instructions if i.stage == 1]

    # --- build stage ---------------------------------------------------------
    uv_copies = [
        i
        for i in build
        if i.keyword == "COPY" and i.argument.startswith("--from=" + UV_IMAGE)
    ]
    if len(uv_copies) != 1 or not re.match(
        r"--from=" + re.escape(UV_IMAGE) + r":[0-9][0-9.]*" + DIGEST + r"\s",
        uv_copies[0].argument + " ",
    ):
        problems.append(
            "the build stage does not take uv from the uv image pinned by digest"
        )
    for i in instructions:
        if i.keyword == "COPY" and i.argument.startswith("--from="):
            source = i.argument.split()[0].removeprefix("--from=")
            if source not in ("build",) and not re.search(DIGEST + "$", source):
                problems.append(
                    f"COPY --from={source} is neither a stage nor pinned by digest"
                )
    build_env: dict[str, str] = {}
    for i in build:
        if i.keyword == "ENV":
            build_env.update(_env_pairs(i.argument))
    if build_env.get("UV_PROJECT_ENVIRONMENT") != IMAGE_ENVIRONMENT:
        problems.append(
            "the build environment path is not the contract's IMAGE_ENVIRONMENT"
        )
    syncs = [
        i.argument for i in build if i.keyword == "RUN" and "uv sync" in i.argument
    ]
    wanted = ("--locked", "--no-dev", "--extra postgres", "--no-editable")
    if len(syncs) != 1 or not all(flag in syncs[0] for flag in wanted):
        problems.append("the build stage lacks the locked non-dev postgres sync")
    collect = [
        i.argument
        for i in build
        if i.keyword == "RUN" and "scripts/collect_licences.py" in i.argument
    ]
    expected_collect = (
        f"{IMAGE_ENVIRONMENT}/bin/python scripts/collect_licences.py "
        f"{LICENCE_DIRECTORY}"
    )
    if collect != [expected_collect]:
        problems.append("the licence script is not run with the environment's python")

    # --- runtime stage -------------------------------------------------------
    copies = [i.argument.split() for i in runtime if i.keyword == "COPY"]
    if ["--from=build", IMAGE_ENVIRONMENT, IMAGE_ENVIRONMENT] not in copies:
        problems.append(
            "the runtime stage does not copy the environment to the same path"
        )
    if ["--from=build", LICENCE_DIRECTORY, LICENCE_DIRECTORY] not in copies:
        problems.append("the runtime stage does not copy the licence texts")
    runtime_env: dict[str, str] = {}
    for i in runtime:
        if i.keyword == "ENV":
            runtime_env.update(_env_pairs(i.argument))
    if not runtime_env.get("PATH", "").startswith(IMAGE_ENVIRONMENT + "/bin:"):
        problems.append("the environment's bin is not first on PATH")
    if runtime_env.get(ENV_HOST) != "0.0.0.0":
        problems.append("the listen address is not set for containers")
    exposed = [i.argument for i in runtime if i.keyword == "EXPOSE"]
    if exposed != [str(IMAGE_PORT)]:
        problems.append(f"EXPOSE is {exposed}, not the contract's port")
    users = [i.argument for i in runtime if i.keyword == "USER"]
    if users != [str(IMAGE_USER_ID)]:
        problems.append(f"USER is {users}, not the numeric contract user")
    elif runtime.index(next(i for i in runtime if i.keyword == "USER")) < max(
        (n for n, i in enumerate(runtime) if i.keyword == "RUN"), default=-1
    ):
        problems.append("a RUN follows USER")
    owned_command = (
        f"install -d -o {IMAGE_USER_ID} -g {IMAGE_USER_ID} -m 0700 {DATA_DIRECTORY}"
    )
    owned = [
        segment
        for i in runtime
        if i.keyword == "RUN"
        for segment in (part.strip() for part in i.argument.split("&&"))
        if segment == owned_command
    ]
    if len(owned) != 1:
        problems.append("the runtime stage does not create the owned data directory")
    others = [
        segment
        for i in runtime
        if i.keyword == "RUN"
        for segment in (part.strip() for part in i.argument.split("&&"))
        if DATA_DIRECTORY in segment and segment != owned_command
    ]
    if others:
        problems.append(f"another command touches the data directory: {others}")
    creates_user = [
        i.argument
        for i in runtime
        if i.keyword == "RUN" and f"useradd --uid {IMAGE_USER_ID}" in i.argument
    ]
    if len(creates_user) != 1:
        problems.append("the runtime stage does not create the contract user")
    entrypoints = [_json_list(i.argument) for i in runtime if i.keyword == "ENTRYPOINT"]
    if entrypoints != [list(IMAGE_ENTRYPOINT)]:
        problems.append(f"ENTRYPOINT is {entrypoints}, not the contract's")
    commands = [_json_list(i.argument) for i in runtime if i.keyword == "CMD"]
    if commands != [list(IMAGE_DEFAULT_COMMAND)]:
        problems.append(f"CMD is {commands}, not the contract's")

    # --- nothing that does not belong ---------------------------------------
    secret_names = [v.name for v in ENVIRONMENT if v.secret]
    for i in instructions:
        if i.keyword == "VOLUME":
            problems.append("the image declares a volume")
        for name in secret_names:
            if name in i.argument:
                problems.append(f"{i.keyword} names the secret variable {name}")
        if i.keyword in ("ENV", "ARG"):
            names = list(_env_pairs(i.argument)) or [i.argument.split("=")[0]]
            for name in names:
                if _SECRET_WORDS.search(name):
                    problems.append(f"{i.keyword} {name} looks like a secret")
                if name.startswith("FITDOCS_RELAY_") and name != ENV_HOST:
                    problems.append(
                        f"{i.keyword} {name} sets contract state the operator owns"
                    )
    for i in instructions:
        if i.keyword in ("COPY", "ADD", "RUN") and _DATABASE_FILE.search(i.argument):
            problems.append(f"{i.keyword} {i.argument!r} handles a database file")
    return problems


def _dockerfile() -> str:
    assert DOCKERFILE.is_file(), "relay/Dockerfile does not exist"
    return DOCKERFILE.read_text(encoding="utf-8")


def _mutated(old: str, new: str) -> str:
    text = _dockerfile()
    assert text.count(old) >= 1, f"anchor {old!r} is not in the Dockerfile"
    return text.replace(old, new)


def test_the_dockerfile_conforms_to_every_rule() -> None:
    assert findings(_dockerfile()) == []


def test_the_parser_sees_both_stages_and_their_instructions() -> None:
    instructions = parse(_dockerfile())
    assert {i.stage for i in instructions} == {0, 1}
    assert [i.keyword for i in instructions if i.keyword in ("ENTRYPOINT", "CMD")] == [
        "ENTRYPOINT",
        "CMD",
    ]
    assert len(instructions) >= 15


def test_the_contract_values_the_rules_are_checked_against() -> None:
    # Literals, so a contract drift cannot move the image and its test together.
    assert IMAGE_USER_ID == 10001
    assert IMAGE_PORT == 8080
    assert IMAGE_ENVIRONMENT == "/opt/fitdocs-relay"
    assert IMAGE_ENTRYPOINT == ("fitdocs-relay",)
    assert IMAGE_DEFAULT_COMMAND == ("serve",)


# --- mutations: each rule must be able to fail ------------------------------

_DIGEST_LITERAL = re.compile(r"(FROM python:3\.12-slim-bookworm)@sha256:[0-9a-f]{64}")


def test_a_tag_only_base_is_refused() -> None:
    text = _DIGEST_LITERAL.sub(r"\1", _dockerfile())
    assert text != _dockerfile()
    assert any("slim Python by digest" in p for p in findings(text))


def test_a_floating_uv_image_is_refused() -> None:
    text = re.sub(r"(ghcr\.io/astral-sh/uv:[0-9.]+)" + DIGEST, r"\1", _dockerfile())
    assert text != _dockerfile()
    assert any("uv image pinned by digest" in p for p in findings(text))


def test_a_root_user_is_refused() -> None:
    assert any("USER" in p for p in findings(_mutated("USER 10001", "USER root")))
    assert any("USER" in p for p in findings(_mutated("USER 10001", "USER relay")))
    assert any("USER" in p for p in findings(_mutated("USER 10001\n", "")))


def test_an_environment_path_other_than_the_contracts_is_refused() -> None:
    build_moved = _mutated(
        "UV_PROJECT_ENVIRONMENT=/opt/fitdocs-relay", "UV_PROJECT_ENVIRONMENT=/opt/relay"
    )
    assert any("build environment path" in p for p in findings(build_moved))
    runtime_moved = _mutated(
        "COPY --from=build /opt/fitdocs-relay /opt/fitdocs-relay",
        "COPY --from=build /opt/fitdocs-relay /opt/relay",
    )
    assert any("same path" in p for p in findings(runtime_moved))
    path_moved = _mutated(
        "PATH=/opt/fitdocs-relay/bin:$PATH", "PATH=/opt/relay/bin:$PATH"
    )
    assert any("PATH" in p for p in findings(path_moved))


def _messages(text: str) -> list[str]:
    return findings(text)


def test_a_volume_is_refused() -> None:
    assert "the image declares a volume" in _messages(_dockerfile() + "VOLUME /data\n")


def test_a_secret_contract_variable_is_refused_by_name() -> None:
    for name in ("FITDOCS_RELAY_DATABASE_URL", "FITDOCS_RELAY_TOKEN_PEPPER"):
        found = _messages(_dockerfile() + f"ENV {name}=x\n")
        assert f"ENV names the secret variable {name}" in found, name
    url = _messages(
        _dockerfile() + "ENV FITDOCS_RELAY_DATABASE_URL=sqlite:////data/x.db\n"
    )
    assert "ENV names the secret variable FITDOCS_RELAY_DATABASE_URL" in url
    assert "ARG names the secret variable FITDOCS_RELAY_DATABASE_PASSWORD" in _messages(
        _dockerfile() + "ARG FITDOCS_RELAY_DATABASE_PASSWORD\n"
    )


def test_the_secret_variables_the_image_must_not_name_are_the_contracts_six() -> None:
    assert [v.name for v in ENVIRONMENT if v.secret] == [
        "FITDOCS_RELAY_DATABASE_URL",
        "FITDOCS_RELAY_DATABASE_PASSWORD",
        "FITDOCS_RELAY_TOKEN_PEPPER",
        "FITDOCS_RELAY_ENCRYPTION_KEYS",
        "FITDOCS_RELAY_STRAVA_CLIENT_SECRET",
        "FITDOCS_RELAY_STRAVA_WEBHOOK_TOKEN",
    ]
    assert ENV_DATABASE_URL == "FITDOCS_RELAY_DATABASE_URL"


def test_a_run_line_naming_a_secret_variable_is_refused() -> None:
    found = _messages(_dockerfile() + "RUN echo $FITDOCS_RELAY_TOKEN_PEPPER\n")
    assert "RUN names the secret variable FITDOCS_RELAY_TOKEN_PEPPER" in found


def test_another_command_on_the_data_directory_is_refused() -> None:
    moved = _mutated("-m 0700 /data", "-m 0700 /data && chown root /data")
    found = _messages(moved)
    assert found == ["another command touches the data directory: ['chown root /data']"]


def test_a_non_secret_contract_variable_is_refused_as_operator_state() -> None:
    found = _messages(_dockerfile() + "ENV FITDOCS_RELAY_LOG_LEVEL=debug\n")
    assert found == [
        "ENV FITDOCS_RELAY_LOG_LEVEL sets contract state the operator owns"
    ]


def test_a_variable_named_like_a_secret_is_refused() -> None:
    assert _messages(_dockerfile() + "ARG DB_PASSWORD\n") == [
        "ARG DB_PASSWORD looks like a secret"
    ]
    assert _messages(_dockerfile() + "ARG API_KEY\n") == [
        "ARG API_KEY looks like a secret"
    ]


def test_a_database_file_is_refused() -> None:
    found = _messages(_dockerfile() + "COPY seed.db /data/seed.db\n")
    assert found == ["COPY 'seed.db /data/seed.db' handles a database file"]


def test_a_run_after_the_user_is_refused() -> None:
    assert _messages(_dockerfile() + "RUN true\n") == ["a RUN follows USER"]


def _without_digest(stage_name: str) -> str:
    pattern = re.compile(r"(slim-bookworm)" + DIGEST + r"( AS " + stage_name + r")")
    text, count = pattern.subn(r"\1\2", _dockerfile())
    assert count == 1, f"expected one {stage_name} FROM, found {count}"
    return text


def test_each_stage_base_must_carry_its_own_digest() -> None:
    runtime_only = _messages(_without_digest("runtime"))
    build_only = _messages(_without_digest("build"))
    assert [p for p in runtime_only if p.startswith("stage")] == [
        "stage 1 base 'python:3.12-slim-bookworm' is not the slim Python by digest"
    ]
    assert [p for p in build_only if p.startswith("stage")] == [
        "stage 0 base 'python:3.12-slim-bookworm' is not the slim Python by digest"
    ]


def test_the_entrypoint_command_port_and_host_are_pinned() -> None:
    assert any(
        "ENTRYPOINT" in p
        for p in findings(_mutated('ENTRYPOINT ["fitdocs-relay"]', 'ENTRYPOINT ["sh"]'))
    )
    assert any(
        "CMD" in p for p in findings(_mutated('CMD ["serve"]', 'CMD ["migrate"]'))
    )
    assert any("EXPOSE" in p for p in findings(_mutated("EXPOSE 8080", "EXPOSE 80")))
    assert any(
        "listen address" in p
        for p in findings(
            _mutated("FITDOCS_RELAY_HOST=0.0.0.0", "FITDOCS_RELAY_HOST=127.0.0.1")
        )
    )


def test_the_build_flags_the_data_directory_and_the_licences_are_pinned() -> None:
    assert findings(_mutated(" --locked", "")) != []
    assert findings(_mutated(" --no-dev", "")) != []
    assert findings(_mutated(" --extra postgres", "")) != []
    assert findings(_mutated(" --no-editable", "")) != []
    for wrong in ("/datax", "/srv"):
        moved = _mutated("-m 0700 /data", f"-m 0700 {wrong}")
        assert any("data directory" in p for p in findings(moved)), wrong
    assert any(
        "data directory" in p
        for p in findings(
            _mutated("install -d -o 10001 -g 10001 -m 0700 /data", "mkdir /data")
        )
    )
    assert any(
        "licence texts" in p
        for p in findings(
            _mutated(
                f"COPY --from=build {LICENCE_DIRECTORY} {LICENCE_DIRECTORY}\n",
                "",
            )
        )
    )
    assert any(
        "licence script" in p
        for p in findings(
            _mutated(
                "/opt/fitdocs-relay/bin/python scripts/collect_licences.py",
                "python scripts/collect_licences.py",
            )
        )
    )
    assert any(
        "contract user" in p
        for p in findings(_mutated("useradd --uid 10001", "useradd --uid 1000"))
    )


def test_a_copy_from_an_unpinned_image_is_refused() -> None:
    text = _dockerfile() + "COPY --from=alpine:3 /bin/sh /bin/sh\n"
    assert any("neither a stage nor pinned" in p for p in findings(text))


# --- the ignore file --------------------------------------------------------


def test_the_ignore_file_keeps_state_and_caches_out_of_the_context() -> None:
    lines = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert {".venv", ".git", "*.db", "*.db-wal", "*.db-shm", "*.serve-lock"} <= lines
    assert {".mypy_cache", ".pytest_cache", ".ruff_cache", "**/__pycache__"} <= lines
    assert "tests" in lines


# --- the smoke script is tied to the image and the workflow ------------------


def _smoke() -> str:
    assert SMOKE_SCRIPT.is_file()
    return SMOKE_SCRIPT.read_text(encoding="utf-8")


def _assign(text: str, name: str) -> str:
    matches = re.findall(rf'^{name}="([^"]+)"$', text, re.MULTILINE)
    assert len(matches) == 1, f"{name} is assigned {len(matches)} times"
    return str(matches[0])


def test_the_script_is_executable_and_names_exactly_the_three_runs() -> None:
    assert os.access(SMOKE_SCRIPT, os.X_OK)
    text = _smoke()
    assert "sqlite | postgres | derived) ;;" in text
    assert text.startswith("#!/usr/bin/env bash\n")


def test_the_script_copies_the_dockerfiles_uv_image() -> None:
    (uv_in_dockerfile,) = re.findall(
        r"--from=(ghcr\.io/astral-sh/uv:\S+) /uv", _dockerfile()
    )
    assert _assign(_smoke(), "UV_IMAGE") == uv_in_dockerfile


def test_the_script_uses_the_workflows_postgres_service_image() -> None:
    (service,) = re.findall(
        r"image: (postgres:17@sha256:[0-9a-f]{64})",
        WORKFLOW.read_text(encoding="utf-8"),
    )
    assert _assign(_smoke(), "POSTGRES_IMAGE") == service


def test_the_script_derives_from_the_contract() -> None:
    text = _smoke()
    assert _assign(text, "ENVIRONMENT_PATH") == IMAGE_ENVIRONMENT
    assert _assign(text, "USER_ID") == str(IMAGE_USER_ID)
    assert _assign(text, "PORT") == str(IMAGE_PORT)


def test_the_derived_image_is_built_by_the_documented_steps() -> None:
    text = _smoke()
    start = text.index("<<DOCKERFILE")
    end = text.index("\nDOCKERFILE\n")
    steps = [line for line in text[start:end].splitlines()[1:]]
    assert steps == [
        "FROM $IMAGE",
        "USER root",
        "COPY --from=$UV_IMAGE /uv /bin/uv",
        "COPY . /tmp/wrapper",
        "RUN uv pip install --python $ENVIRONMENT_PATH/bin/python /tmp/wrapper",
        "USER $USER_ID",
    ]


_WAIT_BLOCK = "wait_for /livez 200\nwait_for /readyz 200\n"
_STOP_BLOCK = (
    'docker kill --signal=SIGTERM "$SERVE_NAME" >/dev/null\n'
    'exit_code="$(docker wait "$SERVE_NAME")"\n'
    '[ "$exit_code" = 0 ] || fail '
    '"SIGTERM ended the container with exit code $exit_code"\n'
)
_SCAN_BLOCK = """\
scan_for_secrets() { # description text
  local planted
  for planted in "$FITDOCS_RELAY_TOKEN_PEPPER" "$DATABASE_PASSWORD"; do
    if contains "$2" "$planted"; then
      fail "a planted secret appears in the $1"
    fi
  done
}
"""
_SCAN_CALLS = (
    'scan_for_secrets "migrate output" "$migrate_out"\n',
    'scan_for_secrets "container log" "$LOGS"\n',
)
_DERIVED_ARGS = (
    '  RUN_IMAGE="$DERIVED_TAG"\n'
    '  RUN_ARGS+=(-e "FITDOCS_RELAY_EXTENSIONS=$EXTENSION_REFERENCE")\n'
)
_ROUTE_BLOCK = (
    '  body="$(curl -s --max-time 5 "$BASE/x/smoke/ping")"\n'
    '  [ "$body" = "smoke extension answers" ] || '
    "fail \"the extension route answered '$body'\"\n"
)


def test_the_script_probes_both_endpoints_for_200() -> None:
    assert _WAIT_BLOCK in _smoke()


def test_the_script_stops_with_sigterm_and_asserts_exit_zero() -> None:
    assert _STOP_BLOCK in _smoke()


def test_the_script_scans_the_migrate_output_and_the_log_for_planted_secrets() -> None:
    text = _smoke()
    assert _SCAN_BLOCK in text
    for call in _SCAN_CALLS:
        assert text.count(call) == 1, call
    # The migrate scan runs on output captured from stdout and stderr.
    assert '"$RUN_IMAGE" migrate 2>&1)"' in text


def test_the_derived_run_names_the_extension_and_checks_its_route() -> None:
    text = _smoke()
    assert _assign(text, "EXTENSION_REFERENCE") == "fitdocs_relay_smoke:EXTENSION"
    assert _DERIVED_ARGS in text
    assert _ROUTE_BLOCK in text


_SMOKE_CODE = r"""set -euo pipefail
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
"""  # noqa: E501


def _code_of(text: str) -> str:
    """The script from its options on, without comment lines and blank lines."""
    start = text.index("set -euo pipefail")
    return "\n".join(_code_lines(text[start:])) + "\n"


def test_the_whole_script_from_its_options_on_is_pinned() -> None:
    assert _code_of(_smoke()) == _SMOKE_CODE


_PUBLISH_WORDS = re.compile(r"\b(publish|login|push|upload|twine)\b")


def _code_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_the_script_never_publishes_logs_in_pushes_or_uploads() -> None:
    lines = _code_lines(_smoke())
    assert len(lines) > 100
    assert [line for line in lines if _PUBLISH_WORDS.search(line)] == []
    for spelling in (
        "docker image push x",
        "docker buildx build --push .",
        "docker login ghcr.io",
        "docker push x",
    ):
        assert _PUBLISH_WORDS.search(spelling), spelling


def test_the_build_backend_is_bounded_in_the_relay_and_the_smoke_wrapper() -> None:
    for path in (
        RELAY_ROOT / "pyproject.toml",
        RELAY_ROOT / "tests" / "smoke_extension" / "pyproject.toml",
    ):
        build = tomllib.loads(path.read_text("utf-8"))["build-system"]
        assert build["requires"] == ["hatchling>=1.27,<2"], path


# --- the smoke extension ----------------------------------------------------


def test_the_smoke_extension_is_an_installable_package_with_one_route() -> None:
    root = RELAY_ROOT / "tests" / "smoke_extension"
    assert (root / "pyproject.toml").is_file()
    source = (root / "fitdocs_relay_smoke" / "__init__.py").read_text(encoding="utf-8")
    assert re.findall(r'Route\("([^"]+)"', source) == ["/x/smoke/ping"]
    (answer,) = re.findall(r'^ANSWER = "([^"]+)"$', source, re.MULTILINE)
    assert f'[ "$body" = "{answer}" ]' in _smoke()
    assert 'name = "smoke"' in source and "EXTENSION = SmokeExtension()" in source


# --- the licence collection script ------------------------------------------


def _collect(destination: Path) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("FITDOCS_RELAY_", "PYTHON"))
    }
    return subprocess.run(
        [sys.executable, "-I", "-B", str(LICENCE_SCRIPT), str(destination)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_the_licence_script_lists_every_installed_distribution(tmp_path: Path) -> None:
    result = _collect(tmp_path / "licences")
    assert result.returncode == 0, result.stderr
    written = {p.name for p in (tmp_path / "licences").iterdir()}
    installed = {
        f"{d.metadata['Name']}-{d.version}".replace(" ", "_") for d in distributions()
    }
    assert len(installed) > 5
    assert installed == written
    starlette = [p for p in written if p.startswith("starlette-")]
    assert len(starlette) == 1
    files = list((tmp_path / "licences" / starlette[0]).iterdir())
    assert files and all("licen" in f.name.lower() for f in files)
    assert all(f.stat().st_size > 100 for f in files)
    (own,) = [p for p in written if p.startswith("fitdocs-relay-")]
    own_files = list((tmp_path / "licences" / own).iterdir())
    assert [f.name for f in own_files] == ["LICENSE"]
    assert own_files[0].read_bytes() == (RELAY_ROOT / "LICENSE").read_bytes()


def test_the_relay_licence_is_the_roots_and_is_declared() -> None:
    assert (RELAY_ROOT / "LICENSE").read_bytes() == (REPO_ROOT / "LICENSE").read_bytes()
    project = tomllib.loads((RELAY_ROOT / "pyproject.toml").read_text("utf-8"))[
        "project"
    ]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]


def test_the_licence_script_refuses_a_missing_destination_argument() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(LICENCE_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr


def _fake_distribution(
    root: Path,
    name: str,
    metadata: str = "",
    files: dict[str, str] | None = None,
) -> PathDistribution:
    info = root / f"{name}-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n{metadata}",
        encoding="utf-8",
    )
    record = [f"{info.name}/METADATA,,"]
    for file_name, content in (files or {}).items():
        (info / file_name).write_text(content, encoding="utf-8")
        record.append(f"{info.name}/{file_name},,")
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")
    return PathDistribution(info)


def _collected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    spec = importlib.util.spec_from_file_location(
        "collect_licences_under_test", LICENCE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    site = tmp_path / "site"
    dists = [
        _fake_distribution(
            site, "has-file", "License-Expression: MIT\n", {"LICENSE": "the text\n"}
        ),
        _fake_distribution(site, "lacks-file", "License-Expression: MIT\n"),
        _fake_distribution(
            site,
            "classifier-only",
            "Classifier: Programming Language :: Python :: 3\n"
            "Classifier: License :: OSI Approved :: MIT License\n",
        ),
        _fake_distribution(site, "declares-nothing"),
        _fake_distribution(
            site, "notice-only", "License: Apache-2.0\n", {"NOTICE": "notice text\n"}
        ),
    ]
    monkeypatch.setattr(module, "distributions", lambda: dists)
    names = module.collect(tmp_path / "out")
    assert names == [
        "classifier-only-1.0",
        "declares-nothing-1.0",
        "has-file-1.0",
        "lacks-file-1.0",
        "notice-only-1.0",
    ]
    return {n: tmp_path / "out" / n for n in names}


def _contents(directory: Path) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in directory.iterdir()}


def test_a_distribution_with_a_licence_file_has_it_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _collected(tmp_path, monkeypatch)
    assert _contents(out["has-file-1.0"]) == {"LICENSE": "the text\n"}


def test_a_notice_file_alone_is_copied_and_no_placeholder_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _collected(tmp_path, monkeypatch)
    assert _contents(out["notice-only-1.0"]) == {"NOTICE": "notice text\n"}


def test_a_distribution_without_a_licence_file_quotes_its_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _collected(tmp_path, monkeypatch)
    assert _contents(out["lacks-file-1.0"]) == {
        "LICENCE-METADATA.txt": "License-Expression: MIT\n"
    }
    assert _contents(out["classifier-only-1.0"]) == {
        "LICENCE-METADATA.txt": "Classifier: License :: OSI Approved :: MIT License\n"
    }
    assert _contents(out["declares-nothing-1.0"]) == {
        "LICENCE-METADATA.txt": "The distribution's metadata declares no licence.\n"
    }
