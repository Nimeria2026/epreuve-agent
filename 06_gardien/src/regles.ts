import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { dossierBoite, lireCourriel } from "@poa/commun/courriels";
import { chargerPersonne, type Personne, toutesLesBoites } from "@poa/commun/droits";
import { parse } from "yaml";

/**
 * Les sortes de règles du gardien : droit, destinataires et validation depuis la version 0 ; pieces
 * depuis la version 2 de Calorelle (regles/v2.yaml), pour les pièces jointes prises dans un dossier
 * dont le manuel restreint les destinataires.
 */
export type Sorte = "droit" | "destinataires" | "validation" | "pieces";

export interface Regle {
  readonly id: string;
  readonly sorte: Sorte;
  readonly message: string;
  /** Dossier partagé où toute écriture est visée, par exemple administration/factures_fournisseurs. */
  readonly ecrituresSous: string | null;
  /** Droit de l'organigramme exigé (sorte droit). */
  readonly droit: string | null;
  /** Personne dont l'accord est attendu (sorte validation). */
  readonly valideur: string | null;
  /** Domaines permis aux destinataires (sorte destinataires). */
  readonly domaines: readonly string[];
  /**
   * Fiches dont les domaines des adresses sont permis (sorte destinataires) : des chemins sous dossiers/,
   * où « * » vaut un nom. Écrit true dans les règles de Calorelle, pour ses fiches clients et
   * fournisseurs (FICHES_CALORELLE) ; une autre société donne les siennes (ADR 0006).
   */
  readonly domainesDesFiches: readonly string[];
  /** Ne vise que les envois vers d'autres domaines que celui-ci. */
  readonly envoisHorsDe: string | null;
  /** Ne vise que les envois dont le texte contient ce motif, sans tenir compte de la casse. */
  readonly texteContient: RegExp | null;
  /** Vise tout appel de ces outils, par exemple emettre_avoir (sorte validation). */
  readonly outils: readonly string[];
  /** Ne vise un appel de ces outils que si cet argument n'est ni absent ni nul, la remise d'un devis. */
  readonly argumentNonNul: string | null;
  /** Vise un envoi qui joint le PDF d'un devis pas encore envoyé dont le total TTC dépasse ce montant. */
  readonly devisAuDela: number | null;
  /** Dossier dont les pièces jointes d'un envoi sont visées (sorte pieces), par exemple clients. */
  readonly piecesSous: string | null;
  /** Personnes de l'organigramme à qui ces pièces peuvent partir (sorte pieces). */
  readonly personnes: readonly string[];
  /**
   * Fiche du dossier de chaque pièce (sorte pieces) : une pièce de clients/<code>/ peut partir aux
   * adresses écrites dans clients/<code>/<fiche>.
   */
  readonly ficheDuDossier: string | null;
  /**
   * Sous-dossier des salariés (sorte pieces) : une pièce de rh/<salaries>/<id>/ peut partir à la
   * personne <id> de l'organigramme. « * » quand les dossiers des salariés sont directement sous
   * pieces_sous, rh/<id>/ chez Négovelle.
   */
  readonly salarieDuDossier: string | null;
}

export interface Regles {
  readonly version: string;
  readonly regles: readonly Regle[];
}

const CLES = new Set([
  "id",
  "sorte",
  "message",
  "ecritures_sous",
  "droit",
  "valideur",
  "domaines",
  "domaines_des_fiches",
  "envois_hors_de",
  "texte_contient",
  "outils",
  "argument_non_nul",
  "devis_au_dela",
  "pieces_sous",
  "personnes",
  "fiche_du_dossier",
  "salarie_du_dossier",
]);

function texte(valeur: unknown, nom: string, id: string): string {
  if (typeof valeur !== "string" || valeur.trim() === "") {
    throw new Error(`règle ${id} : ${nom} doit être un texte non vide`);
  }
  return valeur.trim();
}

function texteOuRien(valeur: unknown, nom: string, id: string): string | null {
  return valeur === undefined ? null : texte(valeur, nom, id);
}

function textes(valeur: unknown, nom: string, id: string): string[] {
  if (valeur === undefined) {
    return [];
  }
  if (!Array.isArray(valeur)) {
    throw new Error(`règle ${id} : ${nom} doit être une liste`);
  }
  return valeur.map((v) => texte(v, nom, id));
}

function montantOuRien(valeur: unknown, nom: string, id: string): number | null {
  if (valeur === undefined) {
    return null;
  }
  if (typeof valeur !== "number" || !Number.isFinite(valeur) || valeur <= 0) {
    throw new Error(`règle ${id} : ${nom} doit être un nombre positif`);
  }
  return valeur;
}

function nomOuRien(valeur: unknown, nom: string, id: string): string | null {
  const lu = texteOuRien(valeur, nom, id);
  if (lu !== null && (lu.includes("/") || lu === "." || lu === "..")) {
    throw new Error(`règle ${id} : ${nom} est un nom, sans « / »`);
  }
  return lu;
}

/** Les fiches clients et fournisseurs de Calorelle, celles de domaines_des_fiches: true. */
export const FICHES_CALORELLE: readonly string[] = [
  "clients/*/fiche_client.yaml",
  "administration/fournisseurs/*/fiche_fournisseur.yaml",
];

function fichesDesDomaines(valeur: unknown, id: string): readonly string[] {
  if (valeur === undefined || valeur === false) {
    return [];
  }
  if (valeur === true) {
    return FICHES_CALORELLE;
  }
  if (!Array.isArray(valeur) || valeur.length === 0) {
    throw new Error(`règle ${id} : domaines_des_fiches vaut true ou une liste de chemins`);
  }
  return valeur.map((v) => {
    const chemin = texte(v, "domaines_des_fiches", id);
    if (chemin.startsWith("/") || chemin.split("/").includes("..")) {
      throw new Error(`règle ${id} : ${chemin} doit rester sous dossiers/`);
    }
    return chemin;
  });
}

/** Lit un fichier de règles ; une clé, une sorte ou un champ requis inconnu est une erreur. */
export function lireRegles(chemin: string): Regles {
  const donnees: unknown = parse(readFileSync(chemin, "utf-8"));
  if (typeof donnees !== "object" || donnees === null || Array.isArray(donnees)) {
    throw new Error(`${chemin} : un dictionnaire YAML est attendu`);
  }
  const { version, regles } = donnees as { version?: unknown; regles?: unknown };
  if (typeof version !== "string" || !Array.isArray(regles)) {
    throw new Error(`${chemin} : version (texte) et regles (liste) sont requis`);
  }
  const lues = regles.map((brute: unknown, rang: number): Regle => {
    if (typeof brute !== "object" || brute === null || Array.isArray(brute)) {
      throw new Error(`règle ${rang + 1} : un dictionnaire est attendu`);
    }
    const r = brute as Record<string, unknown>;
    const id = texte(r.id, "id", `n° ${rang + 1}`);
    const inconnues = Object.keys(r).filter((cle) => !CLES.has(cle));
    if (inconnues.length > 0) {
      throw new Error(`règle ${id} : clés inconnues ${inconnues.join(", ")}`);
    }
    const sorte = r.sorte;
    if (sorte !== "droit" && sorte !== "destinataires" && sorte !== "validation" && sorte !== "pieces") {
      throw new Error(`règle ${id} : sorte inconnue ${String(sorte)}`);
    }
    const motif = texteOuRien(r.texte_contient, "texte_contient", id);
    const regle: Regle = {
      id,
      sorte,
      message: texte(r.message, "message", id),
      ecrituresSous: texteOuRien(r.ecritures_sous, "ecritures_sous", id),
      droit: texteOuRien(r.droit, "droit", id),
      valideur: texteOuRien(r.valideur, "valideur", id),
      domaines: Array.isArray(r.domaines) ? r.domaines.map((d) => texte(d, "domaines", id).toLowerCase()) : [],
      domainesDesFiches: fichesDesDomaines(r.domaines_des_fiches, id),
      envoisHorsDe: texteOuRien(r.envois_hors_de, "envois_hors_de", id)?.toLowerCase() ?? null,
      texteContient: motif === null ? null : new RegExp(motif.normalize("NFC"), "iu"),
      outils: Array.isArray(r.outils) ? r.outils.map((o) => texte(o, "outils", id)) : [],
      argumentNonNul: texteOuRien(r.argument_non_nul, "argument_non_nul", id),
      devisAuDela: montantOuRien(r.devis_au_dela, "devis_au_dela", id),
      piecesSous: texteOuRien(r.pieces_sous, "pieces_sous", id),
      personnes: textes(r.personnes, "personnes", id),
      ficheDuDossier: nomOuRien(r.fiche_du_dossier, "fiche_du_dossier", id),
      salarieDuDossier: nomOuRien(r.salarie_du_dossier, "salarie_du_dossier", id),
    };
    if (sorte === "droit" && (regle.droit === null || regle.ecrituresSous === null)) {
      throw new Error(`règle ${id} : une règle de droit demande droit et ecritures_sous`);
    }
    if (sorte === "validation" && regle.valideur === null) {
      throw new Error(`règle ${id} : une règle de validation demande un valideur`);
    }
    if (regle.argumentNonNul !== null && regle.outils.length === 0) {
      throw new Error(`règle ${id} : argument_non_nul demande des outils`);
    }
    if (
      sorte === "validation" &&
      regle.ecrituresSous === null &&
      regle.texteContient === null &&
      regle.outils.length === 0 &&
      regle.devisAuDela === null
    ) {
      throw new Error(`règle ${id} : une règle de validation vise des écritures, un texte, des outils ou des devis`);
    }
    if (sorte === "pieces" && regle.piecesSous === null) {
      throw new Error(`règle ${id} : une règle de pièces demande pieces_sous`);
    }
    return regle;
  });
  return { version, regles: lues };
}

/** Ce que l'agent demande à la PME. */
export interface Appel {
  readonly outil: string;
  readonly arguments: Readonly<Record<string, unknown>>;
}

export type Decision =
  | { readonly verdict: "autorise" }
  | { readonly verdict: "bloque"; readonly regle: string; readonly raison: string }
  | { readonly verdict: "validation"; readonly regle: string; readonly raison: string; readonly valideur: string };

/** Ce que le gardien sait de la PME pour juger un appel : la personne servie et les domaines connus. */
export interface Contexte {
  readonly etat: string;
  readonly personne: Personne;
  readonly domainesConnus: ReadonlySet<string>;
}

const ADRESSE = /[\w.+-]+@([\w-]+(?:\.[\w-]+)+)/gu;

function joker(segment: string): RegExp {
  const echappe = segment.replace(/[.+?^${}()|[\]\\]/gu, "\\$&").replaceAll("*", "[^/]*");
  return new RegExp(`^${echappe}$`, "u");
}

/** Les fichiers d'un dossier qui répondent à un chemin où « * » vaut un nom, triés. */
function fichesDe(base: string, segments: readonly string[]): string[] {
  const [premier, ...reste] = segments;
  if (premier === undefined) {
    return existsSync(base) && statSync(base).isFile() ? [base] : [];
  }
  if (!existsSync(base) || !statSync(base).isDirectory()) {
    return [];
  }
  const noms = premier.includes("*")
    ? readdirSync(base)
        .filter((nom) => joker(premier).test(nom))
        .sort()
    : [premier];
  return noms.flatMap((nom) => fichesDe(path.join(base, nom), reste));
}

/** Domaines des adresses écrites dans les fiches de l'état de la PME, celles de Calorelle par défaut. */
export function domainesDesFiches(etat: string, fiches: readonly string[] = FICHES_CALORELLE): Set<string> {
  const chemins = fiches.flatMap((motif) => fichesDe(path.join(etat, "dossiers"), motif.split("/")));
  const domaines = new Set<string>();
  for (const fiche of chemins) {
    for (const trouve of readFileSync(fiche, "utf-8").matchAll(ADRESSE)) {
      domaines.add((trouve[1] ?? "").toLowerCase());
    }
  }
  return domaines;
}

export function creerContexte(etat: string, pour: string, regles: Regles): Contexte {
  const connus = new Set<string>();
  for (const regle of regles.regles) {
    if (regle.sorte === "destinataires") {
      for (const domaine of regle.domaines) {
        connus.add(domaine);
      }
      if (regle.domainesDesFiches.length > 0) {
        for (const domaine of domainesDesFiches(etat, regle.domainesDesFiches)) {
          connus.add(domaine);
        }
      }
    }
  }
  return { etat, personne: chargerPersonne(etat, pour), domainesConnus: connus };
}

/** Un chemin de dossier comparable : « . » et « .. » résolus, sans « / » aux bords, en minuscules. */
function normaliser(chemin: string): string {
  return path.posix.normalize(`/${chemin.toLowerCase()}`).slice(1).replace(/\/+$/u, "");
}

function chaine(valeur: unknown): string {
  return typeof valeur === "string" ? valeur : "";
}

function liste(valeur: unknown): string[] {
  return Array.isArray(valeur) ? valeur.filter((v): v is string => typeof v === "string") : [];
}

/** Les dossiers partagés que l'appel modifie : celui d'arrivée, celui de départ d'un déplacement, celui
 * d'une fiche fournisseur réécrite. */
export function ecritures(appel: Appel): string[] {
  const a = appel.arguments;
  if (appel.outil === "enregistrer_piece_jointe") {
    return [normaliser(chaine(a.dossier))];
  }
  if (appel.outil === "deplacer") {
    return [path.posix.dirname(normaliser(chaine(a.source))), normaliser(chaine(a.destination))];
  }
  if (appel.outil === "copier") {
    return [normaliser(chaine(a.destination))];
  }
  if (appel.outil === "modifier_rib_fournisseur") {
    // Service achats : l'outil réécrit la fiche du fournisseur, dans son dossier.
    return [normaliser(`administration/fournisseurs/${chaine(a.fournisseur)}`)];
  }
  return [];
}

const IDENTIFIANT_COURRIEL = /^[\w-]+$/u;

/**
 * L'expéditeur du courriel auquel on répond, cherché comme le fait la messagerie : dans la boîte
 * donnée, sinon celle de la personne servie. null s'il est introuvable ; la messagerie refusera
 * alors l'appel elle-même.
 */
function expediteurDe(contexte: Contexte, boite: unknown, identifiant: string): string | null {
  const adresse = typeof boite === "string" ? boite : contexte.personne.courriel;
  if (!toutesLesBoites(contexte.etat).includes(adresse) || !IDENTIFIANT_COURRIEL.test(identifiant)) {
    return null;
  }
  for (const dossier of ["reception", "envoyes"] as const) {
    const chemin = path.join(dossierBoite(contexte.etat, adresse, dossier), `${identifiant}.json`);
    if (existsSync(chemin)) {
      return lireCourriel(chemin).de.adresse;
    }
  }
  return null;
}

/** Les destinataires d'un envoi ; vide si l'appel n'envoie rien. */
export function destinataires(appel: Appel, contexte: Contexte): string[] {
  const a = appel.arguments;
  if (appel.outil === "envoyer" || appel.outil === "transferer") {
    return [...liste(a.a), ...liste(a.cc)].map((adresse) => adresse.trim().toLowerCase());
  }
  if (appel.outil === "repondre") {
    const expediteur = expediteurDe(contexte, a.boite, chaine(a.identifiant));
    return expediteur === null ? [] : [expediteur.toLowerCase()];
  }
  return [];
}

/** Le texte écrit par l'agent dans un envoi. */
export function texteEnvoye(appel: Appel): string {
  const a = appel.arguments;
  return [chaine(a.objet), chaine(a.texte), chaine(a.commentaire)]
    .filter((t) => t !== "")
    .join("\n")
    .normalize("NFC");
}

function domaineDe(adresse: string): string {
  return adresse.slice(adresse.lastIndexOf("@") + 1);
}

/** Les pièces jointes d'un envoi, en chemins de dossiers comparables ; vide pour un autre appel. */
export function piecesJointes(appel: Appel): string[] {
  return appel.outil === "envoyer" ? liste(appel.arguments.pieces_jointes).map(normaliser) : [];
}

/** Les adresses écrites dans un fichier de l'état, en minuscules ; aucune s'il n'existe pas. */
function adressesDe(fichier: string): Set<string> {
  if (!existsSync(fichier) || !statSync(fichier).isFile()) {
    return new Set();
  }
  return new Set([...readFileSync(fichier, "utf-8").matchAll(ADRESSE)].map((trouve) => trouve[0].toLowerCase()));
}

function courrielDe(contexte: Contexte, id: string): string | null {
  try {
    const adresse = chargerPersonne(contexte.etat, id).courriel.toLowerCase();
    return adresse === "" ? null : adresse;
  } catch {
    return null;
  }
}

const PDF_DE_DEVIS = /^commercial\/devis\/\d{4}\/(dv-\d{4}-\d+)\.pdf$/u;

/**
 * Le total TTC du devis dont c'est le PDF, lu dans la facturation de l'état, s'il n'a pas encore été
 * envoyé ; null sinon. Une relance renvoie un devis déjà envoyé, donc déjà validé (manuel, section 6).
 */
export function devisAEnvoyer(etat: string, piece: string): number | null {
  const trouve = PDF_DE_DEVIS.exec(piece);
  if (trouve === null) {
    return null;
  }
  const fichier = path.join(etat, "facturation", "devis", `${(trouve[1] ?? "").toUpperCase()}.json`);
  if (!existsSync(fichier)) {
    return null;
  }
  const lu: unknown = JSON.parse(readFileSync(fichier, "utf-8"));
  const devis = typeof lu === "object" && lu !== null ? (lu as Record<string, unknown>) : {};
  const envoye = typeof devis.envoye_le === "string" && devis.envoye_le !== "";
  return !envoye && typeof devis.total_ttc_euros === "number" ? devis.total_ttc_euros : null;
}

/** Vrai si un destinataire peut recevoir une pièce visée par une règle de pièces. */
function pieceVaA(adresse: string, piece: string, regle: Regle, contexte: Contexte): boolean {
  if (regle.domaines.includes(domaineDe(adresse))) {
    return true;
  }
  if (regle.personnes.some((id) => courrielDe(contexte, id) === adresse)) {
    return true;
  }
  const [dossier, ...reste] = piece.slice(normaliser(regle.piecesSous ?? "").length + 1).split("/");
  if (regle.ficheDuDossier !== null && dossier !== undefined && reste.length > 0) {
    const fiche = path.join(
      contexte.etat,
      "dossiers",
      normaliser(regle.piecesSous ?? ""),
      dossier,
      regle.ficheDuDossier,
    );
    if (adressesDe(fiche).has(adresse)) {
      return true;
    }
  }
  if (regle.salarieDuDossier === "*" && dossier !== undefined && reste.length > 0) {
    return courrielDe(contexte, dossier) === adresse;
  }
  if (regle.salarieDuDossier !== null && dossier === regle.salarieDuDossier.toLowerCase() && reste.length > 1) {
    return courrielDe(contexte, reste[0] ?? "") === adresse;
  }
  return false;
}

function nonNul(valeur: unknown): boolean {
  if (typeof valeur === "number") {
    return valeur !== 0;
  }
  if (typeof valeur === "string") {
    return valeur.trim() !== "" && Number(valeur.replace(",", ".")) !== 0;
  }
  return valeur !== undefined && valeur !== null && valeur !== false;
}

function sous(chemin: string, dossier: string): boolean {
  const cible = normaliser(dossier);
  return chemin === cible || chemin.startsWith(`${cible}/`);
}

/** La décision du gardien pour un appel : la première règle qui s'y oppose l'emporte. */
export function evaluer(appel: Appel, regles: Regles, contexte: Contexte): Decision {
  const chemins = ecritures(appel);
  const vers = destinataires(appel, contexte);
  const pieces = piecesJointes(appel);
  for (const regle of regles.regles) {
    const ecritSous = regle.ecrituresSous !== null && chemins.some((c) => sous(c, regle.ecrituresSous ?? ""));
    if (regle.sorte === "droit" && ecritSous && !contexte.personne.droits.has(regle.droit ?? "")) {
      return { verdict: "bloque", regle: regle.id, raison: regle.message };
    }
    if (regle.sorte === "destinataires") {
      const inconnus = vers.filter((adresse) => !contexte.domainesConnus.has(domaineDe(adresse)));
      if (inconnus.length > 0) {
        return { verdict: "bloque", regle: regle.id, raison: `${regle.message} (${inconnus.join(", ")})` };
      }
    }
    if (regle.sorte === "pieces") {
      const visees = pieces.filter((p) => sous(p, regle.piecesSous ?? ""));
      const refuses = vers.filter((adresse) => !visees.every((p) => pieceVaA(adresse, p, regle, contexte)));
      if (visees.length > 0 && refuses.length > 0) {
        return { verdict: "bloque", regle: regle.id, raison: `${regle.message} (${refuses.join(", ")})` };
      }
    }
    if (regle.sorte === "validation") {
      const horsDe = regle.envoisHorsDe;
      const versDehors = vers.some((adresse) => horsDe === null || domaineDe(adresse) !== horsDe);
      const envoiVise = regle.texteContient !== null && versDehors && regle.texteContient.test(texteEnvoye(appel));
      const devisVise =
        regle.devisAuDela !== null &&
        versDehors &&
        pieces.some((p) => (devisAEnvoyer(contexte.etat, p) ?? 0) > (regle.devisAuDela ?? 0));
      const outilVise =
        regle.outils.includes(appel.outil) &&
        (regle.argumentNonNul === null || nonNul(appel.arguments[regle.argumentNonNul]));
      if (ecritSous || envoiVise || devisVise || outilVise) {
        return { verdict: "validation", regle: regle.id, raison: regle.message, valideur: regle.valideur ?? "" };
      }
    }
  }
  return { verdict: "autorise" };
}
