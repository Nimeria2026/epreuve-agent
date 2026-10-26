"""Les valeurs de la vérité d'un document, à leur adresse, comme le correcteur du banc les compte.

Reprise du côté vérité de `omni_extract_bench/metric.py` (0.1.7, Apache 2.0) : enveloppes
`{"value": ...}` retirées (`unwrap`), `$ref` locales recopiées (`resolve_refs`), branche non nulle
d'un `anyOf` (`unwrap_schema`), objets à `additionalProperties` sautés (`is_open_map`), puis une
adresse par valeur scalaire qui dit quelque chose (`flatten`, `states_nothing`). Ce que le banc
note pour un document, ce sont ces adresses : `|gold|` de sa métrique.
"""

from __future__ import annotations

from typing import Any, cast

from eke.banc_public.omni.valeurs import ne_dit_rien

METADONNEES_ENVELOPPE = frozenset({
    "citations", "citation", "confidence", "score", "reasoning", "evidence", "provenance",
    "source", "sources", "page", "pages", "bbox", "span", "spans", "offset", "offsets",
    "extraction_status", "status", "meta",
})  # fmt: skip
PROFONDEUR_MAX = 12

Adresse = tuple[tuple[str, str | int], ...]
"""Une suite d'étapes : (« k », clé) ou (« i », indice)."""


def deballer(o: Any) -> Any:
    """`unwrap` : une enveloppe a une clé « value », au moins une clé de métadonnées, rien d'autre."""
    if isinstance(o, dict):
        objet = cast(dict[str, Any], o)
        autres = set(objet) - {"value"}
        if "value" in objet and autres and autres <= METADONNEES_ENVELOPPE:
            return deballer(objet["value"])
        return {k: deballer(v) for k, v in objet.items()}
    if isinstance(o, list):
        return [deballer(x) for x in cast(list[Any], o)]
    return o


def preparer_verite(o: Any) -> dict[str, Any]:
    """`prep_ground_truth`."""
    o = deballer(o)
    return cast(dict[str, Any], o) if isinstance(o, dict) else {}


def carte_ouverte(noeud: Any) -> bool:
    """`is_open_map` : un objet dont les clés viennent du document, que le banc ne note pas."""
    if not isinstance(noeud, dict):
        return False
    objet = cast(dict[str, Any], noeud)
    for branche in ("anyOf", "oneOf", "allOf"):
        for sous in cast(list[Any], objet.get(branche, []) or []):
            if carte_ouverte(sous):
                return True
    autres = objet.get("additionalProperties")
    return autres is True or isinstance(autres, dict)


def schema_deballe(noeud: Any) -> dict[str, Any]:
    """`unwrap_schema` : la première branche non nulle d'un anyOf, oneOf ou allOf."""
    if not isinstance(noeud, dict):
        return {}
    objet = cast(dict[str, Any], noeud)
    for branche in ("anyOf", "oneOf", "allOf"):
        for sous in cast(list[Any], objet.get(branche, []) or []):
            if isinstance(sous, dict) and cast(dict[str, Any], sous).get("type") != "null":
                return cast(dict[str, Any], sous)
    return objet


def resoudre_references(schema: Any, racine: Any = None, profondeur: int = 0) -> Any:
    """`resolve_refs` : les `$ref` locales recopiées, au plus 12 niveaux."""
    if racine is None:
        racine = schema
    if profondeur > PROFONDEUR_MAX or not isinstance(schema, (dict, list)):
        return schema
    if isinstance(schema, list):
        return [resoudre_references(x, racine, profondeur + 1) for x in cast(list[Any], schema)]
    objet = cast(dict[str, Any], schema)
    reference = objet.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        courant: Any = racine
        for partie in reference[2:].split("/"):
            courant = cast(dict[str, Any], courant).get(partie) if isinstance(courant, dict) else None
        if isinstance(courant, dict):
            fusion = {k: v for k, v in objet.items() if k != "$ref"}
            fusion.update({k: v for k, v in cast(dict[str, Any], courant).items() if k not in fusion})
            return resoudre_references(fusion, racine, profondeur + 1)
    return {
        k: (resoudre_references(v, racine, profondeur + 1) if k != "$defs" else v)
        for k, v in objet.items()
        if k != "$defs"
    }


def a_reference(noeud: Any) -> bool:
    """`_has_ref` : une `$ref` reste après recopie (schéma récursif au-delà de la limite)."""
    if isinstance(noeud, dict):
        objet = cast(dict[str, Any], noeud)
        return "$ref" in objet or any(a_reference(v) for v in objet.values())
    if isinstance(noeud, list):
        return any(a_reference(v) for v in cast(list[Any], noeud))
    return False


def aplatir(noeud: Any, schema: Any = None, prefixe: Adresse = ()) -> dict[Adresse, Any]:
    """`flatten` : une adresse par valeur qui dit quelque chose ; une carte ouverte est sautée."""
    schema = schema_deballe(schema) if isinstance(schema, dict) else {}
    if carte_ouverte(schema):
        return {}
    sortie: dict[Adresse, Any] = {}
    if isinstance(noeud, dict):
        proprietes = cast(dict[str, Any], schema.get("properties") or {})
        for cle_, valeur in cast(dict[str, Any], noeud).items():
            sortie.update(aplatir(valeur, proprietes.get(cle_), (*prefixe, ("k", cle_))))
    elif isinstance(noeud, list):
        element = schema.get("items")
        for i, valeur in enumerate(cast(list[Any], noeud)):
            sortie.update(aplatir(valeur, element, (*prefixe, ("i", i))))
    elif not ne_dit_rien(noeud):
        sortie[prefixe] = noeud
    return sortie


def valeurs_de_la_verite(verite: Any, schema: dict[str, Any]) -> dict[Adresse, Any]:
    """Les adresses notées d'un document, comme `score` les tire de la vérité et du schéma."""
    if not schema:
        raise ValueError("le banc exige un schéma")
    resolu = resoudre_references(schema)
    if a_reference(resolu):
        raise ValueError("schéma récursif au-delà de la limite de recopie")
    if verite is not None and not isinstance(verite, dict):
        raise ValueError("la vérité doit être un objet JSON")
    return aplatir(preparer_verite(verite or {}), resolu)
