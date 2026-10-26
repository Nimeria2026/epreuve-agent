"""Les données initiales v3 de Calorelle : v2 et les ajouts de la tranche 5 (JOURNAL, entrée 91),
à jour, conformes aux contrats, chiffrées comme le service de facturation les chiffre, et
cohérentes avec le manuel de v3."""

from __future__ import annotations

import base64
import filecmp
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import yaml
from ease.chargement import racine_depot
from ease.contrats.devis import Devis
from ease.contrats.tarif import Tarif

RACINE = racine_depot()
V2 = RACINE / "05_pme" / "societes" / "calorelle" / "v2"
V3 = RACINE / "05_pme" / "societes" / "calorelle" / "v3"
HORLOGE = datetime.fromisoformat("2026-11-02T09:00:00+01:00")
DEVIS = [
    Devis.model_validate_json(p.read_text(encoding="utf-8"))
    for p in sorted((V3 / "facturation" / "devis").glob("*.json"))
]


def _fichiers(racine: Path) -> set[Path]:
    return {p.relative_to(racine) for p in racine.rglob("*") if p.is_file()}


def test_les_donnees_v3_sont_celles_du_generateur() -> None:
    script = RACINE / "09_outillage" / "scripts" / "generer_donnees_v3.py"
    resultat = subprocess.run([sys.executable, str(script), "--verifier"], capture_output=True, text=True, cwd=RACINE)
    assert resultat.returncode == 0, resultat.stderr


def test_v3_est_v2_plus_la_facturation_le_manuel_la_fiche_et_les_devis_refaits() -> None:
    for partie in ("messagerie", "planning"):
        assert _fichiers(V2 / partie) == _fichiers(V3 / partie)
        assert all(filecmp.cmp(V2 / partie / p, V3 / partie / p, shallow=False) for p in _fichiers(V2 / partie))
    dossiers = _fichiers(V2 / "dossiers")
    assert _fichiers(V3 / "dossiers") == dossiers | {Path("commun/fiche_entreprise.md")}
    changes = {str(p) for p in dossiers if not filecmp.cmp(V2 / "dossiers" / p, V3 / "dossiers" / p, shallow=False)}
    attendus = {"commun/manuel_procedures.md"} | {
        f"commercial/devis/{d.numero[3:7]}/{d.numero.lower()}.pdf" for d in DEVIS
    }
    assert changes == attendus
    assert (V3 / "dossiers" / "commun" / "manuel_procedures.md").read_bytes() == (
        V3 / "entreprise" / "manuel_procedures.md"
    ).read_bytes()
    assert (V3 / "dossiers" / "commun" / "fiche_entreprise.md").read_bytes() == (
        V3 / "entreprise" / "fiche_entreprise.md"
    ).read_bytes()
    assert {str(p) for p in _fichiers(V3 / "facturation")} == {"tarif.json"} | {f"devis/{d.numero}.json" for d in DEVIS}


def test_le_tarif_et_les_vingt_deux_devis_respectent_leurs_contrats() -> None:
    tarif = Tarif.model_validate_json((V3 / "facturation" / "tarif.json").read_text(encoding="utf-8"))
    codes = [ligne.code for ligne in tarif.lignes]
    assert len(codes) == len(set(codes))
    assert [d.numero for d in DEVIS] == [f"DV-2025-{i:03d}" for i in range(1, 11)] + [
        f"DV-2026-{i:03d}" for i in range(1, 13)
    ]
    for d in DEVIS:
        fiche = cast(
            dict[str, Any],
            yaml.safe_load((V3 / "dossiers" / "clients" / d.client / "fiche_client.yaml").read_text(encoding="utf-8")),
        )
        assert d.cree_par == fiche["charge_d_affaires"], d.numero
        assert all(ligne.code in codes for ligne in d.lignes)
        assert (d.envoye_le is None) == (d.statut == "brouillon"), d.numero
        assert (d.reponse_le is None) == (d.statut in {"brouillon", "envoye"}), d.numero
        assert d.cree_le <= (d.envoye_le or d.cree_le) <= (d.reponse_le or d.envoye_le or d.cree_le) < HORLOGE


def test_le_service_de_facturation_chiffre_et_imprime_les_devis_a_l_identique() -> None:
    """Chaque devis de l'état initial, rechiffré par le code du service (TypeScript) : mêmes totaux,
    mêmes lignes, même PDF à l'octet près."""
    entree = [
        {
            "devis": json.loads((V3 / "facturation" / "devis" / f"{d.numero}.json").read_text(encoding="utf-8")),
            "client": yaml.safe_load(
                (V3 / "dossiers" / "clients" / d.client / "fiche_client.yaml").read_text(encoding="utf-8")
            ),
        }
        for d in DEVIS
    ]
    script = """
import { readFileSync } from "node:fs";
import { pdfUnePage } from "./05_pme/commun/src/pdf.ts";
import { chiffrer } from "./05_pme/facturation/src/chiffrage.ts";
import { lignesPdfDevis } from "./05_pme/facturation/src/serveur.ts";
const tarif = JSON.parse(readFileSync("05_pme/societes/calorelle/v3/facturation/tarif.json", "utf-8"));
const entree = JSON.parse(readFileSync(0, "utf-8"));
const sortie = entree.map(({ devis, client }) => ({
  chiffrage: chiffrer(tarif, devis.lignes, devis.remise_pourcent),
  pdf: Buffer.from(pdfUnePage(lignesPdfDevis(devis, { nom: client.nom, adresse: client.adresse ?? "" })))
    .toString("base64"),
}));
process.stdout.write(JSON.stringify(sortie));
"""
    resultat = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(entree),
        capture_output=True,
        text=True,
        cwd=RACINE,
    )
    assert resultat.returncode == 0, resultat.stderr
    for d, calcul in zip(DEVIS, json.loads(resultat.stdout), strict=True):
        enregistre = d.model_dump(
            mode="json", include={"lignes", "total_ht_euros", "total_tva_euros", "total_ttc_euros"}
        )
        assert calcul["chiffrage"] == enregistre, d.numero
        pdf = V3 / "dossiers" / "commercial" / "devis" / d.numero[3:7] / f"{d.numero.lower()}.pdf"
        assert base64.b64decode(calcul["pdf"]) == pdf.read_bytes(), d.numero


def test_les_devis_a_relancer_sont_loin_de_la_limite_des_30_jours() -> None:
    """Au lundi 2 novembre 2026 : trois devis envoyés sans réponse depuis plus de 30 jours, trois
    depuis moins ; aucun à moins de trois jours de la limite, pour qu'aucune lecture de « plus de
    30 jours » ne change la liste."""
    envoyes = [d for d in DEVIS if d.statut == "envoye"]
    assert all(d.envoye_le is not None for d in envoyes)
    ages = {d.numero: HORLOGE - cast(datetime, d.envoye_le) for d in envoyes}
    assert {n for n, a in ages.items() if a > timedelta(days=30)} == {"DV-2026-004", "DV-2026-008", "DV-2026-009"}
    assert {n for n, a in ages.items() if a < timedelta(days=30)} == {"DV-2026-010", "DV-2026-011", "DV-2026-012"}
    assert all(abs(a - timedelta(days=30)) > timedelta(days=3) for a in ages.values())


def _type_client(code: str) -> str:
    fiche = yaml.safe_load((V3 / "dossiers" / "clients" / code / "fiche_client.yaml").read_text(encoding="utf-8"))
    return str(cast(dict[str, Any], fiche)["type"])


def test_les_taux_de_tva_suivent_la_section_6_du_manuel_de_v3() -> None:
    """Pompe à chaleur air-eau : 5,5 % sur tout ; chaudière au gaz, collective ou non : 20 % sur
    tout, depuis le 1er mars 2025 ; climatisation dans un local professionnel : 20 % sur tout ;
    chez un particulier avant le 18 juillet 2026, l'appareil à 20 % et l'installation à 10 %
    (JOURNAL, entrée 99)."""
    for d in DEVIS:
        par_code = {ligne.code: ligne.taux_tva for ligne in d.lignes}
        if d.objet == "Pompe à chaleur air-eau":
            assert set(par_code.values()) == {5.5}, d.numero
        elif d.objet == "Climatisation réversible" and _type_client(d.client) == "particulier":
            assert str(d.cree_le)[:10] < "2026-07-18", d.numero
            assert {c: t for c, t in par_code.items() if c.startswith("CLI-")} == {"CLI-01": 20, "CLI-02": 20}
            assert {t for c, t in par_code.items() if not c.startswith("CLI-")} == {10}, d.numero
        else:
            assert set(par_code.values()) == {20}, d.numero
            assert str(d.cree_le)[:10] >= "2025-03-01", d.numero
    manuel = " ".join((V3 / "entreprise" / "manuel_procedures.md").read_text(encoding="utf-8").split())
    for regle in (
        "5,5 % : pompe à chaleur air-eau, ballon thermodynamique, thermostat",
        "depuis le 18 juillet 2026 (arrêté du 13 juillet 2026), pompe à chaleur air-air réversible fixe",
        "20 % : depuis le 1er mars 2025 (loi de finances pour 2025), chaudière au gaz ou au fioul",
        "10 % : les autres travaux",
    ):
        assert regle in manuel, regle


def test_le_manuel_et_la_fiche_de_v3_portent_les_regles_de_la_tranche_5() -> None:
    manuel = " ".join((V3 / "entreprise" / "manuel_procedures.md").read_text(encoding="utf-8").split())
    for regle in (
        "enregistre dans le logiciel de facturation l'envoi de chaque devis, puis la réponse du client",
        "Une remise sur un devis est décidée par la gérante seule.",
        "sans réponse plus de 30 jours après son envoi est relancé une fois",
        "enregistre l'acceptation et demande au responsable planning",
        "Une demande venue d'ailleurs reçoit un refus poli",
        "un repas, 20,00 € au plus ; un kilomètre fait avec son propre véhicule, 0,45 €",
        "`rh/salaries/<prénom.nom>/`",
    ):
        assert regle in manuel, regle
    fiche = (V3 / "entreprise" / "fiche_entreprise.md").read_text(encoding="utf-8")
    assert "## Zone d'intervention" in fiche and "Loiret (45)" in fiche


def test_le_pdf_du_service_encode_comme_le_codec_cp1252_de_python() -> None:
    """Chaque caractère que Python sait écrire en Windows-1252, le service l'écrit au même octet."""
    attendus: dict[str, int] = {}
    for octet in range(0x20, 0x100):
        try:
            attendus[bytes([octet]).decode("cp1252")] = octet
        except UnicodeDecodeError:
            continue
    script = """
import { readFileSync } from "node:fs";
import { cp1252 } from "./05_pme/commun/src/pdf.ts";
const caracteres = JSON.parse(readFileSync(0, "utf-8"));
process.stdout.write(JSON.stringify(caracteres.map((c) => cp1252(c)[0])));
"""
    resultat = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(list(attendus)),
        capture_output=True,
        text=True,
        cwd=RACINE,
    )
    assert resultat.returncode == 0, resultat.stderr
    assert json.loads(resultat.stdout) == list(attendus.values())


def test_les_numeros_des_devis_suivent_l_ordre_de_leur_creation() -> None:
    """Comme le service numérote : un agent peut juger du plus récent par le numéro."""
    for annee in ("2025", "2026"):
        de_l_annee = [d for d in DEVIS if d.numero[3:7] == annee]
        assert [d.numero for d in sorted(de_l_annee, key=lambda d: d.cree_le)] == [d.numero for d in de_l_annee]
