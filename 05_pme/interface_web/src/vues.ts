// Vues dédiées de la messagerie et des dossiers : elles lisent le texte que rendent les outils et
// le présentent comme un poste de bureau, avec des liens au lieu d'identifiants à recopier.

import { echapper, lien } from "./html.ts";

export interface LigneCourriel {
  readonly identifiant: string;
  readonly date: string;
  readonly expediteur: string;
  readonly objet: string;
  readonly lu: boolean;
  readonly pieces: string;
}

/** Les lignes de lister_courriels : identifiant | date | expéditeur | objet | lu ou non lu | pièces. */
export function lignesCourriels(texte: string): LigneCourriel[] {
  return texte
    .split("\n")
    .map((l) => l.split(" | "))
    .filter((champs) => champs.length >= 6)
    .map((champs) => ({
      identifiant: champs[0] ?? "",
      date: champs[1] ?? "",
      expediteur: champs[2] ?? "",
      objet: champs.slice(3, -2).join(" | "),
      lu: champs.at(-2) === "lu",
      pieces: champs.at(-1) ?? "",
    }));
}

/** Les noms des pièces jointes, lus dans l'en-tête que rend lire_courriel. */
export function piecesJointes(texteCourriel: string): string[] {
  const ligne = texteCourriel.split("\n").find((l) => l.startsWith("Pièces jointes : "));
  const liste = ligne?.slice("Pièces jointes : ".length) ?? "(aucune)";
  if (liste === "(aucune)") {
    return [];
  }
  return [...liste.matchAll(/(.+?) \(\d+ octets\)(?:, |$)/g)].map((m) => m[1] ?? "").filter((p) => p !== "");
}

export interface Entree {
  readonly nom: string;
  readonly dossier: boolean;
}

/** Les lignes de lister : un élément par ligne, les dossiers finissant par « / ». */
export function entreesDossier(texte: string): Entree[] {
  return texte
    .split("\n")
    .filter((l) => l !== "" && !l.startsWith("("))
    .map((l) => (l.endsWith("/") ? { nom: l.slice(0, -1), dossier: true } : { nom: l, dossier: false }));
}

/** Chemin d'un élément dans un dossier ; le dossier racine est la chaîne vide. */
export function joindre(dossier: string, nom: string): string {
  return dossier === "" ? nom : `${dossier.replace(/\/+$/, "")}/${nom}`;
}

/** Le fil d'Ariane d'un chemin de dossier, chaque étape en lien. */
export function filAriane(chemin: string): string {
  const parties = chemin.split("/").filter((p) => p !== "");
  const etapes = [`<a href="${lien("/dossiers")}">Dossiers partagés</a>`];
  parties.forEach((p, i) => {
    etapes.push(`<a href="${lien("/dossiers", { chemin: parties.slice(0, i + 1).join("/") })}">${echapper(p)}</a>`);
  });
  return `<p>${etapes.join(" / ")}</p>`;
}

/** Une date ISO lisible : jour et heure, sans secondes ni décalage (2026-11-02 07:30). */
export function dateLisible(date: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(date) ? date.slice(0, 16).replace("T", " ") : date;
}

/** Le nombre de pièces jointes, vide quand il n'y en a pas. */
function nombrePieces(pieces: string): string {
  const nombre = pieces.split(" ")[0] ?? "";
  return nombre === "0" ? "" : nombre;
}

/** Le tableau des courriels d'une boîte, le plus récent en haut comme dans une messagerie ;
 * chaque ligne mène au courriel. */
export function tableauCourriels(boite: string, lignes: readonly LigneCourriel[]): string {
  if (lignes.length === 0) {
    return "<p>Aucun courriel.</p>";
  }
  const corps = [...lignes]
    .reverse()
    .map(
      (c) =>
        `<tr${c.lu ? "" : ' class="non-lu"'}><td class="date">${echapper(dateLisible(c.date))}</td>` +
        `<td>${echapper(c.expediteur)}</td>` +
        `<td><a href="${lien("/messagerie/lire", { boite, identifiant: c.identifiant })}">${echapper(c.objet || "(sans objet)")}</a></td>` +
        `<td>${c.lu ? "lu" : "non lu"}</td><td>${echapper(nombrePieces(c.pieces))}</td></tr>`,
    )
    .join("");
  return `<table><tr><th>Date</th><th>De</th><th>Objet</th><th>État</th><th>Pièces</th></tr>${corps}</table>`;
}

/** Le contenu d'un dossier, sous-dossiers et documents en liens. */
export function listeDossier(chemin: string, entrees: readonly Entree[]): string {
  if (entrees.length === 0) {
    return "<p>Dossier vide.</p>";
  }
  const lignes = entrees.map((e) => {
    const cible = joindre(chemin, e.nom);
    return e.dossier
      ? `<li><strong><a href="${lien("/dossiers", { chemin: cible })}">${echapper(e.nom)}/</a></strong></li>`
      : `<li><a href="${lien("/dossiers/lire", { chemin: cible })}">${echapper(e.nom)}</a></li>`;
  });
  return `<ul>${lignes.join("")}</ul>`;
}
