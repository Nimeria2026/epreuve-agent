// Le poste humain : un serveur web local qui chronomètre une personne sur une tâche de la PME.
//
// Trois états. En attente, la page propose « Commencer » : l'énoncé n'est pas encore montré, le
// chronomètre ne tourne pas. En cours, la personne travaille dans la PME par les vues de chaque
// service ; chaque action passe par le relais d'EASE. Fini, après « J'ai fini » ou « Abandonner »
// confirmés : le poste écrit sa sortie (contrat sortie_candidat) et s'arrête ; la page attend alors
// le poste de la tâche suivante. Aucun retour sur la réussite n'est donné (conception, §3).

import { randomUUID } from "node:crypto";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { SortieCandidat } from "@poa/commun/contrats/sortie_candidat";
import { type Champ, champs, formulaire, lireArguments } from "./formulaires.ts";
import { echapper, lien, type Navigation, page } from "./html.ts";
import { AUTRES, type Outil, type Pme, type Reponse, SERVICES, type Service, serviceDe } from "./pme.ts";
import { entreesDossier, filAriane, lignesCourriels, listeDossier, piecesJointes, tableauCourriels } from "./vues.ts";

export interface OptionsPoste {
  readonly pme: Pme;
  readonly enonce: string;
  readonly ecrireSortie: (sortie: SortieCandidat) => void;
  /** Appelé une fois la sortie écrite et la dernière page envoyée. */
  readonly quitter: () => void;
  /** Horloge en millisecondes ; performance.now() par défaut. */
  readonly maintenant?: () => number;
}

type Etat = "attente" | "en_cours" | "fini";

const TAILLE_MAX_CORPS = 1_000_000;
const PAUSE_AVANT_ARRET_MS = 300;
const VUES_DEDIEES: Readonly<Record<string, string>> = { messagerie: "/messagerie", dossiers: "/dossiers" };

function envoyer(reponse: ServerResponse, code: number, type: string, contenu: string): void {
  reponse.writeHead(code, { "content-type": `${type}; charset=utf-8`, "cache-control": "no-store" });
  reponse.end(contenu);
}

function rediriger(reponse: ServerResponse, cible: string): void {
  reponse.writeHead(303, { location: cible, "cache-control": "no-store" });
  reponse.end();
}

async function lireCorps(requete: IncomingMessage): Promise<URLSearchParams> {
  const morceaux: Buffer[] = [];
  let taille = 0;
  for await (const morceau of requete) {
    const tampon = morceau as Buffer;
    taille += tampon.length;
    if (taille > TAILLE_MAX_CORPS) {
      throw new Error("formulaire trop volumineux");
    }
    morceaux.push(tampon);
  }
  return new URLSearchParams(Buffer.concat(morceaux).toString("utf-8"));
}

/** Une adresse de retour sûre : un chemin local, jamais une autre origine. */
function retourSur(valeur: string | null, defaut: string): string {
  return valeur?.startsWith("/") && !valeur.startsWith("//") ? valeur : defaut;
}

function blocReponse(reponse: Reponse): string {
  return `<div class="texte${reponse.erreur ? " erreur" : ""}">${echapper(reponse.texte || "(réponse vide)")}</div>`;
}

function lignes(texte: string): string[] {
  return texte.split("\n").filter((l) => l.trim() !== "" && !l.startsWith("("));
}

export function creerPoste(options: OptionsPoste): Server {
  const maintenant = options.maintenant ?? (() => performance.now());
  const instance = randomUUID();
  let etat: Etat = "attente";
  let debut = 0;
  const { pme } = options;

  function terminer(sortie: SortieCandidat): void {
    options.ecrireSortie(sortie);
    etat = "fini";
    setTimeout(options.quitter, PAUSE_AVANT_ARRET_MS);
  }

  async function navigation(): Promise<Navigation[]> {
    const presents = new Set((await pme.outils()).map((o) => serviceDe(o.nom).cle));
    const services = [...SERVICES, AUTRES].filter((s) => presents.has(s.cle));
    return [
      { cle: "accueil", nom: "Accueil", chemin: "/accueil" },
      ...services.map((s) => ({ cle: s.cle, nom: s.nom, chemin: VUES_DEDIEES[s.cle] ?? `/service/${s.cle}` })),
    ];
  }

  async function pageEnCours(titre: string, actif: string, corps: string): Promise<string> {
    return page({ titre, enonce: options.enonce, navigation: await navigation(), actif }, corps);
  }

  async function outilsDu(service: Service): Promise<Outil[]> {
    const outils = await pme.outils();
    if (service.cle === AUTRES.cle) {
      return outils.filter((o) => serviceDe(o.nom).cle === AUTRES.cle);
    }
    return service.outils.flatMap((nom) => outils.filter((o) => o.nom === nom));
  }

  function blocOutil(outil: Outil, retour: string, fixes: Record<string, string> = {}, liste?: Champ[]): string {
    const bouton = outil.lectureSeule ? "Consulter" : "Valider";
    const corps = formulaire(`/outil/${outil.nom}`, liste ?? champs(outil.schema), { fixes }, bouton, {
      _retour: retour,
    });
    return (
      `<details class="outil"><summary>${echapper(outil.titre)}</summary>` +
      `<p>${echapper(outil.description)}</p>${corps}</details>`
    );
  }

  // ---------------------------------------------------------------------------------- pages

  function pageAttente(): string {
    return page(
      { titre: "Poste humain" },
      `<h1>Poste humain</h1><p>La PME est prête. Le chronomètre part au clic sur « Commencer » et s'arrête quand ` +
        `tu confirmes « J'ai fini ». Travaille d'une traite : un essai interrompu est écarté.</p>` +
        `<form method="post" action="/commencer"><button type="submit">Commencer</button></form>`,
    );
  }

  function pageFini(message: string): string {
    const script =
      `const instance = ${JSON.stringify(instance)};` +
      "async function verifier() { try { const r = await fetch('/etat', { cache: 'no-store' }); " +
      "const e = await r.json(); if (e.instance !== instance) { location.href = '/'; return; } } catch (e) {} " +
      "setTimeout(verifier, 2000); } setTimeout(verifier, 2000);";
    return page(
      { titre: "Poste humain", script },
      `<h1>${echapper(message)}</h1><p>La tâche suivante se prépare : cette page s'ouvrira d'elle-même. ` +
        `Si c'était la dernière, la séance est finie ; le terminal où tu as lancé make humain le dit.</p>`,
    );
  }

  async function pageAccueil(): Promise<string> {
    const services = (await navigation()).filter((n) => n.cle !== "accueil");
    const liens = services.map((s) => `<li><a href="${lien(s.chemin)}">${echapper(s.nom)}</a></li>`).join("");
    return pageEnCours(
      "Accueil",
      "accueil",
      `<p>Le chronomètre tourne. Les services de la PME ouverts pour cette tâche :</p><ul>${liens}</ul>`,
    );
  }

  async function pageMessagerie(url: URL): Promise<string> {
    const boites = lignes((await pme.appeler("lister_boites", {})).texte);
    const boite = url.searchParams.get("boite") ?? boites[0] ?? "";
    const dossier = url.searchParams.get("dossier") === "envoyes" ? "envoyes" : "reception";
    const arguments_: Record<string, unknown> = { dossier };
    if (boite !== "") {
      arguments_.boite = boite;
    }
    const liste = await pme.appeler("lister_courriels", arguments_);
    const choixBoites = boites
      .map((b) => {
        const nom = b === boite ? `<strong>${echapper(b)}</strong>` : echapper(b);
        return `<li><a href="${lien("/messagerie", { boite: b })}">${nom}</a></li>`;
      })
      .join("");
    const dossiers = [
      ["reception", "Réception"],
      ["envoyes", "Envoyés"],
    ]
      .map(([cle = "", nom = ""]) => {
        const texte = cle === dossier ? `<strong>${nom}</strong>` : nom;
        return `<a href="${lien("/messagerie", { boite, dossier: cle })}">${texte}</a>`;
      })
      .join(" · ");
    const tableau = liste.erreur ? blocReponse(liste) : tableauCourriels(boite, lignesCourriels(liste.texte));
    return pageEnCours(
      "Messagerie",
      "messagerie",
      `<div class="colonnes"><aside><h3>Boîtes</h3><ul>${choixBoites}</ul>` +
        `<p><a href="${lien("/messagerie/ecrire", { boite })}">Écrire un courriel</a></p>` +
        `<p><a href="${lien("/service/messagerie")}">Tous les outils de la messagerie</a></p></aside>` +
        `<section><h2>${echapper(boite)}</h2><p>${dossiers}</p>${tableau}</section></div>`,
    );
  }

  async function pageCourriel(url: URL): Promise<string> {
    const boite = url.searchParams.get("boite") ?? "";
    const identifiant = url.searchParams.get("identifiant") ?? "";
    const lecture = await pme.appeler("lire_courriel", boite === "" ? { identifiant } : { boite, identifiant });
    const retour = `/messagerie?${new URLSearchParams({ boite }).toString()}`;
    const fixes: Record<string, string> = boite === "" ? { identifiant } : { boite, identifiant };
    const blocs: string[] = [];
    for (const nom of ["repondre", "transferer", "enregistrer_piece_jointe"]) {
      const outil = await pme.outil(nom);
      if (outil === undefined || lecture.erreur) {
        continue;
      }
      let liste = champs(outil.schema);
      const pieces = piecesJointes(lecture.texte);
      if (nom === "enregistrer_piece_jointe") {
        if (pieces.length === 0) {
          continue;
        }
        liste = liste.map(
          (c): Champ =>
            c.nom === "piece"
              ? {
                  nom: c.nom,
                  description: c.description,
                  obligatoire: c.obligatoire,
                  genre: "choix",
                  options: pieces,
                  defaut: pieces[0],
                }
              : c,
        );
      }
      blocs.push(blocOutil(outil, retour, fixes, liste));
    }
    return pageEnCours(
      "Courriel",
      "messagerie",
      `<p><a href="${lien(retour)}">Retour à la boîte</a></p>${blocReponse(lecture)}${blocs.join("")}`,
    );
  }

  async function pageEcrire(url: URL): Promise<string> {
    const outil = await pme.outil("envoyer");
    const boite = url.searchParams.get("boite") ?? "";
    if (outil === undefined) {
      return pageEnCours("Écrire", "messagerie", "<p>La messagerie n'envoie pas de courriel pour cette tâche.</p>");
    }
    const retour = `/messagerie?${new URLSearchParams({ boite }).toString()}`;
    const corps = formulaire(
      "/outil/envoyer",
      champs(outil.schema),
      { fixes: boite === "" ? {} : { boite } },
      "Envoyer",
      { _retour: retour },
    );
    return pageEnCours("Écrire un courriel", "messagerie", `<h2>Écrire un courriel</h2>${corps}`);
  }

  async function pageDossiers(url: URL): Promise<string> {
    const chemin = url.searchParams.get("chemin") ?? "";
    const reponse = await pme.appeler("lister", { dossier: chemin });
    const contenu = reponse.erreur ? blocReponse(reponse) : listeDossier(chemin, entreesDossier(reponse.texte));
    return pageEnCours(
      "Dossiers",
      "dossiers",
      `${filAriane(chemin)}${contenu}<p><a href="${lien("/service/dossiers")}">Tous les outils des dossiers</a></p>`,
    );
  }

  async function pageDocument(url: URL): Promise<string> {
    const chemin = url.searchParams.get("chemin") ?? "";
    const parent = chemin.includes("/") ? chemin.slice(0, chemin.lastIndexOf("/")) : "";
    const retour = `/dossiers?${new URLSearchParams({ chemin: parent }).toString()}`;
    const lecture = await pme.appeler("lire", { chemin });
    const blocs: string[] = [];
    for (const nom of ["deplacer", "copier"]) {
      const outil = await pme.outil(nom);
      if (outil !== undefined && !lecture.erreur) {
        blocs.push(blocOutil(outil, retour, { source: chemin }));
      }
    }
    return pageEnCours(
      "Document",
      "dossiers",
      `${filAriane(parent)}<h2>${echapper(chemin)}</h2>${blocReponse(lecture)}${blocs.join("")}`,
    );
  }

  async function pageService(cle: string): Promise<string | undefined> {
    const service = [...SERVICES, AUTRES].find((s) => s.cle === cle);
    if (service === undefined) {
      return undefined;
    }
    const outils = await outilsDu(service);
    const blocs = outils.map((o) => blocOutil(o, `/service/${cle}`)).join("");
    return pageEnCours(service.nom, cle, `<h2>${echapper(service.nom)}</h2>${blocs || "<p>Aucun outil.</p>"}`);
  }

  async function pageOutil(outil: Outil, valeurs: Record<string, string>, retour: string, haut = ""): Promise<string> {
    const service = serviceDe(outil.nom);
    const bouton = outil.lectureSeule ? "Consulter" : "Valider";
    const corps = formulaire(`/outil/${outil.nom}`, champs(outil.schema), { valeurs }, bouton, { _retour: retour });
    return pageEnCours(
      outil.titre,
      service.cle,
      `${haut}<h2>${echapper(outil.titre)}</h2><p>${echapper(outil.description)}</p>${corps}` +
        `<p><a href="${lien(retour)}">Retour</a></p>`,
    );
  }

  async function appelerOutil(outil: Outil, donnees: URLSearchParams): Promise<string> {
    const service = serviceDe(outil.nom);
    const retour = retourSur(donnees.get("_retour"), VUES_DEDIEES[service.cle] ?? `/service/${service.cle}`);
    const valeurs = Object.fromEntries([...donnees].filter(([cle]) => !cle.startsWith("_")));
    const lecture = lireArguments(champs(outil.schema), donnees);
    if (lecture.erreurs.length > 0) {
      const erreurs = lecture.erreurs.map((e) => `<li>${echapper(e)}</li>`).join("");
      return pageOutil(outil, valeurs, retour, `<div class="texte erreur"><ul>${erreurs}</ul></div>`);
    }
    const reponse = await pme.appeler(outil.nom, lecture.arguments);
    const suite = `<p><a href="${lien(retour)}">Continuer</a></p>`;
    if (outil.lectureSeule) {
      return pageOutil(outil, valeurs, retour, `<h2>Résultat</h2>${blocReponse(reponse)}${suite}`);
    }
    return pageEnCours(outil.titre, service.cle, `<h2>${echapper(outil.titre)}</h2>${blocReponse(reponse)}${suite}`);
  }

  function pageConfirmer(question: string, action: string, bouton: string): string {
    return page(
      { titre: "Confirmer" },
      `<h1>${echapper(question)}</h1><form method="post" action="${echapper(action)}">` +
        `<button type="submit">${echapper(bouton)}</button></form><p><a href="/accueil">Non, je continue</a></p>`,
    );
  }

  // ------------------------------------------------------------------------------- routage

  async function traiter(requete: IncomingMessage, reponse: ServerResponse): Promise<void> {
    const url = new URL(requete.url ?? "/", "http://poste.local");
    const chemin = url.pathname;
    const methode = requete.method ?? "GET";
    if (methode === "GET" && chemin === "/etat") {
      envoyer(reponse, 200, "application/json", JSON.stringify({ instance, etat }));
      return;
    }
    if (chemin === "/") {
      if (etat === "en_cours") {
        rediriger(reponse, "/accueil");
      } else {
        envoyer(reponse, 200, "text/html", etat === "attente" ? pageAttente() : pageFini("Merci."));
      }
      return;
    }
    if (methode === "POST" && chemin === "/commencer") {
      if (etat === "attente") {
        debut = maintenant();
        etat = "en_cours";
      }
      rediriger(reponse, "/accueil");
      return;
    }
    if (etat !== "en_cours") {
      rediriger(reponse, "/");
      return;
    }
    if (methode === "POST") {
      await traiterEnvoi(chemin, requete, reponse);
      return;
    }
    let contenu: string | undefined;
    if (chemin === "/accueil") {
      contenu = await pageAccueil();
    } else if (chemin === "/messagerie") {
      contenu = await pageMessagerie(url);
    } else if (chemin === "/messagerie/lire") {
      contenu = await pageCourriel(url);
    } else if (chemin === "/messagerie/ecrire") {
      contenu = await pageEcrire(url);
    } else if (chemin === "/dossiers") {
      contenu = await pageDossiers(url);
    } else if (chemin === "/dossiers/lire") {
      contenu = await pageDocument(url);
    } else if (chemin.startsWith("/service/")) {
      contenu = await pageService(chemin.slice("/service/".length));
    } else if (chemin.startsWith("/outil/")) {
      const outil = await pme.outil(chemin.slice("/outil/".length));
      if (outil !== undefined) {
        const valeurs = Object.fromEntries([...url.searchParams].filter(([cle]) => !cle.startsWith("_")));
        const service = serviceDe(outil.nom);
        const retour = retourSur(
          url.searchParams.get("_retour"),
          VUES_DEDIEES[service.cle] ?? `/service/${service.cle}`,
        );
        contenu = await pageOutil(outil, valeurs, retour);
      }
    }
    if (contenu === undefined) {
      envoyer(reponse, 404, "text/html", page({ titre: "Introuvable" }, "<p>Page introuvable.</p>"));
    } else {
      envoyer(reponse, 200, "text/html", contenu);
    }
  }

  async function traiterEnvoi(chemin: string, requete: IncomingMessage, reponse: ServerResponse): Promise<void> {
    if (chemin === "/fini") {
      envoyer(reponse, 200, "text/html", pageConfirmer("Tu as fini la tâche ?", "/fini/confirmer", "Oui, j'ai fini"));
      return;
    }
    if (chemin === "/abandon") {
      const question = "Abandonner cet essai ? Il sera écarté, et refait plus tard.";
      envoyer(reponse, 200, "text/html", pageConfirmer(question, "/abandon/confirmer", "Oui, abandonner"));
      return;
    }
    if (chemin === "/fini/confirmer") {
      const secondes = Math.round(maintenant() - debut) / 1000;
      terminer({
        fin: "termine",
        detail: null,
        appels_modele: 0,
        consommation: {},
        modeles_renvoyes: {},
        duree_chronometree_secondes: secondes,
      });
      envoyer(reponse, 200, "text/html", pageFini("Merci, tâche suivante."));
      return;
    }
    if (chemin === "/abandon/confirmer") {
      terminer({
        fin: "erreur",
        detail: "essai abandonné au poste humain",
        appels_modele: 0,
        consommation: {},
        modeles_renvoyes: {},
      });
      envoyer(reponse, 200, "text/html", pageFini("Essai écarté."));
      return;
    }
    if (chemin.startsWith("/outil/")) {
      const outil = await pme.outil(chemin.slice("/outil/".length));
      if (outil !== undefined) {
        envoyer(reponse, 200, "text/html", await appelerOutil(outil, await lireCorps(requete)));
        return;
      }
    }
    envoyer(reponse, 404, "text/html", page({ titre: "Introuvable" }, "<p>Page introuvable.</p>"));
  }

  return createServer((requete, reponse) => {
    traiter(requete, reponse).catch((erreur: unknown) => {
      const message = erreur instanceof Error ? erreur.message : String(erreur);
      envoyer(
        reponse,
        500,
        "text/html",
        page({ titre: "Erreur" }, `<div class="texte erreur">${echapper(message)}</div>`),
      );
    });
  });
}
