#!/usr/bin/env bash
# Prépare une séance de Claude Code dans le cloud (claude.ai/code, JOURNAL, entrée 96) : installe
# les dépendances Python (uv) et TypeScript (pnpm) du dépôt, comme make installer, met Node 24 en
# place et active les crochets git : avant commit comme make installer-hooks, avant poussée pour
# refuser main. Appelé par le crochet SessionStart de .claude/settings.json, au démarrage et à la
# reprise d'une séance.
#
# Hors du cloud (CLAUDE_CODE_REMOTE différent de true), il ne fait rien : le poste d'Alexandre a
# déjà ses dépendances. Il ne bloque jamais le démarrage : ce qui échoue est écrit, la séance
# continue. Aucune clé n'est lue ni écrite ici.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

# La PME et le gardien demandent Node 24 ou plus (package.json, engines ; l'intégration continue
# tourne en 24). L'image du cloud porte Node 20, 21 et 22, la 22 par défaut
# (code.claude.com/docs/en/cloud-environments, lu le 2026-10-08). On tente la dernière 24 de
# nodejs.org, empreinte SHA-256 comparée à celle que publie nodejs.org, puis on la met en tête du
# PATH de la séance par CLAUDE_ENV_FILE (code.claude.com/docs/en/hooks). Si le réseau la refuse,
# on le dit et on continue avec le Node présent.
NODE_24="$HOME/.local/node24"

majeur_node() {
  node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0
}

installer_node_24() {
  local base="https://nodejs.org/dist/latest-v24.x" tmp nom
  [ "$(uname -m)" = "x86_64" ] || return 1
  if [ ! -x "$NODE_24/bin/node" ]; then
    tmp=$(mktemp -d) || return 1
    curl -fsSL --max-time 60 "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt" || return 1
    nom=$(grep -oE 'node-v24\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz' "$tmp/SHASUMS256.txt" | head -n 1)
    [ -n "$nom" ] || return 1
    curl -fsSL --max-time 300 "$base/$nom" -o "$tmp/$nom" || return 1
    (cd "$tmp" && grep " $nom\$" SHASUMS256.txt | sha256sum --check --status) || return 1
    mkdir -p "$NODE_24" || return 1
    tar -xJf "$tmp/$nom" -C "$NODE_24" --strip-components=1 || return 1
    rm -rf "$tmp"
  fi
  export PATH="$NODE_24/bin:$PATH"
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export PATH=\"$NODE_24/bin:\$PATH\"" >>"$CLAUDE_ENV_FILE"
  fi
}

if [ "$(majeur_node)" -lt 24 ]; then
  if installer_node_24; then
    echo "Préparation du cloud : Node $(node --version) en place."
  else
    echo "Préparation du cloud : Node 24 non installé, Node $(majeur_node) ici ; les tests TypeScript peuvent échouer." >&2
  fi
fi

if uv sync --all-packages --frozen; then
  echo "Préparation du cloud : environnement Python prêt (uv)."
else
  echo "Préparation du cloud : uv sync a échoué, voir ci-dessus." >&2
fi

corepack enable >/dev/null 2>&1 || true
if pnpm install --frozen-lockfile; then
  echo "Préparation du cloud : environnement TypeScript prêt (pnpm)."
else
  echo "Préparation du cloud : pnpm install a échoué, voir ci-dessus." >&2
fi

# Crochets git de la séance, rangés hors du dépôt : celui d'avant commit du dépôt (la garde de
# l'arborescence, comme sur le poste), et un crochet avant poussée qui refuse main, puis lance
# celui du dépôt (make tests, ADR 0007).
# GitHub ne protège pas les branches d'un dépôt privé sans offre payante (docs.github.com, page
# about-protected-branches, lue le 2026-10-08), et le proxy GitHub du cloud ne limite pas les
# branches qu'une séance pousse (code.claude.com/docs/en/cloud-environments, section GitHub proxy).
crochets="$HOME/.config/poa/crochets"
if mkdir -p "$crochets"; then
  cat >"$crochets/pre-commit" <<'FIN'
#!/bin/sh
exec sh "$(git rev-parse --show-toplevel)/09_outillage/hooks/pre-commit" "$@"
FIN
  cat >"$crochets/pre-push" <<'FIN'
#!/bin/sh
while read -r _ _ distante _; do
  if [ "$distante" = "refs/heads/main" ]; then
    echo "Poussée refusée : une séance dans le cloud ne pousse jamais main ; pousse ta propre branche." >&2
    exit 1
  fi
done
exec sh "$(git rev-parse --show-toplevel)/09_outillage/hooks/pre-push" "$@"
FIN
fi
if chmod +x "$crochets/pre-commit" "$crochets/pre-push" && git config core.hooksPath "$crochets"; then
  echo "Préparation du cloud : crochets git actifs (avant commit : garde ; avant poussée : jamais main, puis tests)."
else
  echo "Préparation du cloud : crochets git non activés." >&2
fi
exit 0
