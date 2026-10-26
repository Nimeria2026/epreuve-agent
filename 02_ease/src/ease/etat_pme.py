"""L'état de la PME sur le disque, capturé pour les contrôles.

Règle 3 du BRIEF : la réussite se juge sur l'état final, lu directement, sans passer par MCP ni
par l'agent. Un instantané garde l'empreinte de chaque fichier partagé, chaque courriel rangé
dans sa boîte et l'empreinte de chaque pièce jointe.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ease.chargement import PARAMETRES_CALORELLE, parametres_societe
from ease.contrats.avoir import Avoir
from ease.contrats.commande import Commande
from ease.contrats.courriel import Courriel
from ease.contrats.devis import Devis
from ease.contrats.intervention import Intervention
from ease.contrats.retour import Retour
from ease.contrats.technicien import Technicien
from ease.courriels import lire_courriel

type DossierBoite = Literal["reception", "envoyes"]
DOSSIERS_BOITE: tuple[DossierBoite, ...] = ("reception", "envoyes")


def empreinte_octets(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


@dataclass(frozen=True)
class CourrielRange:
    """Un courriel tel qu'il est rangé : sa boîte, son dossier, son contenu."""

    boite: str
    dossier: DossierBoite
    courriel: Courriel


@dataclass(frozen=True)
class Instantane:
    """Instantané de l'état de la PME.

    fichiers : chemin relatif aux dossiers partagés, puis empreinte du contenu ;
    pieces : chemin relatif à la messagerie (pieces/<courriel>/<nom>), puis empreinte ;
    facturation : chemin relatif à la facturation (factures/<numero>.json, avoirs/<numero>.json,
    devis/<numero>.json, tarif.json), puis empreinte ;
    planning : chemin relatif au planning (horaires.yaml, techniciens/<id>.json,
    interventions/<numero>.json), puis empreinte. Vide pour un état sans planning (v1) ;
    ventes : chemin relatif aux ventes (catalogue.json, commandes/<numero>.json,
    livraisons/<numero>.json, retours/<numero>.json), puis empreinte. Vide pour une société sans
    service de ventes (Calorelle, Domivelle).
    """

    fichiers: Mapping[str, str] = field(default_factory=lambda: {})
    courriels: tuple[CourrielRange, ...] = ()
    pieces: Mapping[str, str] = field(default_factory=lambda: {})
    facturation: Mapping[str, str] = field(default_factory=lambda: {})
    avoirs: tuple[Avoir, ...] = ()
    """Les avoirs de la facturation, lus selon leur contrat, par numéro croissant."""
    devis: tuple[Devis, ...] = ()
    """Les devis de la facturation, lus selon leur contrat, par numéro croissant (à partir de v3)."""
    planning: Mapping[str, str] = field(default_factory=lambda: {})
    interventions: tuple[Intervention, ...] = ()
    """Les interventions du planning, annulées comprises, lues selon leur contrat, par numéro croissant."""
    techniciens: tuple[Technicien, ...] = ()
    """Les fiches des techniciens du planning, lues selon leur contrat."""
    ventes: Mapping[str, str] = field(default_factory=lambda: {})
    commandes: tuple[Commande, ...] = ()
    """Les commandes du service des ventes, lues selon leur contrat, par numéro croissant."""
    retours: tuple[Retour, ...] = ()
    """Les retours du service des ventes, lus selon leur contrat, par numéro croissant."""
    clients_bloques: frozenset[str] = frozenset()
    """Les codes des clients bloqués, lus au statut de leur fiche, pour une société qui a un service
    de ventes : c'est lui qui écrit ce statut (bloquer_client)."""
    ibans: Mapping[str, str] = field(default_factory=lambda: {})
    """L'IBAN de la fiche de chaque fournisseur, sans espaces ni mention, par dossier du fournisseur :
    c'est le service des achats qui l'écrit (modifier_rib_fournisseur ; JOURNAL, entrée 202)."""
    domaine: str = PARAMETRES_CALORELLE.domaine
    """Le domaine des adresses du personnel de la société (entreprise/societe.yaml, ADR 0006) :
    <identifiant>@<domaine>, celles de l'organigramme."""

    def courriel(self, identifiant: str) -> Courriel | None:
        """Le courriel portant cet identifiant, où qu'il soit rangé."""
        return next((r.courriel for r in self.courriels if r.courriel.identifiant == identifiant), None)

    def envois_depuis(self, initial: Instantane) -> list[Courriel]:
        """Courriels envoyés depuis l'état initial : présents dans un dossier « envoyes », absents au départ."""
        anciens = {r.courriel.identifiant for r in initial.courriels}
        envois: dict[str, Courriel] = {}
        for rang in self.courriels:
            if rang.dossier == "envoyes" and rang.courriel.identifiant not in anciens:
                envois.setdefault(rang.courriel.identifiant, rang.courriel)
        return [envois[i] for i in sorted(envois)]


def _empreintes(racine: Path, prefixe: str = "") -> dict[str, str]:
    if not racine.is_dir():
        return {}
    return {
        prefixe + chemin.relative_to(racine).as_posix(): empreinte_octets(chemin.read_bytes())
        for chemin in sorted(racine.rglob("*"))
        if chemin.is_file()
    }


STATUT_BLOQUE = re.compile(r'^statut: "?bloque"?\s*$', re.MULTILINE)
"""La ligne de statut d'une fiche client bloquée, telle que l'écrivent le générateur de l'état et le
service des ventes (bloquer_client) : lue sans charger les 350 fiches en YAML."""


def _clients_bloques(etat: Path) -> frozenset[str]:
    if not (etat / "ventes").is_dir():
        return frozenset()
    fiches = sorted((etat / "dossiers" / "clients").glob("*/fiche_client.yaml"))
    return frozenset(f.parent.name for f in fiches if STATUT_BLOQUE.search(f.read_text(encoding="utf-8")))


LIGNE_IBAN = re.compile(r'^iban: "?(FR[0-9 ]+)', re.MULTILINE)
"""La ligne de l'IBAN d'une fiche de fournisseur, telle que l'écrivent les générateurs des états et
le service des achats : lue sans charger les fiches en YAML."""


def _ibans(etat: Path) -> dict[str, str]:
    ibans: dict[str, str] = {}
    for fiche in sorted((etat / "dossiers").rglob("fiche_fournisseur.yaml")):
        if trouve := LIGNE_IBAN.search(fiche.read_text(encoding="utf-8")):
            ibans[fiche.parent.name] = trouve.group(1).replace(" ", "")
    return ibans


def capturer(etat: Path) -> Instantane:
    """Lit l'état de la PME rangé dans un dossier (dossiers/, messagerie/, facturation/, planning/,
    ventes/)."""
    boites = etat / "messagerie" / "boites"
    courriels: list[CourrielRange] = []
    if boites.is_dir():
        for boite in sorted(p for p in boites.iterdir() if p.is_dir()):
            for dossier in DOSSIERS_BOITE:
                for chemin in sorted((boite / dossier).glob("*.json")):
                    courriels.append(CourrielRange(boite.name, dossier, lire_courriel(chemin)))
    return Instantane(
        fichiers=_empreintes(etat / "dossiers"),
        courriels=tuple(courriels),
        pieces=_empreintes(etat / "messagerie" / "pieces", prefixe="pieces/"),
        facturation=_empreintes(etat / "facturation"),
        avoirs=tuple(
            Avoir.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "facturation" / "avoirs").glob("*.json"))
        ),
        devis=tuple(
            Devis.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "facturation" / "devis").glob("*.json"))
        ),
        planning=_empreintes(etat / "planning"),
        interventions=tuple(
            Intervention.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "planning" / "interventions").glob("*.json"))
        ),
        techniciens=tuple(
            Technicien.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "planning" / "techniciens").glob("*.json"))
        ),
        ventes=_empreintes(etat / "ventes"),
        commandes=tuple(
            Commande.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "ventes" / "commandes").glob("*.json"))
        ),
        retours=tuple(
            Retour.model_validate_json(chemin.read_text(encoding="utf-8"))
            for chemin in sorted((etat / "ventes" / "retours").glob("*.json"))
        ),
        clients_bloques=_clients_bloques(etat),
        ibans=_ibans(etat),
        domaine=parametres_societe(etat).domaine,
    )
