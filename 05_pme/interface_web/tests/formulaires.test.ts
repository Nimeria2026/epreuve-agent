import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { champs, formulaire, LIGNES_DE_SAISIE, lireArguments, type Schema } from "../src/formulaires.ts";

// Le schéma de creer_devis, tel que le SDK le tire du schéma zod de la facturation.
const CREER_DEVIS: Schema = {
  type: "object",
  properties: {
    client: { type: "string", description: "code du client, par exemple c-0142" },
    objet: { type: "string", description: "objet du devis" },
    lignes: {
      type: "array",
      items: {
        type: "object",
        properties: {
          code: { type: "string", description: "code d'une ligne du tarif" },
          quantite: { type: "number", description: "quantité, au centième près" },
          taux_tva: { type: "number", description: "taux de TVA en pour cent : 5.5, 10 ou 20" },
        },
        required: ["code", "quantite", "taux_tva"],
      },
    },
    remise_pourcent: { type: "number", description: "remise en pour cent, 0 par défaut" },
  },
  required: ["client", "objet", "lignes"],
};

const LISTER_COURRIELS: Schema = {
  type: "object",
  properties: {
    boite: { type: "string" },
    dossier: { type: "string", enum: ["reception", "envoyes"], default: "reception" },
    non_lus_seulement: { type: "boolean", default: false },
  },
};

const ENVOYER: Schema = {
  type: "object",
  properties: {
    a: { type: "array", items: { type: "string" }, description: "destinataires" },
    cc: { type: "array", items: { type: "string" }, default: [] },
    texte: { type: "string" },
  },
  required: ["a", "texte"],
};

describe("champs tirés d'un schéma", () => {
  it("reconnaît texte, nombre, choix, case, liste et tableau de lignes", () => {
    const genres = Object.fromEntries(
      [...champs(CREER_DEVIS), ...champs(LISTER_COURRIELS), ...champs(ENVOYER)].map((c) => [c.nom, c.genre]),
    );
    assert.deepEqual(genres, {
      client: "texte",
      objet: "texte",
      lignes: "lignes",
      remise_pourcent: "nombre",
      boite: "texte",
      dossier: "choix",
      non_lus_seulement: "booleen",
      a: "liste",
      cc: "liste",
      texte: "texte",
    });
  });
});

describe("lecture d'un formulaire envoyé", () => {
  it("lit les lignes remplies d'un devis, avec la virgule décimale, et ignore les lignes vides", () => {
    const donnees = new URLSearchParams({
      client: "c-0142",
      objet: "Deux radiateurs",
      "lignes.0.code": "RAD-01",
      "lignes.0.quantite": "2",
      "lignes.0.taux_tva": "5,5",
      "lignes.3.code": "MO-H",
      "lignes.3.quantite": "1,5",
      "lignes.3.taux_tva": "10",
      remise_pourcent: "",
    });
    const lecture = lireArguments(champs(CREER_DEVIS), donnees);
    assert.deepEqual(lecture.erreurs, []);
    assert.deepEqual(lecture.arguments, {
      client: "c-0142",
      objet: "Deux radiateurs",
      lignes: [
        { code: "RAD-01", quantite: 2, taux_tva: 5.5 },
        { code: "MO-H", quantite: 1.5, taux_tva: 10 },
      ],
    });
  });

  it("découpe une liste par lignes, virgules ou points-virgules, et omet un champ facultatif vide", () => {
    const donnees = new URLSearchParams({
      a: "marc.duval@calorelle.example\r\njulie.perrin@calorelle.example; ",
      cc: "",
      texte: "Bonjour",
    });
    const lecture = lireArguments(champs(ENVOYER), donnees);
    assert.deepEqual(lecture.arguments, {
      a: ["marc.duval@calorelle.example", "julie.perrin@calorelle.example"],
      texte: "Bonjour",
    });
  });

  it("refuse un nombre illisible, un choix hors liste et une ligne incomplète, sans rien appeler", () => {
    const devis = lireArguments(
      champs(CREER_DEVIS),
      new URLSearchParams({ client: "c", objet: "o", "lignes.0.code": "X", "lignes.0.quantite": "deux" }),
    );
    assert.equal(devis.erreurs.length, 2);
    assert.ok(devis.erreurs.some((e) => e.includes("« deux » n'est pas un nombre")));
    assert.ok(devis.erreurs.some((e) => e.includes("taux_tva : un nombre est attendu")));
    const liste = lireArguments(champs(LISTER_COURRIELS), new URLSearchParams({ dossier: "corbeille" }));
    assert.deepEqual(liste.erreurs, ["dossier : « corbeille » n'est pas proposé"]);
  });

  it("lit une case cochée ou non", () => {
    const coche = lireArguments(champs(LISTER_COURRIELS), new URLSearchParams({ non_lus_seulement: "oui" }));
    const vide = lireArguments(champs(LISTER_COURRIELS), new URLSearchParams());
    assert.equal(coche.arguments.non_lus_seulement, true);
    assert.equal(vide.arguments.non_lus_seulement, false);
  });
});

describe("affichage d'un formulaire", () => {
  it("montre un champ fixé sans le rendre modifiable, échappe les valeurs, et offre les lignes d'un devis", () => {
    const html = formulaire(
      "/outil/creer_devis",
      champs(CREER_DEVIS),
      { fixes: { client: "c-0142" }, valeurs: { objet: '<script>"x"</script>' } },
      "Valider",
      { _retour: "/service/facturation" },
    );
    assert.ok(html.includes('<input type="hidden" name="client" value="c-0142">'));
    assert.ok(!html.includes('name="client" id='));
    assert.ok(html.includes("&lt;script&gt;&quot;x&quot;&lt;/script&gt;"));
    assert.ok(!html.includes("<script>"));
    assert.equal(html.split('name="lignes.').length - 1, LIGNES_DE_SAISIE * 3);
    assert.ok(html.includes('name="_retour" value="/service/facturation"'));
  });
});
