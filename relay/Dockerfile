# The relay image (relay-server task 5.3; design.md "RelayImage and
# RelayWorkflow"; Requirements 9.1, 9.11). Build it with the relay directory as
# the context:
#
#     docker build -t fitdocs-relay relay
#
# Two stages. The build stage installs the locked, non-dev dependency set and
# the relay itself, plus the postgres extra, into /opt/fitdocs-relay and
# collects the licence texts of everything installed. The runtime stage copies
# that environment to the same path, so its scripts and symlinks stay valid.
#
# Both base images are pinned by digest. Re-pin with
# `docker buildx imagetools inspect <image>:<tag>` and copy the index digest.
# The uv version in the COPY below and the Python base must move together with
# relay/scripts/image_smoke.sh, which copies the same uv binary into the
# derived image.

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.24@sha256:99ea34acedc870ba4ad11a1f540a1c04267c9f30aadc465a94406f52dfda2c36 /uv /bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/fitdocs-relay \
    UV_PYTHON=/usr/local/bin/python \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY scripts ./scripts
RUN uv sync --locked --no-dev --extra postgres --no-editable
RUN /opt/fitdocs-relay/bin/python scripts/collect_licences.py /usr/share/licenses/fitdocs-relay

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime

COPY --from=build /opt/fitdocs-relay /opt/fitdocs-relay
COPY --from=build /usr/share/licenses/fitdocs-relay /usr/share/licenses/fitdocs-relay

RUN groupadd --gid 10001 relay \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin relay \
    && install -d -o 10001 -g 10001 -m 0700 /data

ENV PATH=/opt/fitdocs-relay/bin:$PATH \
    FITDOCS_RELAY_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

WORKDIR /data
EXPOSE 8080
USER 10001
ENTRYPOINT ["fitdocs-relay"]
CMD ["serve"]
