# syntax=docker/dockerfile:1
#
# Черновик образа портала SwarmLab (`swarmlab serve --public`, M9b, DECISIONS №93, №95).
# Общий для всех веток: ставит пакет той ветки, из которой собирается (`pip install .`) —
# в `master` это ядро без модуля, в ветке модуля (`bees`, …) — ядро + модуль.
#
#   docker build -t swarmlab .                     образ приложения (цель по умолчанию)
#   docker build --target test -t swarmlab-test .  то же + pytest и ruff (тесты в Linux)
#
# Предлагаемый запуск — без --privileged и без docker.sock, с профилями из docker/.
# Требует проверки в Linux по критериям M9b (docs/ROADMAP.md); параметры ещё не приняты.
#   docker run -d -p 127.0.0.1:8000:8000 -v swarmlab-data:/data \
#     --security-opt seccomp=docker/seccomp.json \
#     --security-opt apparmor=swarmlab-sandbox swarmlab

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ------------------------------------------------------------------ nsjail из исходников
FROM debian:bookworm-slim AS nsjail
ARG NSJAIL_VERSION=3.4
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      autoconf bison ca-certificates flex g++ gcc git libnl-route-3-dev libprotobuf-dev \
      libtool make pkg-config protobuf-compiler \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${NSJAIL_VERSION}" --recurse-submodules --shallow-submodules \
      https://github.com/google/nsjail /src/nsjail \
 && make -C /src/nsjail -j"$(nproc)" \
 && strip /src/nsjail/nsjail

# ------------------------------------------------------------------ общая основа
FROM ${PYTHON_IMAGE} AS base
RUN apt-get update \
 && apt-get install -y --no-install-recommends libnl-route-3-200 libprotobuf32 uidmap \
 && rm -rf /var/lib/apt/lists/*
COPY --from=nsjail /src/nsjail/nsjail /usr/local/bin/nsjail
# Сервер — от пользователя swarmlab (1000). Код игрока — от uid 100000 из его диапазона
# /etc/subuid (newuidmap, docker/runner.nsjail.cfg): не uid сервера.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin swarmlab \
 && echo "swarmlab:100000:65536" > /etc/subuid \
 && echo "swarmlab:100000:65536" > /etc/subgid \
 && python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir /app

# ------------------------------------------------------------------ тесты в Linux
FROM base AS test
RUN pip install --no-cache-dir "/app[dev]"
USER swarmlab
CMD ["sh", "-c", "python -m pytest -q -p no:cacheprovider && ruff check --no-cache ."]

# ------------------------------------------------------------------ приложение
FROM base AS app
RUN mkdir /data && chown swarmlab:swarmlab /data
USER swarmlab
VOLUME /data
EXPOSE 8000
CMD ["swarmlab", "serve", "--public", "--host", "0.0.0.0", "--port", "8000", "--data", "/data"]
