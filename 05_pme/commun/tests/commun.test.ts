import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import { premierDossier, resoudreDansRacine } from "../src/chemins.ts";
import type { Courriel } from "../src/contrats/courriel.ts";
import { chargerAccesDossiers, chargerPersonne, peutOuvrir } from "../src/droits.ts";
import { ErreurOutil } from "../src/erreurs.ts";
import { MENTION_FICTIF, pdfUnePage } from "../src/pdf.ts";
import { PARAMETRES_CALORELLE, parametresSociete } from "../src/societe.ts";
import { ecartsContrat } from "../src/validation.ts";

const RACINE_DEPOT = new URL("../../../", import.meta.url);
const ETAT_V1 = new URL("05_pme/societes/calorelle/v1/", RACINE_DEPOT).pathname;

describe("validation par les contrats de 01_contrats/", () => {
  const exemple = JSON.parse(
    readFileSync(new URL("01_contrats/exemples/courriel_facture.json", RACINE_DEPOT), "utf-8"),
  ) as Courriel;

  it("accepte l'exemple de courriel", () => {
    assert.deepEqual(ecartsContrat("courriel", exemple), []);
  });

  it("refuse une adresse réelle : seules les adresses en .example sont permises", () => {
    const ecarts = ecartsContrat("courriel", { ...exemple, a: ["patrick@gmail.com"] });
    assert.ok(ecarts.some((e) => e.startsWith("/a/0")));
  });

  it("refuse une date sans décalage horaire et un champ inconnu", () => {
    assert.notDeepEqual(ecartsContrat("courriel", { ...exemple, date: "2026-11-02 08:12" }), []);
    assert.notDeepEqual(ecartsContrat("courriel", { ...exemple, priorite: "haute" }), []);
  });
});

describe("chemins confinés à une racine", () => {
  const racine = mkdtempSync(path.join(tmpdir(), "poa-chemins-"));

  it("résout un chemin relatif à l'intérieur", () => {
    assert.equal(resoudreDansRacine(racine, "a/b.txt"), path.join(racine, "a", "b.txt"));
  });

  it("refuse les chemins absolus, les remontées et les liens vers l'extérieur", () => {
    assert.throws(() => resoudreDansRacine(racine, "/etc/passwd"), ErreurOutil);
    assert.throws(() => resoudreDansRacine(racine, "../voisin.txt"), ErreurOutil);
    assert.throws(() => resoudreDansRacine(racine, "a/../../voisin.txt"), ErreurOutil);
    symlinkSync(tmpdir(), path.join(racine, "sortie"));
    assert.throws(() => resoudreDansRacine(racine, "sortie"), ErreurOutil);
  });

  it("donne le premier dossier d'un chemin", () => {
    assert.equal(premierDossier("administration/factures/x.pdf"), "administration");
    assert.equal(premierDossier("./clients/"), "clients");
    assert.equal(premierDossier(""), "");
  });
});

describe("droits de la personne servie, sur les données v1", () => {
  const acces = chargerAccesDossiers(ETAT_V1);

  it("ouvre l'administration au comptable et la ferme aux RH", () => {
    const patrick = chargerPersonne(ETAT_V1, "patrick.roux");
    assert.ok(peutOuvrir(acces, patrick, "administration"));
    assert.ok(!peutOuvrir(acces, patrick, "rh"));
    assert.ok(!peutOuvrir(acces, patrick, "clients"));
  });

  it("ouvre les clients à la chargée d'affaires", () => {
    assert.ok(peutOuvrir(acces, chargerPersonne(ETAT_V1, "julie.perrin"), "clients"));
  });

  it("ouvre le dossier commun à tout le personnel, même sans droit particulier", () => {
    const enzo = chargerPersonne(ETAT_V1, "enzo.caron");
    assert.ok(peutOuvrir(acces, enzo, "commun"));
    assert.ok(!peutOuvrir(acces, enzo, "clients"));
  });

  it("ferme par défaut un dossier que la liste ne prévoit pas", () => {
    assert.ok(!peutOuvrir(acces, chargerPersonne(ETAT_V1, "helene.marchal"), "inconnu"));
  });

  it("refuse une personne absente de l'organigramme", () => {
    assert.throws(() => chargerPersonne(ETAT_V1, "personne.inconnue"), /personne inconnue/);
  });
});

describe("pdf d'une page", () => {
  it("échappe parenthèses et barres obliques, écrit en Windows-1252, finit par la mention FICTIF", () => {
    const texte = Buffer.from(pdfUnePage(["Total : 1 234,56 € (TTC) a\\b"])).toString("latin1");
    assert.ok(texte.startsWith("%PDF-1.4\n") && texte.endsWith("%%EOF\n"));
    assert.ok(texte.includes("(Total : 1 234,56 \x80 \\(TTC\\) a\\\\b) Tj T*"));
    assert.ok(texte.includes(`(${MENTION_FICTIF}) Tj T*`));
  });

  it("refuse un caractère que Helvetica en Windows-1252 n'a pas", () => {
    assert.throws(() => pdfUnePage(["→"]), /absent de Windows-1252/u);
  });
});

describe("paramètres de société (ADR 0006)", () => {
  it("rend ceux de Calorelle quand l'état n'a pas de entreprise/societe.yaml", () => {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-societe-"));
    assert.deepEqual(parametresSociete(etat), PARAMETRES_CALORELLE);
    const v3 = new URL("../../societes/calorelle/v3/", import.meta.url).pathname;
    assert.deepEqual(parametresSociete(v3), PARAMETRES_CALORELLE);
  });

  it("lit entreprise/societe.yaml, et refuse un fichier hors contrat", () => {
    const etat = mkdtempSync(path.join(tmpdir(), "poa-societe-"));
    mkdirSync(path.join(etat, "entreprise"));
    const fichier = path.join(etat, "entreprise", "societe.yaml");
    writeFileSync(fichier, "nom: Essai\ndomaine: essai.example\ndossier_fiches_fournisseurs: artisans\n");
    assert.deepEqual(parametresSociete(etat), {
      nom: "Essai",
      domaine: "essai.example",
      dossier_fiches_fournisseurs: "artisans",
    });
    writeFileSync(fichier, "nom: Essai\ndomaine: essai.fr\ndossier_fiches_fournisseurs: artisans\n");
    assert.throws(() => parametresSociete(etat), /paramètres de société mal formés/u);
  });
});
