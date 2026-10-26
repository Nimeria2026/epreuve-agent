// Petits outils HTML du poste humain : échappement et page commune.

const CARACTERES: Readonly<Record<string, string>> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Échappe un texte pour l'insérer dans du HTML, contenu ou valeur d'attribut. */
export function echapper(texte: string): string {
  return texte.replace(/[&<>"']/g, (c) => CARACTERES[c] ?? c);
}

/** Lien relatif avec ses paramètres de requête, déjà échappé pour un attribut href. */
export function lien(chemin: string, parametres: Readonly<Record<string, string>> = {}): string {
  const requete = new URLSearchParams(parametres).toString();
  return echapper(requete === "" ? chemin : `${chemin}?${requete}`);
}

const STYLE = `
body { font-family: system-ui, sans-serif; margin: 0; color: #1d1d1f; background: #f6f6f4; line-height: 1.45; }
header { background: #fff; border-bottom: 1px solid #ddd; padding: 10px 20px; display: flex; gap: 16px;
  align-items: center; flex-wrap: wrap; }
header nav a { margin-right: 12px; text-decoration: none; color: #1d4f91; font-weight: 600; }
header nav a.actif { color: #1d1d1f; border-bottom: 2px solid #1d4f91; }
header form { display: inline; margin: 0; }
.fin { margin-left: auto; display: flex; gap: 8px; }
main { padding: 16px 20px; max-width: 1100px; }
.enonce { background: #fffbe8; border: 1px solid #e8d98a; border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; }
.enonce summary { font-weight: 600; cursor: pointer; }
.texte { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 14px; background: #fff;
  border: 1px solid #ddd; border-radius: 6px; padding: 10px 12px; }
.erreur { border-color: #c0392b; background: #fdf0ee; }
table { border-collapse: collapse; background: #fff; width: 100%; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }
tr.non-lu td { font-weight: 600; }
td.date { white-space: nowrap; }
details.outil { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 8px 12px; margin: 10px 0; }
details.outil summary { cursor: pointer; font-weight: 600; }
label { display: block; margin-top: 8px; font-weight: 600; }
label small { font-weight: 400; color: #555; }
input[type=text], textarea, select { width: 100%; max-width: 640px; box-sizing: border-box; font: inherit; padding: 4px 6px; }
table.lignes input { max-width: none; }
button { font: inherit; padding: 5px 12px; margin-top: 10px; cursor: pointer; }
form > button { display: block; }
.colonnes { display: flex; gap: 20px; align-items: flex-start; }
.colonnes > aside { min-width: 220px; }
.colonnes > section { flex: 1; }
`;

export interface Navigation {
  readonly cle: string;
  readonly nom: string;
  readonly chemin: string;
}

export interface Cadre {
  readonly titre: string;
  readonly enonce?: string;
  readonly navigation?: readonly Navigation[];
  readonly actif?: string;
  readonly script?: string;
}

/** Une page complète : en-tête, navigation entre services, énoncé repliable, puis le corps. */
export function page(cadre: Cadre, corps: string): string {
  const liens = (cadre.navigation ?? [])
    .map((n) => `<a href="${lien(n.chemin)}"${n.cle === cadre.actif ? ' class="actif"' : ""}>${echapper(n.nom)}</a>`)
    .join("");
  const enTete =
    cadre.navigation === undefined
      ? `<header><strong>Calorelle</strong></header>`
      : `<header><strong>Calorelle</strong><nav>${liens}</nav><div class="fin">` +
        `<form method="post" action="/fini"><button type="submit">J'ai fini</button></form>` +
        `<form method="post" action="/abandon"><button type="submit">Abandonner l'essai</button></form></div></header>`;
  const enonce =
    cadre.enonce === undefined
      ? ""
      : `<details class="enonce" open><summary>Ta tâche</summary><div class="texte">${echapper(cadre.enonce)}</div></details>`;
  const script = cadre.script === undefined ? "" : `<script>${cadre.script}</script>`;
  return (
    `<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${echapper(cadre.titre)}</title>` +
    `<meta name="viewport" content="width=device-width, initial-scale=1"><style>${STYLE}</style></head>` +
    `<body>${enTete}<main>${enonce}${corps}</main>${script}</body></html>`
  );
}
