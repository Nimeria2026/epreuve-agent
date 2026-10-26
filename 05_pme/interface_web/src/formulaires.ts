// Formulaires du poste humain, construits depuis le schéma JSON des arguments d'un outil MCP.
// Une personne remplit des champs, jamais du JSON : les listes s'écrivent une valeur par ligne,
// les tableaux d'objets (les lignes d'un devis) en lignes de saisie.

import { echapper } from "./html.ts";

/** Ce que le poste lit d'un schéma JSON d'arguments (sous-ensemble de JSON Schema). */
export interface Schema {
  readonly type?: string | readonly string[];
  readonly enum?: readonly unknown[];
  readonly items?: Schema;
  readonly properties?: Readonly<Record<string, Schema>>;
  readonly required?: readonly string[];
  readonly default?: unknown;
  readonly description?: string;
}

interface Base {
  readonly nom: string;
  readonly description: string;
  readonly obligatoire: boolean;
}

export type Champ =
  | (Base & { readonly genre: "texte"; readonly long: boolean; readonly defaut: string | undefined })
  | (Base & { readonly genre: "nombre"; readonly defaut: number | undefined })
  | (Base & { readonly genre: "booleen"; readonly defaut: boolean })
  | (Base & { readonly genre: "choix"; readonly options: readonly string[]; readonly defaut: string | undefined })
  | (Base & { readonly genre: "liste"; readonly defaut: readonly string[] | undefined })
  | (Base & { readonly genre: "lignes"; readonly colonnes: readonly Champ[] })
  | (Base & { readonly genre: "json"; readonly defaut: unknown });

/** Champs de texte qui appellent une zone de plusieurs lignes. */
const LONGS = new Set(["texte", "commentaire", "motif", "corps"]);

/** Nombre de lignes de saisie offertes pour un tableau d'objets ; les lignes vides sont ignorées. */
export const LIGNES_DE_SAISIE = 8;

function typeDe(schema: Schema): string | undefined {
  if (typeof schema.type === "string") {
    return schema.type;
  }
  return schema.type?.find((t) => t !== "null");
}

function textes(valeurs: readonly unknown[]): string[] | undefined {
  return valeurs.every((v) => typeof v === "string") ? (valeurs as string[]) : undefined;
}

/** Les champs d'un formulaire, dans l'ordre du schéma. */
export function champs(schema: Schema): Champ[] {
  const requis = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([nom, propriete]) => champ(nom, propriete, requis.has(nom)));
}

function champ(nom: string, schema: Schema, obligatoire: boolean): Champ {
  const base = { nom, description: schema.description ?? "", obligatoire };
  const options = schema.enum === undefined ? undefined : textes(schema.enum);
  if (options !== undefined) {
    return {
      ...base,
      genre: "choix",
      options,
      defaut: typeof schema.default === "string" ? schema.default : undefined,
    };
  }
  switch (typeDe(schema)) {
    case "string":
      return {
        ...base,
        genre: "texte",
        long: LONGS.has(nom),
        defaut: typeof schema.default === "string" ? schema.default : undefined,
      };
    case "number":
    case "integer":
      return { ...base, genre: "nombre", defaut: typeof schema.default === "number" ? schema.default : undefined };
    case "boolean":
      return { ...base, genre: "booleen", defaut: schema.default === true };
    case "array": {
      const elements = schema.items ?? {};
      if (typeDe(elements) === "string" && elements.enum === undefined) {
        const defaut = Array.isArray(schema.default) ? textes(schema.default) : undefined;
        return { ...base, genre: "liste", defaut };
      }
      if (typeDe(elements) === "object") {
        const colonnes = champs(elements);
        if (colonnes.every((c) => c.genre !== "lignes" && c.genre !== "json")) {
          return { ...base, genre: "lignes", colonnes };
        }
      }
      return { ...base, genre: "json", defaut: schema.default };
    }
    default:
      return { ...base, genre: "json", defaut: schema.default };
  }
}

// ------------------------------------------------------------------------------- affichage

export interface Remplissage {
  /** Valeurs déjà saisies ou proposées, par nom de champ (nom.ligne.colonne pour un tableau). */
  readonly valeurs?: Readonly<Record<string, string>>;
  /** Champs fixés par la page : envoyés tels quels, montrés sans être modifiables. */
  readonly fixes?: Readonly<Record<string, string>>;
}

/** Libellés des arguments dont le nom technique se lit mal ; les autres prennent une majuscule. */
const LIBELLES: Readonly<Record<string, string>> = {
  a: "À",
  cc: "Cc",
  boite: "Boîte",
  piece: "Pièce jointe",
  pieces_jointes: "Pièces jointes",
  non_lus_seulement: "Non lus seulement",
  nom_fichier: "Nom du fichier",
  debut: "Début",
  du: "Du",
  au: "Au",
  duree_minutes: "Durée, en minutes",
  competence: "Compétence",
  numero: "Numéro",
  quantite: "Quantité",
  taux_tva: "Taux de TVA",
  remise_pourcent: "Remise, en pour cent",
  montant_euros: "Montant, en euros",
  reponse: "Réponse",
  iban: "IBAN",
};

/** Le nom d'un argument tel qu'une personne le lit. */
export function nomLisible(nom: string): string {
  const libre = nom.replaceAll("_", " ");
  return LIBELLES[nom] ?? libre.charAt(0).toUpperCase() + libre.slice(1);
}

function libelle(c: Champ, identifiant: string): string {
  const nom = nomLisible(c.nom);
  const precisions = [c.description, c.obligatoire ? "" : "facultatif"].filter((p) => p !== "").join(" ; ");
  return `<label for="${identifiant}">${echapper(nom)}${precisions === "" ? "" : ` <small>(${echapper(precisions)})</small>`}</label>`;
}

function valeurInitiale(c: Champ, valeurs: Readonly<Record<string, string>>): string {
  const saisie = valeurs[c.nom];
  if (saisie !== undefined) {
    return saisie;
  }
  switch (c.genre) {
    case "texte":
    case "choix":
      return c.defaut ?? "";
    case "nombre":
      return c.defaut === undefined ? "" : String(c.defaut);
    case "liste":
      return (c.defaut ?? []).join("\n");
    case "json":
      return c.defaut === undefined ? "" : JSON.stringify(c.defaut);
    default:
      return "";
  }
}

function controle(c: Champ, nom: string, identifiant: string, valeur: string, cochee: boolean): string {
  const attributs = `name="${echapper(nom)}" id="${echapper(identifiant)}"`;
  switch (c.genre) {
    case "texte":
      return c.long
        ? `<textarea ${attributs} rows="5">${echapper(valeur)}</textarea>`
        : `<input type="text" ${attributs} value="${echapper(valeur)}">`;
    case "nombre":
      return `<input type="text" inputmode="decimal" ${attributs} value="${echapper(valeur)}">`;
    case "booleen":
      return `<input type="checkbox" ${attributs} value="oui"${cochee ? " checked" : ""}>`;
    case "choix": {
      const vide = c.obligatoire ? "" : `<option value="">(aucun)</option>`;
      const options = c.options
        .map((o) => `<option value="${echapper(o)}"${o === valeur ? " selected" : ""}>${echapper(o)}</option>`)
        .join("");
      return `<select ${attributs}>${vide}${options}</select>`;
    }
    case "liste":
      return `<textarea ${attributs} rows="3" placeholder="une valeur par ligne">${echapper(valeur)}</textarea>`;
    default:
      return `<textarea ${attributs} rows="4">${echapper(valeur)}</textarea>`;
  }
}

function tableau(c: Champ & { readonly genre: "lignes" }, valeurs: Readonly<Record<string, string>>): string {
  const entetes = c.colonnes.map((col) => `<th>${echapper(nomLisible(col.nom))}</th>`).join("");
  const lignes = Array.from({ length: LIGNES_DE_SAISIE }, (_, i) => {
    const cellules = c.colonnes.map((col) => {
      const nom = `${c.nom}.${i}.${col.nom}`;
      const valeur = valeurs[nom] ?? "";
      return `<td>${controle(col, nom, nom, valeur, valeur === "oui")}</td>`;
    });
    return `<tr>${cellules.join("")}</tr>`;
  });
  const aide = c.colonnes
    .filter((col) => col.description !== "")
    .map((col) => `${nomLisible(col.nom)} : ${col.description}`)
    .join(" ; ");
  return (
    `<label>${echapper(nomLisible(c.nom))} <small>(${echapper(aide || "une ligne par élément")} ; ` +
    `lignes vides ignorées)</small></label><table class="lignes"><tr>${entetes}</tr>${lignes.join("")}</table>`
  );
}

/** Le HTML d'un formulaire qui envoie ses champs à l'adresse donnée. */
export function formulaire(
  action: string,
  liste: readonly Champ[],
  remplissage: Remplissage,
  bouton: string,
  cachees: Readonly<Record<string, string>> = {},
): string {
  const valeurs = remplissage.valeurs ?? {};
  const fixes = remplissage.fixes ?? {};
  const parties: string[] = [];
  for (const [nom, valeur] of Object.entries(cachees)) {
    parties.push(`<input type="hidden" name="${echapper(nom)}" value="${echapper(valeur)}">`);
  }
  for (const c of liste) {
    const fixe = fixes[c.nom];
    if (fixe !== undefined) {
      parties.push(
        `<input type="hidden" name="${echapper(c.nom)}" value="${echapper(fixe)}">` +
          `<p><strong>${echapper(nomLisible(c.nom))}</strong> : ${echapper(fixe)}</p>`,
      );
      continue;
    }
    if (c.genre === "lignes") {
      parties.push(tableau(c, valeurs));
      continue;
    }
    const identifiant = `champ-${c.nom}`;
    const valeur = valeurInitiale(c, valeurs);
    const cochee = c.genre === "booleen" && (valeurs[c.nom] === undefined ? c.defaut : valeurs[c.nom] === "oui");
    parties.push(libelle(c, identifiant) + controle(c, c.nom, identifiant, valeur, cochee));
  }
  return `<form method="post" action="${echapper(action)}">${parties.join("")}<button type="submit">${echapper(bouton)}</button></form>`;
}

// ---------------------------------------------------------------------------------- lecture

export interface Lecture {
  readonly arguments: Record<string, unknown>;
  readonly erreurs: readonly string[];
}

type Lu =
  | { readonly present: false }
  | { readonly present: true; readonly valeur: unknown }
  | { readonly erreur: string };

function lireValeur(c: Champ, brut: string | null): Lu {
  const texte = (brut ?? "").replaceAll("\r\n", "\n");
  switch (c.genre) {
    case "booleen":
      return { present: true, valeur: texte === "oui" };
    case "texte":
      if (texte.trim() === "") {
        return c.obligatoire ? { erreur: "un texte est attendu" } : { present: false };
      }
      return { present: true, valeur: texte };
    case "nombre": {
      const net = texte.replace(/\s/g, "").replace(",", ".");
      if (net === "") {
        return c.obligatoire ? { erreur: "un nombre est attendu" } : { present: false };
      }
      const nombre = Number(net);
      return Number.isFinite(nombre)
        ? { present: true, valeur: nombre }
        : { erreur: `« ${texte} » n'est pas un nombre` };
    }
    case "choix":
      if (texte === "") {
        return c.obligatoire ? { erreur: "un choix est attendu" } : { present: false };
      }
      return c.options.includes(texte)
        ? { present: true, valeur: texte }
        : { erreur: `« ${texte} » n'est pas proposé` };
    case "liste": {
      const elements = texte
        .split(/[\n,;]+/)
        .map((e) => e.trim())
        .filter((e) => e !== "");
      return elements.length === 0 && !c.obligatoire ? { present: false } : { present: true, valeur: elements };
    }
    case "json":
      if (texte.trim() === "") {
        return c.obligatoire ? { erreur: "une valeur est attendue" } : { present: false };
      }
      try {
        return { present: true, valeur: JSON.parse(texte) as unknown };
      } catch {
        return { erreur: "valeur illisible" };
      }
    default:
      return { erreur: "champ inattendu" };
  }
}

function lireLignes(c: Champ & { readonly genre: "lignes" }, donnees: URLSearchParams, erreurs: string[]): Lu {
  const lignes: Record<string, unknown>[] = [];
  for (let i = 0; i < LIGNES_DE_SAISIE; i++) {
    const brut = c.colonnes.map((col) => donnees.get(`${c.nom}.${i}.${col.nom}`) ?? "");
    if (brut.every((b) => b.trim() === "")) {
      continue;
    }
    const ligne: Record<string, unknown> = {};
    c.colonnes.forEach((col, j) => {
      const lu = lireValeur(col, brut[j] ?? "");
      if ("erreur" in lu) {
        erreurs.push(`${c.nom}, ligne ${i + 1}, ${col.nom} : ${lu.erreur}`);
      } else if (lu.present) {
        ligne[col.nom] = lu.valeur;
      }
    });
    lignes.push(ligne);
  }
  if (lignes.length === 0 && !c.obligatoire) {
    return { present: false };
  }
  return { present: true, valeur: lignes };
}

/** Les arguments d'un appel, lus dans un formulaire envoyé ; les champs vides facultatifs sont omis. */
export function lireArguments(liste: readonly Champ[], donnees: URLSearchParams): Lecture {
  const resultat: Record<string, unknown> = {};
  const erreurs: string[] = [];
  for (const c of liste) {
    const lu = c.genre === "lignes" ? lireLignes(c, donnees, erreurs) : lireValeur(c, donnees.get(c.nom));
    if ("erreur" in lu) {
      erreurs.push(`${c.nom} : ${lu.erreur}`);
    } else if (lu.present) {
      resultat[c.nom] = lu.valeur;
    }
  }
  return { arguments: resultat, erreurs };
}
