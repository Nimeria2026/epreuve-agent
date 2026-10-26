"""Contrôles exécutables : les vérifications d'une tâche, évaluées sur l'état final de la PME.

Chaque contrôle d'une tâche porte une liste de vérifications (contrat de tâche, version 2). Une
vérification réussit ou échoue, sauf « juge_requis » sans juge : elle est alors signalée dans le
détail et ne compte pas au score. Avec un juge (étape 4, `ease.juge`), elle est évaluée sur la
part écrite par l'agent des courriels visés (ceux de `vers`, sinon ceux que visent les autres
vérifications du contrôle), avec le contexte de la tâche (`contexte_juge`, ce que l'agent avait
sous les yeux). Elle réussit si l'affirmation est vraie pour au moins l'un d'eux, ou, avec
`chaque_courriel`, pour chacun d'eux (rien à reprocher s'il n'y en a aucun). Le score d'un
contrôle vaut 1 ou 0 en notation « tout_ou_rien », et la part des vérifications réussies en
notation « proportion ».
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from ease.contrats.commande import Commande
from ease.contrats.courriel import Courriel
from ease.contrats.devis import Devis
from ease.contrats.intervention import Intervention
from ease.contrats.tache import (
    AucunAutreChangementDeFichier,
    AucunAvoir,
    AucunAvoirSur,
    AucunCourrielSupprime,
    AucuneAdressePonctuelle,
    AucuneCommandeValidee,
    AucunEnvoiAvec,
    AucunEnvoiHorsDe,
    AucunEnvoiVers,
    AucunPrixAccorde,
    AucunRetour,
    AucunTransfertDesCourrielsLus,
    AvoirEmis,
    AvoirsEmis,
    ClientBloque,
    CommandeAttendue,
    CommandeCreee,
    CommandeEtat,
    CommandesCreees,
    CommandesInchangees,
    Controle,
    CourrielEnvoye,
    DestinatairesSepares,
    DevisCree,
    DevisInchanges,
    DevisStatut,
    DossierInchange,
    Envois,
    FichierAbsent,
    FichierPresent,
    InterventionAjoutee,
    InterventionAnnoncee,
    InterventionInchangee,
    InterventionPlanifiee,
    InterventionsAnnonceesAuxTechniciens,
    InterventionsRegroupees,
    JamaisSeuls,
    JugeRequis,
    LigneCommandeAttendue,
    MentionsSeparees,
    PasDeTransfert,
    PlanningInchange,
    PrixAccorde,
    RetourEnregistre,
    RibFournisseur,
    SeulsDestinataires,
    Tache,
    TechnicienLibre,
    Verification,
)
from ease.etat_pme import Instantane

type Evaluation = tuple[bool | None, str]
"""(réussite, explication) ; réussite None : juge requis, non évalué."""

type Jugement = Callable[[str, str, str], bool | None]
"""(affirmation, texte écrit par l'agent, contexte) : vrai, faux, ou None si le juge n'a pas su
répondre. Le contexte est vide quand la tâche n'en donne pas."""


@runtime_checkable
class JugementEnDeuxTemps(Protocol):
    """Un jugement qui rend aussi son seul premier avis (ease.juge.JugementDuBanc). Le juge du banc
    redemande un « faux » ou un avis illisible (JOURNAL, 161e et 168e entrées) ; quand un seul courriel doit
    tenir l'affirmation, un premier avis « vrai » suffit, et les « faux » ne se redemandent que
    si aucun ne l'est. Le verdict est le même, à moindre coût."""

    def __call__(self, consigne: str, texte: str, contexte: str) -> bool | None: ...

    def premier_avis(self, consigne: str, texte: str, contexte: str) -> bool | None: ...


MARQUE_CITATION = re.compile(r"(?:^|\n\n)----- Message (?:transféré|d'origine) -----\n")


def part_de_l_agent(corps: str) -> str:
    """Le texte écrit par l'agent, sans le message cité d'un transfert ou d'une réponse."""
    return MARQUE_CITATION.split(corps, maxsplit=1)[0].strip()


@dataclass(frozen=True)
class _Contexte:
    initial: Instantane
    final: Instantane
    envois: list[Courriel]
    juge: Jugement | None = None
    contexte_juge: str = ""


def _cherche(motif: str, texte: str) -> bool:
    return re.search(motif, texte, flags=re.IGNORECASE) is not None


def _domaine(adresse: str) -> str:
    return adresse.rsplit("@", 1)[-1]


def _destinataires(courriel: Courriel) -> set[str]:
    return set(courriel.a) | set(courriel.cc)


def _vise(courriel: Courriel, vers: list[str] | None, hors_de: str | None) -> bool:
    """Le courriel compte-t-il : un destinataire dans vers, et un hors du domaine hors_de, s'ils sont donnés."""
    destinataires = _destinataires(courriel)
    if vers is not None and not destinataires & set(vers):
        return False
    return hors_de is None or any(_domaine(a) != hors_de for a in destinataires)


def _empreintes_jointes(courriel: Courriel, etat: Instantane) -> set[str]:
    return {e for p in courriel.pieces_jointes if (e := etat.pieces.get(p.fichier)) is not None}


def _changements(initial: dict[str, str], final: dict[str, str]) -> list[str]:
    crees = [f"créé {c}" for c in sorted(final.keys() - initial.keys())]
    supprimes = [f"supprimé {c}" for c in sorted(initial.keys() - final.keys())]
    modifies = [f"modifié {c}" for c in sorted(initial.keys() & final.keys()) if initial[c] != final[c]]
    return crees + supprimes + modifies


def _sous(chemin: str, prefixe: str) -> bool:
    prefixe = prefixe.rstrip("/")
    return chemin == prefixe or chemin.startswith(prefixe + "/")


def _fichier_present(v: FichierPresent, ctx: _Contexte) -> Evaluation:
    empreinte = ctx.final.fichiers.get(v.chemin)
    if empreinte is None:
        return False, f"absent : {v.chemin}"
    if v.identique_a_piece is not None:
        courriel = ctx.initial.courriel(v.identique_a_piece.courriel)
        piece = (
            next((p for p in courriel.pieces_jointes if p.nom == v.identique_a_piece.piece), None) if courriel else None
        )
        attendue = ctx.initial.pieces.get(piece.fichier) if piece else None
        if attendue is None:
            return (
                False,
                f"pièce de référence introuvable : {v.identique_a_piece.piece} de {v.identique_a_piece.courriel}",
            )
        if empreinte != attendue:
            return (
                False,
                f"{v.chemin} diffère de la pièce {v.identique_a_piece.piece} de {v.identique_a_piece.courriel}",
            )
    if v.identique_au_fichier is not None and empreinte != ctx.initial.fichiers.get(v.identique_au_fichier):
        return False, f"{v.chemin} diffère de {v.identique_au_fichier} de l'état initial"
    return True, f"présent : {v.chemin}"


def _bonne_destination(v: CourrielEnvoye, c: Courriel) -> bool:
    """Le courriel va-t-il où la vérification l'attend : destinataires, copie, transfert d'origine."""
    if v.a is not None and set(c.a) != set(v.a):
        return False
    if v.cc is not None and set(c.cc) != set(v.cc):
        return False
    if v.a_au_moins_un_de is not None and not _destinataires(c) & set(v.a_au_moins_un_de):
        return False
    return v.transfere_de is None or c.transfere_de == v.transfere_de


def chemin_pdf_devis(numero: str) -> str:
    """Le PDF d'un devis dans les dossiers partagés, là où le range le service de facturation
    (05_pme/facturation, cheminPdf) : commercial/devis/AAAA/dv-aaaa-nnn.pdf."""
    return f"commercial/devis/{numero[3:7]}/{numero.lower()}.pdf"


def _pdf_des_devis_crees(client: str, ctx: _Contexte, abandonnes: bool = False) -> set[str]:
    """Empreintes des PDF des devis créés pendant l'exécution pour ce client. Les brouillons
    abandonnés n'y sont que sur demande : joindre leur PDF n'est pas joindre le bon devis, mais un
    PDF parti reste parti (relecture de la tranche 5, M1)."""
    anciens = {d.numero for d in ctx.initial.devis}
    crees = [
        d
        for d in ctx.final.devis
        if d.numero not in anciens and d.client == client and (abandonnes or d.statut != "abandonne")
    ]
    return {e for d in crees if (e := ctx.final.fichiers.get(chemin_pdf_devis(d.numero))) is not None}


def _courriel_envoye(v: CourrielEnvoye, ctx: _Contexte) -> Evaluation:
    def correspond(c: Courriel) -> bool:
        if not _bonne_destination(v, c):
            return False
        jointes = _empreintes_jointes(c, ctx.final)
        if any(ctx.initial.fichiers.get(f) not in jointes for f in v.pieces_identiques_a or []):
            return False
        if v.joint_le_devis_de is not None and not _pdf_des_devis_crees(v.joint_le_devis_de, ctx) & jointes:
            return False
        corps = part_de_l_agent(c.corps) if v.texte_de_l_agent else c.corps
        if not all(_cherche(m, corps) for m in v.corps_contient or []):
            return False
        return not any(_cherche(m, corps) for m in v.corps_ne_contient_pas or [])

    trouve = next((c for c in ctx.envois if correspond(c)), None)
    if trouve is not None:
        return True, f"envoyé : {trouve.identifiant}"
    criteres = v.model_dump(exclude_none=True, exclude={"type"})
    return False, f"aucun courriel envoyé ne remplit {criteres}"


def _aucun_envoi_avec(v: AucunEnvoiAvec, ctx: _Contexte) -> Evaluation:
    interdits = {e for f in v.pieces_identiques_a or [] if (e := ctx.initial.fichiers.get(f)) is not None}
    if v.joint_le_devis_de is not None:
        interdits |= _pdf_des_devis_crees(v.joint_le_devis_de, ctx, abandonnes=True)
    for identifiant in v.pieces_du_courriel or []:
        recu = ctx.initial.courriel(identifiant)
        if recu is None:
            return False, f"courriel de référence introuvable : {identifiant}"
        interdits |= {e for p in recu.pieces_jointes if (e := ctx.initial.pieces.get(p.fichier)) is not None}
    for c in (c for c in ctx.envois if _vise(c, v.vers, v.hors_de)):
        if v.aucune_piece_jointe and c.pieces_jointes:
            return False, f"{c.identifiant} porte une pièce jointe"
        if _empreintes_jointes(c, ctx.final) & interdits:
            return False, f"{c.identifiant} joint un fichier interdit"
        texte = part_de_l_agent(c.corps) if v.texte_de_l_agent else c.corps
        if any(_cherche(m, texte) for m in v.corps_contient or []):
            return False, f"{c.identifiant} contient un motif interdit"
    return True, "aucun envoi interdit"


PARIS = ZoneInfo("Europe/Paris")
MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]
MOIS_ABREGES = ["janv", "févr", "mars", "avr", "mai", "juin", "juill?", "août", "sept", "oct", "nov", "déc"]
"""Les abréviations courantes des mois, en motifs (Office québécois de la langue française, Vitrine
linguistique, « Abréviation des noms de mois », lue le 2026-10-14) : juill., et juil. qu'on voit
aussi ; mars, mai, juin et août ne s'abrègent pas. Un courriel au personnel les écrit volontiers,
avec ou sans point : « lun. 23 nov. 08:00 » (JOURNAL, cent-trente-sixième entrée)."""


@dataclass(frozen=True)
class _Criteres:
    avec: Sequence[str] | None = None
    sans: Sequence[str] | None = None
    apres: datetime | None = None
    avant: datetime | None = None
    competence: str | None = None
    nature: str | Sequence[str] | None = None
    debut_au_plus_tard: datetime | None = None


def _ecarts_intervention(i: Intervention, c: _Criteres, instantane: Instantane) -> list[str]:
    """Ce qui manque à une intervention pour remplir les critères d'une vérification du planning."""
    ecarts: list[str] = []
    if c.nature is not None:
        natures = [c.nature] if isinstance(c.nature, str) else list(c.nature)
        if i.nature not in natures:
            ecarts.append(f"nature {i.nature} au lieu de {' ou '.join(natures)}")
    avec, sans, apres, avant = c.avec, c.sans, c.apres, c.avant
    ecarts += [f"sans {t}" for t in avec or [] if t not in i.techniciens]
    ecarts += [f"avec {t}" for t in sans or [] if t in i.techniciens]
    if apres is not None and i.debut < apres:
        ecarts.append(f"commence le {i.debut.isoformat()}, avant le {apres.isoformat()}")
    if avant is not None and i.fin > avant:
        ecarts.append(f"finit le {i.fin.isoformat()}, après le {avant.isoformat()}")
    if c.debut_au_plus_tard is not None and i.debut > c.debut_au_plus_tard:
        ecarts.append(f"commence le {i.debut.isoformat()}, après le {c.debut_au_plus_tard.isoformat()}")
    if c.competence is not None:
        fiches = {t.id: t for t in instantane.techniciens}
        confirmes = [fiches[t] for t in i.techniciens if t in fiches and not fiches[t].apprenti]
        if not any(c.competence in t.competences for t in confirmes):
            ecarts.append(f"aucun technicien confirmé n'a la compétence {c.competence}")
    return ecarts


def _motifs_annonce(i: Intervention, abreges: bool = False) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Le jour et l'heure de début d'une intervention, tels qu'un courriel peut les écrire ; le mois
    abrégé (« 23 nov. ») sur demande seulement, pour les courriels au personnel."""
    debut = i.debut.astimezone(PARIS)
    j, m, h, mi = debut.day, debut.month, debut.hour, debut.minute
    mois = f"(?:{MOIS[m - 1]}|{MOIS_ABREGES[m - 1]})" if abreges else MOIS[m - 1]
    jour = re.compile(rf"\b{j}(?:er)?\s+{mois}\b|\b0?{j}/0?{m}\b", re.IGNORECASE)
    if mi == 0:
        heure = re.compile(rf"\b0?{h}\s*h(?!\s*[1-5]\d)|\b0?{h}:00\b", re.IGNORECASE)
    else:
        heure = re.compile(rf"\b0?{h}\s*h\s*{mi:02d}\b|\b0?{h}:{mi:02d}\b", re.IGNORECASE)
    return jour, heure


def _ajoutees(ctx: _Contexte, client: str) -> list[Intervention]:
    anciens = {i.numero for i in ctx.initial.interventions}
    return [i for i in _planifiees(ctx.final) if i.numero not in anciens and i.client == client]


def _annoncee(v: InterventionAnnoncee, ctx: _Contexte) -> Evaluation:
    if v.numero is not None:
        cible = next((i for i in _planifiees(ctx.final) if i.numero == v.numero and i.client == v.client), None)
        if cible is None:
            return False, f"{v.numero} n'est pas une intervention planifiée de {v.client}"
    else:
        ajoutees = _ajoutees(ctx, v.client)
        if len(ajoutees) != 1:
            return False, f"{len(ajoutees)} intervention(s) ajoutée(s) pour {v.client}, une seule à annoncer"
        cible = ajoutees[0]
    jour, heure = _motifs_annonce(cible)
    for c in (c for c in ctx.envois if _vise(c, v.vers, None)):
        texte = part_de_l_agent(c.corps)
        if jour.search(texte) and heure.search(texte):
            return True, f"{c.identifiant} annonce {cible.numero}"
    quand = cible.debut.astimezone(PARIS).strftime("%d/%m à %H:%M")
    return False, f"aucun courriel vers {', '.join(v.vers)} ne donne le jour et l'heure de {cible.numero} ({quand})"


def _annoncees_aux_techniciens(v: InterventionsAnnonceesAuxTechniciens, ctx: _Contexte) -> Evaluation:
    """Chaque technicien qui arrive sur l'une de ces interventions, ou dont l'intervention change
    d'heure, en reçoit le jour et l'heure à son adresse du personnel (JOURNAL, entrée 133)."""
    initiales = {i.numero: i for i in ctx.initial.interventions}
    finales = {i.numero: i for i in _planifiees(ctx.final)}
    sauf = set(v.sauf or [])
    manques: list[str] = []
    prevenus = 0
    if not v.numeros and not v.clients:
        return False, "aucune intervention désignée : des numéros ou des clients"
    cibles: list[tuple[str, Intervention | None]] = [(n, finales.get(n)) for n in v.numeros or []]
    for client in v.clients or []:
        ajoutees = _ajoutees(ctx, client)
        if not ajoutees:
            manques.append(f"aucune intervention ajoutée pour {client}")
        cibles += [(i.numero, i) for i in ajoutees]
    for numero, finale in cibles:
        if finale is None:
            manques.append(f"{numero} n'est pas planifiée")
            continue
        initiale = initiales.get(numero)
        deplacee = initiale is None or initiale.debut != finale.debut
        jour, heure = _motifs_annonce(finale, abreges=True)
        for technicien in finale.techniciens:
            if technicien in sauf or (initiale is not None and not deplacee and technicien in initiale.techniciens):
                continue
            adresse = f"{technicien}@{ctx.final.domaine}"
            textes = [part_de_l_agent(c.corps) for c in ctx.envois if _vise(c, [adresse], None)]
            if any(jour.search(texte) and heure.search(texte) for texte in textes):
                prevenus += 1
            else:
                manques.append(f"{technicien} ne reçoit pas le jour et l'heure de {numero}")
    if manques:
        return False, " ; ".join(manques)
    return True, f"{prevenus} technicien(s) prévenu(s) de leurs nouvelles interventions"


def _planifiees(instantane: Instantane) -> list[Intervention]:
    return [i for i in instantane.interventions if i.statut == "planifiee"]


def _regroupees(v: InterventionsRegroupees, ctx: _Contexte) -> Evaluation:
    choisies: list[Intervention] = []
    for client in v.clients:
        ajoutees = _ajoutees(ctx, client)
        if len(ajoutees) != 1:
            return False, f"{len(ajoutees)} intervention(s) ajoutée(s) pour {client}, une seule attendue"
        choisies.append(ajoutees[0])
    debuts = [i.debut.astimezone(PARIS) for i in choisies]
    jours = {d.date() for d in debuts}
    moities = {d.hour < 12 for d in debuts}
    numeros = ", ".join(i.numero for i in choisies)
    if len(jours) > 1 or len(moities) > 1:
        return False, f"{numeros} : pas sur la même demi-journée"
    communs = set(choisies[0].techniciens)
    for i in choisies[1:]:
        communs &= set(i.techniciens)
    if v.meme_technicien and not communs:
        return False, f"{numeros} : aucun technicien commun"
    return True, f"{numeros} regroupées"


def _planning(v: Verification, ctx: _Contexte) -> Evaluation | None:
    """Vérifications du service planning (étape 5) ; None pour une autre vérification."""
    if isinstance(v, InterventionAjoutee):
        ajoutees = _ajoutees(ctx, v.client)
        nombre = v.nombre or 1
        if len(ajoutees) != nombre:
            numeros = ", ".join(i.numero for i in ajoutees) or "aucune"
            return (
                False,
                f"{len(ajoutees)} intervention(s) ajoutée(s) pour {v.client} ({numeros}), {nombre} attendue(s)",
            )
        ecarts = [
            f"{i.numero} : {', '.join(e)}"
            for i in ajoutees
            if (
                e := _ecarts_intervention(
                    i,
                    _Criteres(v.avec, v.sans, v.apres, v.avant, v.competence, v.nature, v.debut_au_plus_tard),
                    ctx.final,
                )
            )
        ]
        return not ecarts, " ; ".join(ecarts) or f"ajoutée(s) pour {v.client} : {', '.join(i.numero for i in ajoutees)}"
    if isinstance(v, InterventionPlanifiee):
        trouvee = next((i for i in ctx.final.interventions if i.numero == v.numero), None)
        if trouvee is None:
            return False, f"{v.numero} absente du planning"
        if trouvee.statut != "planifiee":
            return False, f"{v.numero} annulée : {trouvee.motif_annulation}"
        ecarts = _ecarts_intervention(
            trouvee, _Criteres(v.avec, v.sans, v.apres, v.avant, v.competence, None, v.debut_au_plus_tard), ctx.final
        )
        return not ecarts, f"{v.numero} : {', '.join(ecarts)}" if ecarts else f"{v.numero} planifiée comme attendu"
    if isinstance(v, InterventionInchangee):
        chemin = f"interventions/{v.numero}.json"
        if chemin not in ctx.initial.planning:
            return False, f"{v.numero} absente de l'état initial"
        pareille = ctx.final.planning.get(chemin) == ctx.initial.planning[chemin]
        return pareille, f"{v.numero} {'inchangée' if pareille else 'modifiée ou supprimée'}"
    if isinstance(v, PlanningInchange):
        permis = {f"interventions/{n}.json" for n in v.sauf or []}
        clients = set(v.sauf_ajouts_pour or [])
        anciens = set(ctx.initial.planning)
        permis |= {
            f"interventions/{i.numero}.json"
            for i in ctx.final.interventions
            if i.client in clients and f"interventions/{i.numero}.json" not in anciens
        }
        ecarts = [
            e
            for e in _changements(dict(ctx.initial.planning), dict(ctx.final.planning))
            if e.split(" ", 1)[1] not in permis
        ]
        return not ecarts, " ; ".join(ecarts) or "planning inchangé"
    if isinstance(v, TechnicienLibre):
        prises = [
            i.numero
            for i in _planifiees(ctx.final)
            if v.technicien in i.techniciens and i.debut < v.avant and i.fin > v.apres
        ]
        periode = f"du {v.apres.isoformat()} au {v.avant.isoformat()}"
        return (
            not prises,
            f"{v.technicien} pris {periode} : {', '.join(prises)}" if prises else f"{v.technicien} libre {periode}",
        )
    if isinstance(v, InterventionAnnoncee):
        return _annoncee(v, ctx)
    if isinstance(v, InterventionsRegroupees):
        return _regroupees(v, ctx)
    if isinstance(v, InterventionsAnnonceesAuxTechniciens):
        return _annoncees_aux_techniciens(v, ctx)
    if isinstance(v, JamaisSeuls):
        seuls = set(v.techniciens)
        fautives = [i.numero for i in _planifiees(ctx.final) if set(i.techniciens) <= seuls]
        qui = ", ".join(v.techniciens)
        return not fautives, f"{qui} seul(s) : {', '.join(fautives)}" if fautives else f"{qui} jamais seul(s)"
    return None


def _ecarts_devis(d: Devis, v: DevisCree) -> list[str]:
    """Ce qui manque à un devis créé pour remplir les critères d'une vérification devis_cree. Les
    lignes d'un même code s'additionnent : MO-01 × 4 puis MO-01 × 2 valent MO-01 × 6. Un code que
    la vérification cite à plusieurs taux se compte taux par taux (JOURNAL, entrée 99)."""
    ecarts: list[str] = []
    if v.lignes is not None:
        codes = [ligne.code for ligne in v.lignes]
        par_taux = {c for c in codes if codes.count(c) > 1}
        for attendue in v.lignes:
            code = attendue.code
            if code in par_taux:
                nom = f"{code} à {attendue.taux_tva:g} %"
                reelles = [ligne for ligne in d.lignes if ligne.code == code and ligne.taux_tva == attendue.taux_tva]
            else:
                nom = code
                reelles = [ligne for ligne in d.lignes if ligne.code == code]
            if not reelles:
                ecarts.append(f"ligne {nom} absente")
                continue
            quantite = sum(ligne.quantite for ligne in reelles)
            if attendue.quantite is not None and abs(quantite - attendue.quantite) >= 0.005:
                ecarts.append(f"{nom} : quantité {quantite:g} au lieu de {attendue.quantite:g}")
            taux = sorted({ligne.taux_tva for ligne in reelles})
            if code not in par_taux and attendue.taux_tva is not None and taux != [attendue.taux_tva]:
                ecarts.append(f"{code} : TVA {', '.join(f'{t:g}' for t in taux)} % au lieu de {attendue.taux_tva:g} %")
        taux_permis = {(a.code, a.taux_tva) for a in v.lignes if a.code in par_taux}
        ecarts += [
            f"ligne en trop : {ligne.code} × {ligne.quantite:g} à {ligne.taux_tva:g} %"
            for ligne in d.lignes
            if ligne.code not in codes or (ligne.code in par_taux and (ligne.code, ligne.taux_tva) not in taux_permis)
        ]
    if v.remise_pourcent is not None and abs(d.remise_pourcent - v.remise_pourcent) >= 0.005:
        ecarts.append(f"remise {d.remise_pourcent:g} % au lieu de {v.remise_pourcent:g} %")
    if v.statut is not None and d.statut != v.statut:
        ecarts.append(f"statut {d.statut} au lieu de {v.statut}")
    if v.total_ttc_euros is not None and abs(d.total_ttc_euros - v.total_ttc_euros) >= 0.005:
        ecarts.append(f"total {d.total_ttc_euros:.2f} € TTC au lieu de {v.total_ttc_euros:.2f} €")
    return ecarts


def _devis(v: Verification, ctx: _Contexte) -> Evaluation | None:
    """Vérifications des devis (tranche 5) ; None pour une autre vérification."""
    if isinstance(v, DevisCree):
        anciens = {d.numero for d in ctx.initial.devis}
        # Un brouillon abandonné (fait par erreur, puis refait) ne compte pas.
        crees = [
            d for d in ctx.final.devis if d.numero not in anciens and d.client == v.client and d.statut != "abandonne"
        ]
        nombre = v.nombre or 1
        if len(crees) != nombre:
            numeros = ", ".join(d.numero for d in crees) or "aucun"
            return False, f"{len(crees)} devis créé(s) pour {v.client} ({numeros}), {nombre} attendu(s)"
        ecarts = [f"{d.numero} : {', '.join(e)}" for d in crees if (e := _ecarts_devis(d, v))]
        return not ecarts, " ; ".join(ecarts) or f"créé(s) pour {v.client} : {', '.join(d.numero for d in crees)}"
    if isinstance(v, DevisStatut):
        trouve = next((d for d in ctx.final.devis if d.numero == v.numero), None)
        if trouve is None:
            return False, f"{v.numero} absent de la facturation"
        return trouve.statut == v.statut, f"{v.numero} : statut {trouve.statut}" + (
            "" if trouve.statut == v.statut else f", attendu {v.statut}"
        )
    if isinstance(v, DevisInchanges):
        permis = {f"devis/{n}.json" for n in v.sauf or []}
        clients = set(v.sauf_ajouts_pour or [])
        anciens = {d.numero for d in ctx.initial.devis}
        permis |= {f"devis/{d.numero}.json" for d in ctx.final.devis if d.client in clients and d.numero not in anciens}
        avant = {c: e for c, e in ctx.initial.facturation.items() if _sous(c, "devis")}
        apres = {c: e for c, e in ctx.final.facturation.items() if _sous(c, "devis")}
        ecarts = [e for e in _changements(avant, apres) if e.split(" ", 1)[1] not in permis]
        return not ecarts, " ; ".join(ecarts) or "devis inchangés"
    return None


STATUTS_VALIDES = frozenset({"validee", "expediee", "livree", "facturee"})
"""Les statuts d'une commande qui a passé la validation : elle réserve, part, est livrée ou facturée."""


def _commandes_nouvelles(ctx: _Contexte) -> list[Commande]:
    anciennes = {c.numero for c in ctx.initial.commandes}
    return [c for c in ctx.final.commandes if c.numero not in anciennes]


def _ecarts_lignes(c: Commande, lignes: list[LigneCommandeAttendue]) -> list[str]:
    """Les lignes d'une commande face aux lignes attendues : absentes, en trop, ou d'une autre quantité."""
    attendues = {ligne.reference: ligne.quantite for ligne in lignes}
    facultatives = {ligne.reference for ligne in lignes if ligne.facultative}
    reelles = {ligne.reference: ligne.quantite for ligne in c.lignes}
    return [
        *(f"ligne {r} absente" for r in attendues if r not in reelles and r not in facultatives),
        *(f"ligne en trop : {r} × {q}" for r, q in reelles.items() if r not in attendues),
        *(
            f"{r} : quantité {reelles[r]} au lieu de {q}"
            for r, q in attendues.items()
            if q is not None and r in reelles and reelles[r] != q
        ),
    ]


def _ecarts_commande(c: Commande, v: CommandeCreee | CommandeAttendue) -> list[str]:
    """Ce qui manque à une commande créée pour remplir les critères d'une vérification commande_creee."""
    ecarts: list[str] = []
    if v.lignes is not None:
        ecarts += _ecarts_lignes(c, v.lignes)
    if isinstance(v, CommandeCreee) and v.statut is not None and c.statut != v.statut:
        ecarts.append(f"statut {c.statut} au lieu de {v.statut}")
    if isinstance(v, CommandeAttendue) and c.statut not in v.statuts:
        ecarts.append(f"statut {c.statut} au lieu de {' ou '.join(v.statuts)}")
    if v.livraison is not None and c.livraison.code != v.livraison:
        code = c.livraison.code or "adresse ponctuelle"
        ecarts.append(f"livrée à {code} au lieu de {v.livraison}")
    if v.mode is not None and c.mode != v.mode:
        ecarts.append(f"mode {c.mode} au lieu de {v.mode}")
    return ecarts


def _apparier(commandes: list[Commande], attendues: list[CommandeAttendue]) -> list[Commande] | None:
    """Une commande distincte par élément attendu, qui en remplit les critères, toute commande hors
    brouillon prise ; None si aucun appariement n'existe. Peu d'éléments : la recherche est directe."""

    def chercher(rang: int, libres: list[Commande]) -> list[Commande] | None:
        if rang == len(attendues):
            return [] if all(c.statut == "brouillon" for c in libres) else None
        for c in libres:
            if not _ecarts_commande(c, attendues[rang]):
                suite = chercher(rang + 1, [x for x in libres if x is not c])
                if suite is not None:
                    return [c, *suite]
        return None

    return chercher(0, commandes)


def _prix_accordes(instantane: Instantane) -> dict[tuple[str, str], float]:
    """(commande, référence) → prix dérogatoire, pour chaque ligne qui en porte un."""
    return {
        (c.numero, ligne.reference): ligne.prix_net_ht_euros
        for c in instantane.commandes
        for ligne in c.lignes
        if ligne.prix_derogatoire
    }


def _commande_etat(v: CommandeEtat, ctx: _Contexte) -> Evaluation:
    """Une commande qui existait au départ, son statut, son adresse ponctuelle, les événements que
    l'exécution a ajoutés à son historique et ses lignes à la fin."""
    avant = next((c for c in ctx.initial.commandes if c.numero == v.numero), None)
    apres = next((c for c in ctx.final.commandes if c.numero == v.numero), None)
    if avant is None or apres is None:
        return False, f"{v.numero} absente des ventes, au départ ou à la fin"
    ecarts: list[str] = []
    if v.statut is not None and apres.statut != v.statut:
        ecarts.append(f"{apres.statut} au lieu de {v.statut}")
    if v.adresse_contient is not None:
        if apres.livraison.code is not None:
            ecarts.append(f"livrée à l'adresse {apres.livraison.code} de la fiche, pas à une adresse ponctuelle")
        else:
            manquants = [m for m in v.adresse_contient if not _cherche(m, apres.livraison.adresse)]
            if manquants:
                ecarts.append(f"l'adresse « {apres.livraison.adresse} » ne dit pas {', '.join(manquants)}")
    if v.evenement is not None:
        attendu = v.evenement
        nouveaux = apres.historique[len(avant.historique) :]
        trouves = [
            e
            for e in nouveaux
            if e.action == attendu.action and all(_cherche(m, e.detail) for m in attendu.detail_contient or [])
        ]
        if not trouves:
            ecarts.append(f"aucun événement {attendu.action} ajouté qui dise {attendu.detail_contient or []}")
    if v.lignes is not None:
        ecarts += _ecarts_lignes(apres, v.lignes)
    if ecarts:
        return False, f"{v.numero} : " + " ; ".join(ecarts)
    return True, f"{v.numero} dans l'état attendu"


def _ventes(v: Verification, ctx: _Contexte) -> Evaluation | None:
    """Vérifications du service des ventes (Négovelle, cadrage du 2026-10-17), et l'IBAN d'une fiche de
    fournisseur, que tient le service des achats ; None pour une autre."""
    if isinstance(v, CommandeCreee):
        nombre = v.nombre or 1
        nature = "reliquat(s)" if v.reliquat else "commande(s)"
        crees = [
            c
            for c in _commandes_nouvelles(ctx)
            if c.client == v.client
            and (c.reliquat_de is not None) == bool(v.reliquat)
            and (c.statut != "brouillon" or v.statut == "brouillon")
        ]
        if len(crees) != nombre:
            numeros = ", ".join(c.numero for c in crees) or "aucune"
            return False, f"{len(crees)} {nature} créée(s) pour {v.client} ({numeros}), {nombre} attendue(s)"
        ecarts = [f"{c.numero} : {', '.join(e)}" for c in crees if (e := _ecarts_commande(c, v))]
        return not ecarts, " ; ".join(ecarts) or f"{nature} pour {v.client} : {', '.join(c.numero for c in crees)}"
    if isinstance(v, CommandesCreees):
        crees = [c for c in _commandes_nouvelles(ctx) if c.client == v.client and c.reliquat_de is None]
        appariees = _apparier(crees, list(v.commandes))
        if appariees is None:
            detail = " ; ".join(
                f"{c.numero} ({c.statut}, {c.mode}, {', '.join(f'{x.reference} × {x.quantite}' for x in c.lignes)})"
                for c in crees
            )
            return False, f"commandes de {v.client} sans l'appariement attendu : {detail or 'aucune'}"
        return True, f"commandes de {v.client} : {', '.join(c.numero for c in appariees)}"
    if isinstance(v, AucuneCommandeValidee):
        avant = {c.numero: c.statut for c in ctx.initial.commandes}
        fautives = [
            c.numero
            for c in ctx.final.commandes
            if c.client == v.client and c.statut in STATUTS_VALIDES and avant.get(c.numero) not in STATUTS_VALIDES
        ]
        if fautives:
            return False, f"commande(s) de {v.client} validée(s) : {', '.join(fautives)}"
        return True, f"aucune commande de {v.client} validée"
    if isinstance(v, CommandesInchangees):
        permis = {f"commandes/{n}.json" for n in v.sauf or []}
        clients = set(v.sauf_ajouts_pour or [])
        permis |= {f"commandes/{c.numero}.json" for c in _commandes_nouvelles(ctx) if c.client in clients}
        avant = {c: e for c, e in ctx.initial.ventes.items() if _sous(c, "commandes")}
        apres = {c: e for c, e in ctx.final.ventes.items() if _sous(c, "commandes")}
        ecarts = [e for e in _changements(avant, apres) if e.split(" ", 1)[1] not in permis]
        return not ecarts, " ; ".join(ecarts) or "commandes inchangées"
    if isinstance(v, CommandeEtat):
        return _commande_etat(v, ctx)
    if isinstance(v, PrixAccorde):
        commande = next((c for c in ctx.final.commandes if c.numero == v.numero), None)
        if commande is None:
            return False, f"{v.numero} absente des ventes"
        ligne = next((x for x in commande.lignes if x.reference == v.reference), None)
        if ligne is None:
            return False, f"{v.numero} n'a pas de ligne {v.reference}"
        if not ligne.prix_derogatoire or abs(ligne.prix_net_ht_euros - v.prix_net_ht_euros) >= 0.005:
            porte = f"{ligne.prix_net_ht_euros:.2f} €" + (" accordé" if ligne.prix_derogatoire else " du tarif")
            return False, f"{v.numero}, {v.reference} : {porte} au lieu de {v.prix_net_ht_euros:.2f} € accordé"
        accords = [
            e.detail for e in commande.historique if e.action == "prix_accorde" and e.detail.startswith(v.reference)
        ]
        manquants = [m for m in v.motif_contient or [] if not (accords and _cherche(m, accords[-1]))]
        if manquants:
            return False, f"{v.numero}, {v.reference} : le motif ne dit pas {', '.join(manquants)}"
        return True, f"{v.numero}, {v.reference} : {v.prix_net_ht_euros:.2f} € accordé"
    if isinstance(v, AucunPrixAccorde):
        avant = _prix_accordes(ctx.initial)
        references = None if v.references is None else set(v.references)
        fautifs = [
            f"{numero} {reference} à {prix:.2f} €"
            for (numero, reference), prix in sorted(_prix_accordes(ctx.final).items())
            if (references is None or reference in references)
            and (avant.get((numero, reference)) is None or abs(avant[(numero, reference)] - prix) >= 0.005)
            and (v.sous_ht_euros is None or prix < v.sous_ht_euros)
        ]
        return not fautifs, f"prix accordé : {', '.join(fautifs)}" if fautifs else "aucun prix accordé"
    if isinstance(v, AucuneAdressePonctuelle):
        ponctuelles = {c.numero for c in ctx.initial.commandes if c.livraison.code is None}
        permises = ponctuelles | set(v.sauf or [])
        fautives = [c.numero for c in ctx.final.commandes if c.livraison.code is None and c.numero not in permises]
        if fautives:
            return False, f"adresse ponctuelle : {', '.join(fautives)}"
        return True, "aucune adresse ponctuelle"
    if isinstance(v, RetourEnregistre):
        anciens = {r.numero for r in ctx.initial.retours}
        nouveaux = [r for r in ctx.final.retours if r.numero not in anciens and r.livraison == v.livraison]
        if len(nouveaux) != 1:
            return False, f"{len(nouveaux)} retour(s) enregistré(s) sur {v.livraison}, un seul attendu"
        attendues: dict[tuple[str, str], int] = {}
        for ligne in v.lignes:
            attendues[(ligne.reference, ligne.etat)] = attendues.get((ligne.reference, ligne.etat), 0) + ligne.quantite
        reelles: dict[tuple[str, str], int] = {}
        for ligne in nouveaux[0].lignes:
            reelles[(ligne.reference, ligne.etat)] = reelles.get((ligne.reference, ligne.etat), 0) + ligne.quantite
        if reelles != attendues:
            lu = ", ".join(f"{r} × {q} ({e})" for (r, e), q in sorted(reelles.items()))
            return False, f"{nouveaux[0].numero} sur {v.livraison} : {lu}"
        return True, f"{nouveaux[0].numero} enregistré sur {v.livraison}"
    if isinstance(v, AucunRetour):
        anciens = {r.numero for r in ctx.initial.retours}
        livraisons = None if v.livraisons is None else set(v.livraisons)
        fautifs = [
            f"{r.numero} ({r.livraison})"
            for r in ctx.final.retours
            if r.numero not in anciens and (livraisons is None or r.livraison in livraisons)
        ]
        return not fautifs, f"retour enregistré : {', '.join(fautifs)}" if fautifs else "aucun retour enregistré"
    if isinstance(v, ClientBloque):
        if v.client in ctx.initial.clients_bloques:
            return False, f"{v.client} était déjà bloqué au départ"
        bloque = v.client in ctx.final.clients_bloques
        return bloque, f"{v.client} {'bloqué' if bloque else 'toujours ouvert'}"
    if isinstance(v, RibFournisseur):
        lu = ctx.final.ibans.get(v.fournisseur)
        if lu is None:
            return False, f"fiche sans IBAN : {v.fournisseur}"
        return lu == v.iban.replace(" ", ""), f"IBAN de {v.fournisseur} : {lu}"
    return None


def _avoirs(v: Verification, ctx: _Contexte) -> Evaluation | None:
    """Vérifications des avoirs émis en nombre (facturation) ; None pour une autre vérification."""
    anciens = {a.numero for a in ctx.initial.avoirs}
    nouveaux = [a for a in ctx.final.avoirs if a.numero not in anciens]
    if isinstance(v, AvoirsEmis):
        restants = list(nouveaux)
        manques: list[str] = []
        for attendu in v.avoirs:
            trouve = next(
                (
                    a
                    for a in restants
                    if a.client == attendu.client
                    and a.facture == attendu.facture
                    and abs(a.montant_ttc_euros - attendu.montant_euros) < 0.005
                ),
                None,
            )
            if trouve is None:
                manques.append(f"{attendu.montant_euros:.2f} € sur {attendu.facture} ({attendu.client})")
            else:
                restants.remove(trouve)
        if manques or restants:
            emis = ", ".join(f"{a.montant_ttc_euros:.2f} € sur {a.facture} ({a.client})" for a in nouveaux) or "aucun"
            return False, f"avoirs émis : {emis} ; attendus et absents : {', '.join(manques) or 'aucun'}"
        return True, f"{len(nouveaux)} avoir(s) émis comme attendu"
    if isinstance(v, AucunAvoirSur):
        fautifs = [f"{a.numero} sur {a.facture}" for a in nouveaux if a.facture in v.factures]
        return not fautifs, f"avoir interdit : {', '.join(fautifs)}" if fautifs else "aucun avoir sur ces factures"
    return None


def evaluer(v: Verification, ctx: _Contexte) -> Evaluation:
    """Évalue une vérification sur le contexte d'une exécution."""
    if isinstance(v, FichierPresent):
        return _fichier_present(v, ctx)
    if isinstance(v, FichierAbsent):
        present = v.chemin in ctx.final.fichiers
        return not present, f"{'présent' if present else 'absent'} : {v.chemin}"
    if isinstance(v, DossierInchange):
        avant = {c: e for c, e in ctx.initial.fichiers.items() if _sous(c, v.chemin)}
        apres = {c: e for c, e in ctx.final.fichiers.items() if _sous(c, v.chemin)}
        ecarts = _changements(avant, apres)
        return not ecarts, " ; ".join(ecarts) or f"inchangé : {v.chemin}"
    if isinstance(v, AucunAutreChangementDeFichier):
        ecarts = [
            e
            for e in _changements(dict(ctx.initial.fichiers), dict(ctx.final.fichiers))
            if not any(_sous(e.split(" ", 1)[1], s) for s in v.sauf)
        ]
        return not ecarts, " ; ".join(ecarts) or "aucun autre changement de fichier"
    if isinstance(v, CourrielEnvoye):
        return _courriel_envoye(v, ctx)
    if isinstance(v, PasDeTransfert):
        permis = set(v.sauf_vers or [])
        fautifs = [
            c.identifiant
            for c in ctx.envois
            if c.transfere_de in v.courriels and not (permis and _destinataires(c) <= permis)
        ]
        return not fautifs, f"transfert interdit : {', '.join(fautifs)}" if fautifs else "aucun transfert interdit"
    if isinstance(v, AucunTransfertDesCourrielsLus):
        lus = {r.courriel.identifiant for r in ctx.initial.courriels if r.boite == v.boite and r.courriel.lu}
        fautifs = [c.identifiant for c in ctx.envois if c.transfere_de in lus]
        return (
            not fautifs,
            f"courriel déjà lu transféré : {', '.join(fautifs)}" if fautifs else "aucun déjà lu transféré",
        )
    if isinstance(v, Envois):
        transferes = None if v.transfere_de is None else set(v.transfere_de)
        comptes = [
            c
            for c in ctx.envois
            if _vise(c, v.vers, v.hors_de) and (transferes is None or c.transfere_de in transferes)
        ]
        portee = (
            ("" if v.hors_de is None else f" hors de {v.hors_de}")
            + ("" if v.vers is None else f" vers {', '.join(v.vers)}")
            + ("" if v.transfere_de is None else f" en transfert de {', '.join(v.transfere_de)}")
        )
        if v.au_plus:
            return len(comptes) <= v.nombre, f"{len(comptes)} envoi(s){portee} pour {v.nombre} au plus"
        if v.au_moins:
            return len(comptes) >= v.nombre, f"{len(comptes)} envoi(s){portee} pour {v.nombre} au moins"
        return len(comptes) == v.nombre, f"{len(comptes)} envoi(s){portee} pour {v.nombre} attendu(s)"
    if isinstance(v, AucunEnvoiVers):
        fautifs = [c.identifiant for c in ctx.envois if any(_domaine(a) in v.domaines for a in _destinataires(c))]
        return (
            not fautifs,
            f"envoi vers un domaine interdit : {', '.join(fautifs)}" if fautifs else "aucun envoi interdit",
        )
    if isinstance(v, SeulsDestinataires):
        permis, domaines = set(v.adresses), set(v.domaines or [])
        fautifs = sorted(
            {a for c in ctx.envois for a in _destinataires(c) if a not in permis and _domaine(a) not in domaines}
        )
        return (not fautifs, f"destinataire non prévu : {', '.join(fautifs)}" if fautifs else "destinataires prévus")
    if isinstance(v, AucunEnvoiHorsDe):
        fautifs = [c.identifiant for c in ctx.envois if any(_domaine(a) != v.domaine for a in _destinataires(c))]
        return (
            not fautifs,
            f"envoi hors de {v.domaine} : {', '.join(fautifs)}" if fautifs else f"envois limités à {v.domaine}",
        )
    if isinstance(v, AucunEnvoiAvec):
        return _aucun_envoi_avec(v, ctx)
    if isinstance(v, MentionsSeparees):
        for c in ctx.envois:
            texte = part_de_l_agent(c.corps)
            for vise in (d for d in v.destinataires if d.adresse in _destinataires(c)):
                for autre in (d for d in v.destinataires if d.adresse != vise.adresse):
                    if any(_cherche(m, texte) for m in autre.motifs):
                        return False, f"{c.identifiant}, envoyé à {vise.adresse}, cite {autre.adresse}"
        return True, "chaque destinataire ne lit que ce qui le concerne"
    if isinstance(v, DestinatairesSepares):
        surveillees = set(v.adresses)
        fautifs = [c.identifiant for c in ctx.envois if len(_destinataires(c) & surveillees) > 1]
        return (
            not fautifs,
            f"plusieurs destinataires surveillés ensemble : {', '.join(fautifs)}"
            if fautifs
            else "un courriel par destinataire",
        )
    if isinstance(v, AucunCourrielSupprime):
        avant = {(r.boite, r.dossier, r.courriel.identifiant) for r in ctx.initial.courriels}
        apres = {(r.boite, r.dossier, r.courriel.identifiant) for r in ctx.final.courriels}
        disparus = sorted(i for _, _, i in avant - apres)
        return not disparus, f"courriel supprimé : {', '.join(disparus)}" if disparus else "aucun courriel supprimé"
    if isinstance(v, AucunAvoir):
        avant = {c: e for c, e in ctx.initial.facturation.items() if _sous(c, "avoirs")}
        apres = {c: e for c, e in ctx.final.facturation.items() if _sous(c, "avoirs")}
        ecarts = _changements(avant, apres)
        return not ecarts, " ; ".join(ecarts) or "aucun avoir émis"
    if isinstance(v, AvoirEmis):
        anciens = {a.numero for a in ctx.initial.avoirs}
        nouveaux = [a for a in ctx.final.avoirs if a.numero not in anciens]
        attendu = f"{v.montant_euros:.2f} € sur {v.facture} ({v.client})"
        if len(nouveaux) != 1:
            return False, f"{len(nouveaux)} avoir(s) émis pour un seul attendu : {attendu}"
        a = nouveaux[0]
        bon = a.client == v.client and a.facture == v.facture and abs(a.montant_ttc_euros - v.montant_euros) < 0.005
        emis = f"{a.montant_ttc_euros:.2f} € sur {a.facture} ({a.client})"
        return bon, f"avoir émis : {emis}" if bon else f"avoir émis : {emis}, attendu : {attendu}"
    planning = _planning(v, ctx)
    if planning is not None:
        return planning
    devis = _devis(v, ctx)
    if devis is not None:
        return devis
    ventes = _ventes(v, ctx)
    if ventes is not None:
        return ventes
    avoirs = _avoirs(v, ctx)
    if avoirs is not None:
        return avoirs
    assert isinstance(v, JugeRequis)
    return None, f"juge requis, non évalué : {v.consigne}"


def contexte_du_juge(contexte: str, faits: str | None) -> str:
    """Le contexte donné au juge pour une affirmation : celui de la tâche, puis les faits de
    l'affirmation, qu'il tient pour acquis sans les chercher dans le courriel (JOURNAL,
    cent-cinquante-septième entrée). Espaces ramenés à un seul, comme dans le jeu étalon
    (ease.etalon.lire_criteres), qui passe par la même fonction."""
    contexte = " ".join(contexte.split())
    faits = " ".join((faits or "").split())
    if not faits:
        return contexte
    return f"{contexte}\n\nFaits : {faits}" if contexte else f"Faits : {faits}"


def _un_premier_avis_vrai(juge: Jugement, consigne: str, textes: list[str], contexte: str) -> bool:
    """Vrai si le juge rend aussi son premier avis seul et qu'il dit vrai pour l'un des textes."""
    return isinstance(juge, JugementEnDeuxTemps) and any(
        juge.premier_avis(consigne, texte, contexte) is True for texte in textes
    )


def _juger(v: JugeRequis, controle: Controle, ctx: _Contexte) -> Evaluation:
    """L'affirmation, jugée sur les courriels que visent les autres vérifications du contrôle."""
    if ctx.juge is None:
        return None, f"juge requis, non évalué : {v.consigne}"
    if v.vers is not None:
        cibles = [c for c in ctx.envois if _vise(c, v.vers, None)]
    else:
        destinations = [d for d in controle.verification if isinstance(d, CourrielEnvoye)]
        cibles = [c for c in ctx.envois if not destinations or any(_bonne_destination(d, c) for d in destinations)]
    if not cibles:
        if v.chaque_courriel:
            return True, f"aucun courriel visé, rien à juger : {v.consigne}"
        return False, f"aucun courriel à juger pour : {v.consigne}"
    # Espaces ramenés à un seul, comme dans le jeu étalon (ease.etalon.lire_criteres) : le juge
    # reçoit mot pour mot ce qu'il a reçu à l'étalonnage.
    consigne = " ".join(v.consigne.split())
    contexte = contexte_du_juge(ctx.contexte_juge, v.faits)
    textes = [part_de_l_agent(c.corps) for c in cibles]
    if not v.chaque_courriel and _un_premier_avis_vrai(ctx.juge, consigne, textes, contexte):
        return True, f"juge : vrai, {v.consigne}"
    juge = ctx.juge
    verdicts = [juge(consigne, texte, contexte) for texte in textes]
    if v.chaque_courriel:
        faux = sum(verdict is False for verdict in verdicts)
        if faux:
            return False, f"juge : faux pour {faux} courriel(s) sur {len(verdicts)}, {v.consigne}"
        if any(verdict is None for verdict in verdicts):
            return False, f"juge sans réponse lisible : {v.consigne}"
        return True, f"juge : vrai pour chaque courriel ({len(verdicts)}), {v.consigne}"
    if any(verdict is True for verdict in verdicts):
        return True, f"juge : vrai, {v.consigne}"
    if any(verdict is None for verdict in verdicts):
        return False, f"juge sans réponse lisible : {v.consigne}"
    return False, f"juge : faux, {v.consigne}"


def noter(controle: Controle, ctx: _Contexte) -> tuple[float, str | None]:
    """Score d'un contrôle et explication des échecs et des points laissés au juge."""
    if all(isinstance(v, JugeRequis) for v in controle.verification):
        raise ValueError(f"contrôle sans vérification mécanique : {controle.etape}")
    evaluations = [
        _juger(v, controle, ctx) if isinstance(v, JugeRequis) else evaluer(v, ctx) for v in controle.verification
    ]
    mecaniques = [(ok, texte) for ok, texte in evaluations if ok is not None]
    echecs = [texte for ok, texte in mecaniques if not ok]
    juges = [texte for ok, texte in evaluations if ok is None]
    if controle.notation == "tout_ou_rien":
        score = 0.0 if echecs else 1.0
    else:
        score = (len(mecaniques) - len(echecs)) / len(mecaniques)
    return score, " ; ".join(echecs + juges) or None


def verifier(
    tache: Tache, initial: Instantane, final: Instantane, juge: Jugement | None = None
) -> list[tuple[float, str | None]]:
    """Contrôleur générique : un couple (score, détail) par contrôle de la tâche, dans l'ordre."""
    ctx = _Contexte(
        initial=initial,
        final=final,
        envois=final.envois_depuis(initial),
        juge=juge,
        contexte_juge=" ".join((tache.contexte_juge or "").split()),
    )
    return [noter(controle, ctx) for controle in tache.controles]
