import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { dateLisible, entreesDossier, joindre, lignesCourriels, piecesJointes, tableauCourriels } from "../src/vues.ts";

describe("lecture des réponses des outils", () => {
  it("lit les lignes de lister_courriels, même avec une barre dans l'objet", () => {
    const texte = [
      "m-ctc-501 | 2026-11-02T07:48:00+01:00 | Agnès Martin <agnes.martin@exemple.example> | Panne | urgent | non lu | 0 pièce(s) jointe(s)",
      "m-ctc-502 | 2026-11-02T08:10:00+01:00 | Lucas Bernard <lucas@exemple.example> | Devis | lu | 1 pièce(s) jointe(s)",
    ].join("\n");
    const lignes = lignesCourriels(texte);
    assert.equal(lignes.length, 2);
    assert.equal(lignes[0]?.objet, "Panne | urgent");
    assert.equal(lignes[0]?.lu, false);
    assert.equal(lignes[1]?.lu, true);
    assert.deepEqual(lignesCourriels("(aucun courriel)"), []);
  });

  it("lit les pièces jointes d'un courriel, virgule dans un nom comprise", () => {
    const courriel =
      "Identifiant : m-1\nPièces jointes : Facture_F-2026-1187.pdf (2048 octets), Devis, version 2.pdf (99 octets)\n\nTexte";
    assert.deepEqual(piecesJointes(courriel), ["Facture_F-2026-1187.pdf", "Devis, version 2.pdf"]);
    assert.deepEqual(piecesJointes("Pièces jointes : (aucune)"), []);
  });

  it("lit le contenu d'un dossier et joint les chemins", () => {
    assert.deepEqual(entreesDossier("factures_fournisseurs/\nmanuel.pdf\n"), [
      { nom: "factures_fournisseurs", dossier: true },
      { nom: "manuel.pdf", dossier: false },
    ]);
    assert.equal(joindre("", "administration"), "administration");
    assert.equal(joindre("administration/", "factures"), "administration/factures");
  });

  it("montre les courriels du plus récent au plus ancien, avec des dates lisibles", () => {
    const lignes = lignesCourriels(
      "m-1 | 2026-08-09T11:47:00+02:00 | A | Ancien | lu | 0 pièce(s) jointe(s)\n" +
        "m-2 | 2026-11-02T07:30:00+01:00 | B | Récent | non lu | 1 pièce(s) jointe(s)",
    );
    const html = tableauCourriels("contact@calorelle.example", lignes);
    assert.ok(html.indexOf("Récent") < html.indexOf("Ancien"));
    assert.ok(html.includes("2026-11-02 07:30"));
    assert.equal(dateLisible("hier"), "hier");
  });
});
