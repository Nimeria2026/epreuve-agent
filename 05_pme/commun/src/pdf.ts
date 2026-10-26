/**
 * Un PDF d'une page, en Helvetica, sans date ni identifiant : mêmes lignes, mêmes octets. Même
 * construction que `pdf()` de 09_outillage/scripts/generer_donnees_v1.py, pour que les documents
 * écrits par les services ressemblent à ceux de l'état initial. Tout est fictif.
 */

export const MENTION_FICTIF = "Document FICTIF : Calorelle et ses partenaires n'existent pas.";

/** Les 27 caractères de Windows-1252 placés de 0x80 à 0x9f, ailleurs qu'en Unicode : la table
 * entière, celle du codec cp1252 de Python, pour que les PDF des deux langages coïncident. */
const CP1252: ReadonlyMap<string, number> = new Map([
  ["€", 0x80],
  ["‚", 0x82],
  ["ƒ", 0x83],
  ["„", 0x84],
  ["…", 0x85],
  ["†", 0x86],
  ["‡", 0x87],
  ["ˆ", 0x88],
  ["‰", 0x89],
  ["Š", 0x8a],
  ["‹", 0x8b],
  ["Œ", 0x8c],
  ["Ž", 0x8e],
  ["‘", 0x91],
  ["’", 0x92],
  ["“", 0x93],
  ["”", 0x94],
  ["•", 0x95],
  ["–", 0x96],
  ["—", 0x97],
  ["˜", 0x98],
  ["™", 0x99],
  ["š", 0x9a],
  ["›", 0x9b],
  ["œ", 0x9c],
  ["ž", 0x9e],
  ["Ÿ", 0x9f],
]);

/** Un texte en Windows-1252, l'encodage de Helvetica dans le PDF ; refuse un caractère absent. */
export function cp1252(texte: string): number[] {
  return [...texte].map((caractere) => {
    const special = CP1252.get(caractere);
    if (special !== undefined) {
      return special;
    }
    const code = caractere.codePointAt(0) ?? 0;
    if (code < 0x80 || (code >= 0xa0 && code <= 0xff)) {
      return code;
    }
    throw new Error(`caractère absent de Windows-1252 : ${caractere}`);
  });
}

function octets(texte: string): number[] {
  return [...Buffer.from(texte, "latin1")];
}

/** Le PDF d'une page portant ces lignes, puis une ligne vide et la mention FICTIF. */
export function pdfUnePage(lignes: readonly string[]): Uint8Array {
  const flux: number[][] = [octets("BT"), octets("/F1 11 Tf"), octets("15 TL"), octets("56 786 Td")];
  for (const ligne of [...lignes, "", MENTION_FICTIF]) {
    const texte: number[] = [];
    for (const octet of cp1252(ligne)) {
      if (octet === 0x5c || octet === 0x28 || octet === 0x29) {
        texte.push(0x5c);
      }
      texte.push(octet);
    }
    flux.push([0x28, ...texte, 0x29, ...octets(" Tj T*")]);
  }
  flux.push(octets("ET"));
  const contenu = flux.flatMap((ligne, rang) => (rang === 0 ? ligne : [0x0a, ...ligne]));
  const objets: number[][] = [
    octets("<< /Type /Catalog /Pages 2 0 R >>"),
    octets("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    octets(
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    ),
    octets("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
    [...octets(`<< /Length ${contenu.length} >>\nstream\n`), ...contenu, ...octets("\nendstream")],
  ];
  const sortie: number[] = octets("%PDF-1.4\n");
  const positions: number[] = [];
  objets.forEach((objet, rang) => {
    positions.push(sortie.length);
    sortie.push(...octets(`${rang + 1} 0 obj\n`), ...objet, ...octets("\nendobj\n"));
  });
  const debutXref = sortie.length;
  sortie.push(...octets(`xref\n0 ${objets.length + 1}\n0000000000 65535 f \n`));
  for (const position of positions) {
    sortie.push(...octets(`${String(position).padStart(10, "0")} 00000 n \n`));
  }
  sortie.push(...octets(`trailer\n<< /Size ${objets.length + 1} /Root 1 0 R >>\nstartxref\n${debutXref}\n%%EOF\n`));
  return Uint8Array.from(sortie);
}
