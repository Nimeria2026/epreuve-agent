# syntax=docker/dockerfile:1
# Image du banc de l'Épreuve d'agent (étape 8) : EASE, la PME, le gardien, EKE et τ²-bench, lancés
# comme sur le poste, en stdio, dans un seul conteneur. Le modèle reste dehors : un fournisseur par
# son API, ou Qwen 3.8 27B servi par make qwen sur la machine.
# Cadrage : 00_docs/sources/2026-10-11_cadrage_etape8.md.
#
# Ne se construit pas à la main : make image [COMMIT=HEAD], par
# 09_outillage/scripts/construire_image.sh. Le contexte est l'archive git d'un commit, donc les
# seuls fichiers suivis : les tâches cachées, le .env et 99_local/ n'y entrent jamais.
#
# Derrière un proxy qui déchiffre le TLS (réseau d'entreprise, bac à sable d'une séance Claude), son
# certificat passe en secret de construction, POA_CA=<fichier> make image : il ne sert qu'aux
# téléchargements de la construction et n'entre pas dans l'image.
#
# Images de base épinglées par leur empreinte, relevée le 2026-10-11.

FROM node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node
FROM ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 AS uv

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# git : uv récupère τ²-bench à son commit figé ; make : les commandes du dépôt.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git make ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Node 24, pour les services de la PME et le gardien ; pnpm à la version de package.json.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN --mount=type=secret,id=ca \
    if [ -s /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi \
 && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && npm install --global pnpm@12.9.1 \
 && npm cache clean --force

COPY --from=uv /uv /uvx /usr/local/bin/

# L'environnement Python du dépôt sur le Python de l'image, jamais un Python téléchargé.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /poa
COPY . .

# Comme make installer, versions figées par uv.lock et pnpm-lock.yaml.
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=ca \
    if [ -s /run/secrets/ca ]; then \
      export SSL_CERT_FILE=/run/secrets/ca GIT_SSL_CAINFO=/run/secrets/ca \
             NODE_EXTRA_CA_CERTS=/run/secrets/ca; \
    fi \
 && uv sync --all-packages --frozen \
 && pnpm install --frozen-lockfile --config.package-import-method=copy --store-dir=/tmp/pnpm \
 && rm -rf /tmp/pnpm

# Au lancement, sous l'identité de qui lance : rien à installer, rien à écrire hors de 99_local/
# (monté) et de /tmp.
ENV UV_NO_SYNC=1 \
    UV_FROZEN=1 \
    UV_CACHE_DIR=/tmp/uv \
    HOME=/tmp \
    USER=poa \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/poa/.venv/bin:$PATH

# Le commit complet de l'archive : EASE le lit pour la fiche de run, l'image n'ayant pas de dépôt
# git (POA_COMMIT_IMAGE, executeur.version_code). Déclaré en dernier pour garder le cache des
# couches d'installation d'un commit à l'autre.
ARG COMMIT
RUN case "$COMMIT" in \
      [0-9a-f]*) test "${#COMMIT}" -eq 40 ;; \
      *) false ;; \
    esac || { echo "COMMIT absent ou incomplet : construire par make image" >&2; exit 1; }
ENV POA_COMMIT_IMAGE=${COMMIT}
LABEL org.opencontainers.image.title="poa-banc" \
      org.opencontainers.image.description="Banc de l'Épreuve d'agent : EASE, PME, gardien, EKE, τ²-bench" \
      org.opencontainers.image.revision="${COMMIT}"

CMD ["make"]
