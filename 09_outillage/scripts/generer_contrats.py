"""Génère le code des contrats à partir des schémas JSON de 01_contrats/.

Les contrats s'écrivent en JSON Schema, source de vérité unique (BRIEF §6). Ce script en tire
deux sorties, jamais modifiées à la main :
- les modèles Pydantic d'EASE, avec datamodel-code-generator (uv) ;
- les types TypeScript de la PME, avec json-schema-to-typescript (pnpm).

Usage, depuis la racine du dépôt :
    uv run python 09_outillage/scripts/generer_contrats.py              # régénère
    uv run python 09_outillage/scripts/generer_contrats.py --verifier   # contrôle sans écrire

Codes de sortie : 0 à jour ou régénéré, 1 code généré périmé, 2 erreur de génération.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SCHEMAS = RACINE / "01_contrats"
SUFFIXE = ".schema.json"
AVERTISSEMENT = "Ne pas modifier à la main : modifier le schéma, puis régénérer."

# Options de datamodel-code-generator, en un seul endroit pour la génération et le contrôle.
OPTIONS_PYTHON = [
    "--input-file-type",
    "jsonschema",
    "--output-model-type",
    "pydantic_v2.BaseModel",
    "--target-python-version",
    "3.12",
    "--disable-timestamp",
    "--use-standard-collections",
    "--use-union-operator",
    "--use-annotated",
    "--use-type-alias",
    "--field-constraints",
    "--use-double-quotes",
    "--use-schema-description",
    "--use-field-description",
    "--enum-field-as-literal",
    "all",
    "--output-datetime-class",
    "AwareDatetime",
    "--extra-fields",
    "forbid",
]


def _lancer(commande: list[str], schema: Path) -> None:
    resultat = subprocess.run(commande, capture_output=True, text=True, cwd=RACINE)
    if resultat.returncode != 0:
        raise RuntimeError(f"génération de {schema.name} impossible :\n{resultat.stderr}{resultat.stdout}")


def _generer_python(schema: Path, sortie: Path) -> None:
    entete = f"# Généré depuis 01_contrats/{schema.name} par make contrats.\n# {AVERTISSEMENT}"
    _lancer(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(schema),
            "--output",
            str(sortie),
            "--custom-file-header",
            entete,
            *OPTIONS_PYTHON,
        ],
        schema,
    )


def _generer_typescript(schema: Path, sortie: Path) -> None:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm introuvable : installer l'outillage TypeScript (make installer).")
    entete = f"// Généré depuis 01_contrats/{schema.name} par make contrats.\n// {AVERTISSEMENT}"
    _lancer(
        [pnpm, "exec", "json2ts", "--input", str(schema), "--output", str(sortie), "--bannerComment", entete],
        schema,
    )


@dataclass(frozen=True)
class Cible:
    """Une sortie de la génération : un langage, un dossier, une extension."""

    langage: str
    dossier: Path
    extension: str
    marque: str
    generer: Callable[[Path, Path], None]

    def module(self, schema: Path) -> Path:
        return self.dossier / (schema.name.removesuffix(SUFFIXE) + self.extension)


CIBLES = [
    Cible("Python", RACINE / "02_ease" / "src" / "ease" / "contrats", ".py", "# Généré depuis", _generer_python),
    Cible(
        "TypeScript", RACINE / "05_pme" / "commun" / "src" / "contrats", ".ts", "// Généré depuis", _generer_typescript
    ),
]


def schemas() -> list[Path]:
    return sorted(SCHEMAS.glob(f"*{SUFFIXE}"))


def orphelins(cible: Cible) -> list[Path]:
    """Modules générés dont le schéma n'existe plus."""
    attendus = {cible.module(s) for s in schemas()}
    return [
        module
        for module in sorted(cible.dossier.glob(f"*{cible.extension}"))
        if module not in attendus and module.read_text(encoding="utf-8").startswith(cible.marque)
    ]


def ecarts() -> list[str]:
    """Liste ce qui diffère entre le code généré présent et une génération fraîche."""
    messages: list[str] = []
    with tempfile.TemporaryDirectory() as dossier:
        for cible in CIBLES:
            for schema in schemas():
                present = cible.module(schema)
                frais = Path(dossier) / f"{cible.langage}_{present.name}"
                cible.generer(schema, frais)
                if not present.exists():
                    messages.append(f"absent : {present.relative_to(RACINE)}")
                elif present.read_text(encoding="utf-8") != frais.read_text(encoding="utf-8"):
                    messages.append(f"périmé : {present.relative_to(RACINE)}")
            messages += [f"orphelin, schéma disparu : {m.relative_to(RACINE)}" for m in orphelins(cible)]
    return messages


def main() -> int:
    analyse = argparse.ArgumentParser(description=(__doc__ or "Génère le code des contrats.").splitlines()[0])
    analyse.add_argument("--verifier", action="store_true", help="contrôle sans rien écrire")
    args = analyse.parse_args()
    try:
        if args.verifier:
            messages = ecarts()
            if messages:
                print("Code des contrats à régénérer (make contrats) :", file=sys.stderr)
                for message in messages:
                    print(f"  {message}", file=sys.stderr)
                return 1
            print(f"Code des contrats à jour ({len(schemas())} schéma(s), {len(CIBLES)} langages).")
            return 0
        for cible in CIBLES:
            cible.dossier.mkdir(parents=True, exist_ok=True)
            for schema in schemas():
                cible.generer(schema, cible.module(schema))
                print(f"généré : {cible.module(schema).relative_to(RACINE)}")
            for module in orphelins(cible):
                print(f"orphelin à supprimer à la main : {module.relative_to(RACINE)}", file=sys.stderr)
        return 0
    except RuntimeError as erreur:
        print(erreur, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
