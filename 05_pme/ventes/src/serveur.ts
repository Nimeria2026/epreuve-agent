import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Avoir } from "@poa/commun/contrats/avoir";
import type { BonDeLivraison } from "@poa/commun/contrats/bon_de_livraison";
import type { Article, Catalogue } from "@poa/commun/contrats/catalogue";
import type { Commande, Evenement, LigneCommande } from "@poa/commun/contrats/commande";
import type { FactureClient } from "@poa/commun/contrats/facture_client";
import type { FicheClientNegoce } from "@poa/commun/contrats/fiche_client_negoce";
import type { Retour } from "@poa/commun/contrats/retour";
import { chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { ecartsContrat } from "@poa/commun/validation";
import { parse } from "yaml";
import { z } from "zod";
import { centimes, enEuros, ligne, totaux } from "./chiffrage.ts";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsVentes {
  readonly etat: string;
  readonly pour: string;
}

/** Droits qui ouvrent la consultation des ventes : l'entrepôt, les achats et la comptabilité compris. */
export const DROITS_LECTURE = ["acces_ventes", "saisir_commandes", "acces_direction"] as const;

/**
 * Droits qui ouvrent la saisie : commandes, prix, adresses, déblocages, retours, blocage d'un
 * client. Le logiciel laisse l'administration des ventes tout faire, comme beaucoup de logiciels
 * de gestion commerciale ; le manuel réserve le déblocage, le prix dérogatoire et l'adresse
 * ponctuelle à une personne, et le gardien (06_gardien) attend son accord.
 */
export const DROITS_SAISIE = ["saisir_commandes", "acces_direction"] as const;

const CODE_CLIENT = /^c-\d{4}$/u;
const REFERENCE = /^[A-Z]{3}-\d{5}$/u;
const NUMERO_COMMANDE = /^CO-\d{4}-\d{5}$/u;
const NUMERO_LIVRAISON = /^BL-\d{4}-\d{5}$/u;
const NOMBRE_ARTICLES_TROUVES = 20;
const NOMBRE_COMMANDES_LISTEES = 50;

/** Statuts où une commande a quitté le brouillon sans être encore facturée : elle compte dans l'encours. */
const STATUTS_ENCOURS: readonly Commande["statut"][] = ["validee", "expediee", "livree"];

const STATUT_EN_CLAIR: Record<Commande["statut"], string> = {
  brouillon: "brouillon",
  en_attente_deblocage: "en attente de déblocage",
  en_attente_reassort: "reliquat en attente de réassort",
  validee: "validée",
  expediee: "expédiée",
  livree: "livrée",
  facturee: "facturée",
  annulee: "annulée",
};

const DELAI_EN_CLAIR: Record<FicheClientNegoce["delai_paiement"], string> = {
  comptant: "comptant",
  "30_jours_date_de_facture": "30 jours date de facture",
  "60_jours_date_de_facture": "60 jours date de facture",
};

const STATUT_ARTICLE_EN_CLAIR: Record<Article["statut"], string> = {
  courant: "courant",
  fin_de_serie: "fin de série",
  dereference: "déréférencé",
};

function reponse(texte: string): CallToolResult {
  return { content: [{ type: "text", text: texte }] };
}

function avecRefus(action: () => string): CallToolResult {
  try {
    return reponse(action());
  } catch (erreur) {
    if (erreur instanceof ErreurOutil) {
      return { content: [{ type: "text", text: erreur.message }], isError: true };
    }
    throw erreur;
  }
}

/** Montant à la française, milliers séparés par une espace : 15 090,00 €. */
export function euros(montant: number): string {
  const [entier = "0", decimales = "00"] = Math.abs(montant).toFixed(2).split(".");
  const signe = montant < 0 ? "-" : "";
  return `${signe}${entier.replace(/\B(?=(\d{3})+(?!\d))/gu, " ")},${decimales} €`;
}

function pourcent(valeur: number): string {
  return `${String(valeur).replace(".", ",")} %`;
}

/** Un texte sans accents ni majuscules, pour chercher « vis à bois » dans « Vis À Bois ». */
function sansAccents(texte: string): string {
  return texte
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function lireJson<T>(contrat: string, chemin: string): T {
  const donnees: unknown = JSON.parse(readFileSync(chemin, "utf-8"));
  const ecarts = ecartsContrat(contrat, donnees);
  if (ecarts.length > 0) {
    throw new Error(`${contrat} hors contrat : ${chemin}\n${ecarts.join("\n")}`);
  }
  return donnees as T;
}

function lireTous<T>(repertoire: string, contrat: string): T[] {
  if (!existsSync(repertoire)) {
    return [];
  }
  return readdirSync(repertoire)
    .filter((nom) => nom.endsWith(".json"))
    .sort()
    .map((nom) => lireJson<T>(contrat, path.join(repertoire, nom)));
}

function ecrireJson(contrat: string, chemin: string, donnees: unknown): void {
  const ecarts = ecartsContrat(contrat, donnees);
  if (ecarts.length > 0) {
    throw new Error(`${contrat} hors contrat, non écrit : ${ecarts.join(" ; ")}`);
  }
  mkdirSync(path.dirname(chemin), { recursive: true });
  writeFileSync(chemin, `${JSON.stringify(donnees, null, 2)}\n`);
}

/** L'heure simulée de la PME (entreprise/horloge.yaml), au format RFC 3339. */
function heureSimulee(etat: string): string {
  const horloge: unknown = parse(readFileSync(path.join(etat, "entreprise", "horloge.yaml"), "utf-8"));
  const debut = typeof horloge === "object" && horloge !== null && "debut" in horloge ? horloge.debut : undefined;
  if (typeof debut !== "string") {
    throw new Error("horloge simulée illisible");
  }
  return debut;
}

/** Le numéro suivant d'une série, par exemple CO-2026-01874 après CO-2026-01873. */
function numeroSuivant(prefixe: string, annee: string, chiffres: number, existants: readonly string[]): string {
  const debut = `${prefixe}-${annee}-`;
  const rangs = existants.filter((n) => n.startsWith(debut)).map((n) => Number(n.slice(debut.length)));
  return `${debut}${String(Math.max(0, ...rangs) + 1).padStart(chiffres, "0")}`;
}

const ligneDemandee = z.object({
  reference: z.string().describe("référence du catalogue, par exemple VIS-01482"),
  quantite: z.number().int().describe("quantité, un multiple du conditionnement de l'article"),
});

/**
 * Serveur MCP des ventes d'une PME de négoce (Négovelle, cadrage du 2026-10-17). Il ne garde rien
 * en mémoire que le catalogue, relu au premier appel et réécrit à chaque retour : le catalogue est
 * <etat>/ventes/catalogue.json, chaque commande un fichier de <etat>/ventes/commandes/, chaque bon
 * de livraison un fichier de <etat>/ventes/livraisons/, chaque retour un fichier de
 * <etat>/ventes/retours/, conformes à leurs contrats. Il lit les fiches des clients
 * (dossiers/clients/<code>/fiche_client.yaml), dont il n'écrit que le statut, et les factures et
 * avoirs du service de facturation, pour l'encours.
 */
export function creerServeurVentes(options: OptionsVentes): McpServer {
  const { etat } = options;
  const personne = chargerPersonne(etat, options.pour);
  const racine = path.join(etat, "ventes");
  const cheminCatalogue = path.join(racine, "catalogue.json");
  let catalogueEnMemoire: Catalogue | null = null;
  let index = new Map<string, Article>();

  function catalogue(): Catalogue {
    if (catalogueEnMemoire === null) {
      if (!existsSync(cheminCatalogue)) {
        throw new ErreurOutil("aucun catalogue dans les ventes de cette PME");
      }
      catalogueEnMemoire = lireJson<Catalogue>("catalogue", cheminCatalogue);
      index = new Map(catalogueEnMemoire.articles.map((a) => [a.reference, a]));
    }
    return catalogueEnMemoire;
  }

  function article(reference: string): Article {
    catalogue();
    if (!REFERENCE.test(reference)) {
      throw new ErreurOutil(`référence invalide : ${reference} (format ABC-00000)`);
    }
    const trouve = index.get(reference);
    if (trouve === undefined) {
      throw new ErreurOutil(`référence inconnue du catalogue : ${reference}`);
    }
    return trouve;
  }

  function autoriserLecture(): void {
    if (!DROITS_LECTURE.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`accès refusé aux ventes pour ${personne.nom}`);
    }
  }

  function autoriserSaisie(): void {
    autoriserLecture();
    if (!DROITS_SAISIE.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`${personne.nom} n'a pas le droit de saisir dans les ventes`);
    }
  }

  function cheminFiche(code: string): string {
    if (!CODE_CLIENT.test(code)) {
      throw new ErreurOutil(`code client invalide : ${code} (format c-0000)`);
    }
    const chemin = path.join(etat, "dossiers", "clients", code, "fiche_client.yaml");
    if (!existsSync(chemin)) {
      throw new ErreurOutil(`client inconnu : ${code} (aucune fiche client)`);
    }
    return chemin;
  }

  function fiche(code: string): FicheClientNegoce {
    const chemin = cheminFiche(code);
    const donnees: unknown = parse(readFileSync(chemin, "utf-8"));
    const ecarts = ecartsContrat("fiche_client_negoce", donnees);
    if (ecarts.length > 0) {
      throw new Error(`fiche client hors contrat : ${chemin}\n${ecarts.join("\n")}`);
    }
    return donnees as FicheClientNegoce;
  }

  const commandes = (): Commande[] => lireTous<Commande>(path.join(racine, "commandes"), "commande");
  const livraisons = (): BonDeLivraison[] =>
    lireTous<BonDeLivraison>(path.join(racine, "livraisons"), "bon_de_livraison");
  const retours = (): Retour[] => lireTous<Retour>(path.join(racine, "retours"), "retour");

  function uneCommande(numero: string): Commande {
    if (!NUMERO_COMMANDE.test(numero)) {
      throw new ErreurOutil(`numéro de commande invalide : ${numero} (format CO-0000-00000)`);
    }
    const chemin = path.join(racine, "commandes", `${numero}.json`);
    if (!existsSync(chemin)) {
      throw new ErreurOutil(`commande introuvable : ${numero}`);
    }
    return lireJson<Commande>("commande", chemin);
  }

  function ecrireCommande(commande: Commande): void {
    ecrireJson("commande", path.join(racine, "commandes", `${commande.numero}.json`), commande);
  }

  function uneLivraison(numero: string): BonDeLivraison {
    if (!NUMERO_LIVRAISON.test(numero)) {
      throw new ErreurOutil(`numéro de bon de livraison invalide : ${numero} (format BL-0000-00000)`);
    }
    const trouve = livraisons().find((l) => l.numero === numero);
    if (trouve === undefined) {
      throw new ErreurOutil(`bon de livraison introuvable : ${numero}`);
    }
    return trouve;
  }

  /** Unités réservées par référence : les lignes des commandes validées, pas encore expédiées. */
  function reservations(): Map<string, number> {
    const reservees = new Map<string, number>();
    for (const c of commandes()) {
      if (c.statut === "validee") {
        for (const l of c.lignes) {
          reservees.set(l.reference, (reservees.get(l.reference) ?? 0) + l.quantite);
        }
      }
    }
    return reservees;
  }

  function disponible(reservees: ReadonlyMap<string, number>, reference: string): number {
    return Math.max(0, article(reference).stock_physique - (reservees.get(reference) ?? 0));
  }

  /** Les numéros déjà pris dans un sous-dossier des ventes, lus aux noms des fichiers. */
  function numeros(sousDossier: string): string[] {
    const dossier = path.join(racine, sousDossier);
    return existsSync(dossier)
      ? readdirSync(dossier)
          .filter((nom) => nom.endsWith(".json"))
          .map((nom) => nom.slice(0, -".json".length))
      : [];
  }

  /** L'encours d'un client, en centimes TTC : factures non réglées, avoirs déduits, et commandes non facturées. */
  function encours(code: string): { factures: number; commandes: number; total: number } {
    const racineFacturation = path.join(etat, "facturation");
    const avoirs = lireTous<Avoir>(path.join(racineFacturation, "avoirs"), "avoir");
    const factures = lireTous<FactureClient>(path.join(racineFacturation, "factures"), "facture_client")
      .filter((f) => f.client === code && !f.payee)
      .reduce((somme, f) => {
        const rendu = avoirs
          .filter((a) => a.facture === f.numero)
          .reduce((s, a) => s + centimes(a.montant_ttc_euros), 0);
        return somme + Math.max(0, centimes(f.montant_ttc_euros) - rendu);
      }, 0);
    const enCours = commandes()
      .filter((c) => c.client === code && c.facture === null && STATUTS_ENCOURS.includes(c.statut))
      .reduce((somme, c) => somme + centimes(c.total_ttc_euros), 0);
    return { factures, commandes: enCours, total: factures + enCours };
  }

  function evenement(action: Evenement["action"], detail: string): Evenement {
    return { date: heureSimulee(etat), par: personne.id, action, detail };
  }

  /** Les lignes chiffrées d'une demande ; un prix dérogatoire déjà accordé suit sa référence. */
  function chiffrerLignes(
    client: FicheClientNegoce,
    demandees: readonly { reference: string; quantite: number }[],
    anciennes: readonly LigneCommande[] = [],
  ): LigneCommande[] {
    if (demandees.length === 0) {
      throw new ErreurOutil("une commande a au moins une ligne");
    }
    const vues = new Set<string>();
    return demandees.map(({ reference, quantite }) => {
      const a = article(reference);
      if (vues.has(reference)) {
        throw new ErreurOutil(`référence en double dans la commande : ${reference} (une ligne par référence)`);
      }
      vues.add(reference);
      if (!Number.isInteger(quantite) || quantite < 1) {
        throw new ErreurOutil(`quantité invalide pour ${reference} : ${quantite}`);
      }
      if (quantite % a.conditionnement !== 0) {
        throw new ErreurOutil(
          `${reference} se vend par ${a.conditionnement} : ${quantite} n'est pas un multiple du conditionnement`,
        );
      }
      const accordee = anciennes.find((l) => l.reference === reference && l.prix_derogatoire);
      return ligne(
        catalogue(),
        a,
        client.categorie_remise,
        quantite,
        accordee ? centimes(accordee.prix_net_ht_euros) : null,
      );
    });
  }

  /** La commande avec ses lignes et ses totaux recalculés ; un port imposé remplace celui des conditions. */
  function rechiffree(commande: Commande, lignes: LigneCommande[], portImpose: number | null = null): Commande {
    const [premiere, ...autres] = lignes;
    if (premiere === undefined) {
      throw new ErreurOutil("une commande a au moins une ligne");
    }
    return {
      ...commande,
      lignes: [premiere, ...autres],
      ...totaux(catalogue(), lignes, commande.mode, commande.reliquat_de !== null, portImpose),
    };
  }

  function adresseDeLaFiche(client: FicheClientNegoce, code: string): { code: string; adresse: string } {
    const trouvee = client.adresses_livraison.find((a) => a.code === code);
    if (trouvee === undefined) {
      const codes = client.adresses_livraison.map((a) => a.code).join(", ");
      throw new ErreurOutil(`adresse ${code} absente de la fiche de ${client.code} (adresses : ${codes})`);
    }
    return { code: trouvee.code, adresse: trouvee.adresse };
  }

  function texteCommande(c: Commande): string {
    const lignes = c.lignes.map((l) => {
      const remise = l.prix_derogatoire ? "prix accordé" : `remise ${pourcent(l.remise_pourcent)}`;
      return `${l.reference} | ${l.libelle} | ${l.quantite} × ${euros(l.prix_net_ht_euros)} HT (tarif ${euros(l.prix_tarif_ht_euros)}, ${remise}) | ${euros(l.montant_ht_euros)} HT`;
    });
    const livraison = c.livraison.code === null ? "adresse ponctuelle" : `adresse ${c.livraison.code} de la fiche`;
    const morceaux = [
      `Commande ${c.numero} | client ${c.client} | ${STATUT_EN_CLAIR[c.statut]}`,
      `Créée le ${c.cree_le.slice(0, 10)} par ${c.cree_par}${c.reference_client === null ? "" : ` ; référence du client : ${c.reference_client}`}`,
      `Mode : ${c.mode} ; livraison : ${livraison}, ${c.livraison.adresse}`,
      ...(c.motif_attente === null ? [] : [`En attente : ${c.motif_attente}`]),
      ...(c.reliquat_de === null ? [] : [`Reliquat de la commande ${c.reliquat_de}`]),
      "Lignes :",
      ...lignes,
      `Port : ${euros(c.port_ht_euros)} HT`,
      `Total : ${euros(c.total_ht_euros)} HT, TVA ${euros(c.total_tva_euros)}, ${euros(c.total_ttc_euros)} TTC`,
      `Livraisons : ${c.livraisons.length > 0 ? c.livraisons.join(", ") : "aucune"} ; facture : ${c.facture ?? "aucune"}`,
      "Historique :",
      ...c.historique.map((e) => `${e.date} | ${e.par} | ${e.action}${e.detail === "" ? "" : ` | ${e.detail}`}`),
    ];
    return morceaux.join("\n");
  }

  const serveur = new McpServer({ name: "pme-ventes", version: "0.1.0" });

  serveur.registerTool(
    "chercher_articles",
    {
      title: "Chercher des articles",
      annotations: { readOnlyHint: true },
      description: `Cherche dans le catalogue les articles dont la référence ou le libellé contient un texte ; au plus ${NOMBRE_ARTICLES_TROUVES} réponses.`,
      inputSchema: { texte: z.string().describe("par exemple « vis à bois 5x50 » ou une référence") },
    },
    ({ texte }) =>
      avecRefus(() => {
        autoriserLecture();
        const cherche = sansAccents(texte.trim());
        if (cherche === "") {
          throw new ErreurOutil("texte de recherche vide");
        }
        const mots = cherche.split(/\s+/u);
        const reservees = reservations();
        const trouves = catalogue().articles.filter((a) => {
          const contenu = sansAccents(`${a.reference} ${a.libelle}`);
          return mots.every((mot) => contenu.includes(mot));
        });
        const montres = trouves
          .slice(0, NOMBRE_ARTICLES_TROUVES)
          .map(
            (a) =>
              `${a.reference} | ${a.libelle} | ${a.unite} | ${euros(a.prix_vente_ht_euros)} HT | disponible ${disponible(reservees, a.reference)} | ${STATUT_ARTICLE_EN_CLAIR[a.statut]}`,
          );
        const entete =
          trouves.length > NOMBRE_ARTICLES_TROUVES
            ? `${trouves.length} articles, les ${NOMBRE_ARTICLES_TROUVES} premiers :`
            : `${trouves.length} article(s) :`;
        return trouves.length === 0 ? "(aucun article)" : [entete, ...montres].join("\n");
      }),
  );

  serveur.registerTool(
    "consulter_article",
    {
      title: "Consulter un article",
      annotations: { readOnlyHint: true },
      description:
        "Renvoie la fiche d'un article : famille, conditionnement, prix de vente, barème par quantité, prix d'achat, stock, réassort, statut et substituts.",
      inputSchema: { reference: z.string().describe("référence du catalogue, par exemple VIS-01482") },
    },
    ({ reference }) =>
      avecRefus(() => {
        autoriserLecture();
        const a = article(reference);
        const reservees = reservations().get(reference) ?? 0;
        const bareme =
          a.bareme_quantite.length === 0
            ? "aucun"
            : a.bareme_quantite.map((p) => `dès ${p.a_partir_de} : ${pourcent(p.remise_pourcent)}`).join(" ; ");
        const reassort =
          a.reassort === null ? "aucun" : `${a.reassort.quantite} unités attendues le ${a.reassort.date_prevue}`;
        return [
          `${a.reference} | ${a.libelle}`,
          `Famille : ${a.famille} ; unité : ${a.unite} ; vendu par ${a.conditionnement}`,
          `Prix de vente : ${euros(a.prix_vente_ht_euros)} HT${a.prix_net ? ", prix net, sans remise" : ""} ; TVA ${pourcent(a.taux_tva)}`,
          `Barème par quantité : ${bareme}`,
          `Achat : fournisseur ${a.achat.fournisseur} ; dernier prix net facturé ${euros(a.achat.prix_net_facture_ht_euros)} HT ; autres avantages financiers ${pourcent(a.achat.avantages_financiers_pourcent)} ; transport ${euros(a.achat.transport_unitaire_ht_euros)} HT par unité`,
          `Stock : ${a.stock_physique} en rayon, ${reservees} réservées, ${Math.max(0, a.stock_physique - reservees)} disponibles ; point de commande ${a.point_de_commande}, réassort par ${a.quantite_reassort}`,
          `Réassort commandé : ${reassort}`,
          `Statut : ${STATUT_ARTICLE_EN_CLAIR[a.statut]}`,
          `Substituts : ${a.substituts.length > 0 ? a.substituts.join(", ") : "aucun"}`,
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "consulter_client",
    {
      title: "Consulter un client",
      annotations: { readOnlyHint: true },
      description:
        "Renvoie les conditions d'un client, ses contacts et ses adresses de livraison déclarés, son statut et son encours.",
      inputSchema: { client: z.string().describe("code du client, par exemple c-0142") },
    },
    ({ client: code }) =>
      avecRefus(() => {
        autoriserLecture();
        const f = fiche(code);
        const e = encours(code);
        const limite = centimes(f.limite_encours_euros);
        const remise = catalogue().conditions.remises_categories[f.categorie_remise];
        return [
          `Client ${f.code} : ${f.nom} (${f.type}), secteur ${f.secteur}`,
          `Siège : ${f.adresse} ; téléphone : ${f.telephone}`,
          `Commercial : ${f.commercial} ; administration des ventes : ${f.administration_des_ventes}`,
          `Contacts déclarés : ${f.contacts.map((c) => `${c.nom} (${c.fonction}) <${c.courriel}>`).join(" ; ")}`,
          `Adresses de livraison : ${f.adresses_livraison.map((a) => `${a.code} ${a.libelle} : ${a.adresse}`).join(" ; ")}`,
          `Catégorie de remise : ${f.categorie_remise} (${pourcent(remise)}) ; délai de paiement : ${DELAI_EN_CLAIR[f.delai_paiement]} ; client depuis le ${f.client_depuis}`,
          `Livraisons partielles : ${f.livraisons_partielles ? "acceptées" : "non"} ; substitution : ${f.substitution_acceptee ? "acceptée" : "non"}`,
          `Statut : ${f.statut === "bloque" ? `bloqué (${f.motif_blocage ?? "?"})` : "ouvert"}`,
          `Encours : ${euros(enEuros(e.total))} TTC (factures non réglées ${euros(enEuros(e.factures))}, commandes non facturées ${euros(enEuros(e.commandes))}) ; limite ${euros(f.limite_encours_euros)} ; reste ${euros(enEuros(limite - e.total))}`,
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "lister_commandes",
    {
      title: "Lister des commandes",
      annotations: { readOnlyHint: true },
      description: `Liste les commandes d'un client, ou celles d'un statut ; au plus les ${NOMBRE_COMMANDES_LISTEES} plus récentes.`,
      inputSchema: {
        client: z.string().optional().describe("code du client, par exemple c-0142"),
        statut: z
          .enum([
            "brouillon",
            "en_attente_deblocage",
            "en_attente_reassort",
            "validee",
            "expediee",
            "livree",
            "facturee",
            "annulee",
          ])
          .optional(),
      },
    },
    ({ client: code, statut }) =>
      avecRefus(() => {
        autoriserLecture();
        if (code === undefined && statut === undefined) {
          throw new ErreurOutil("donner un client, un statut, ou les deux");
        }
        if (code !== undefined) {
          cheminFiche(code);
        }
        const trouvees = commandes().filter(
          (c) => (code === undefined || c.client === code) && (statut === undefined || c.statut === statut),
        );
        const montrees = trouvees
          .slice(-NOMBRE_COMMANDES_LISTEES)
          .map(
            (c) =>
              `${c.numero} | ${c.client} | ${c.cree_le.slice(0, 10)} | ${STATUT_EN_CLAIR[c.statut]} | ${c.lignes.length} ligne(s) | ${euros(c.total_ttc_euros)} TTC`,
          );
        if (montrees.length === 0) {
          return "(aucune commande)";
        }
        const entete =
          trouvees.length > NOMBRE_COMMANDES_LISTEES
            ? `${trouvees.length} commandes, les ${NOMBRE_COMMANDES_LISTEES} plus récentes :`
            : `${trouvees.length} commande(s) :`;
        return [entete, ...montrees].join("\n");
      }),
  );

  serveur.registerTool(
    "consulter_commande",
    {
      title: "Consulter une commande",
      annotations: { readOnlyHint: true },
      description:
        "Renvoie une commande : lignes, prix nets et remises, adresse, mode, totaux, statut, livraisons, facture et historique.",
      inputSchema: { numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873") },
    },
    ({ numero }) =>
      avecRefus(() => {
        autoriserLecture();
        return texteCommande(uneCommande(numero));
      }),
  );

  serveur.registerTool(
    "consulter_livraison",
    {
      title: "Consulter un bon de livraison",
      annotations: { readOnlyHint: true },
      description:
        "Renvoie un bon de livraison : dates, flotte ou transporteur, colis, lignes livrées, réserves portées à la livraison, signataire.",
      inputSchema: { numero: z.string().describe("numéro du bon, par exemple BL-2026-01544") },
    },
    ({ numero }) =>
      avecRefus(() => {
        autoriserLecture();
        const l = uneLivraison(numero);
        const transport =
          l.transport.mode === "flotte"
            ? "camionnette de la PME"
            : `transporteur ${l.transport.transporteur ?? "?"}, récépissé ${l.transport.recepisse ?? "?"}`;
        const statut = { en_cours: "en cours", livre: "livré", refuse: "refusé" }[l.statut];
        return [
          `Bon de livraison ${l.numero} | commande ${l.commande} | client ${l.client} | ${statut}`,
          `Expédié le ${l.date_expedition} ; livré le ${l.date_livraison ?? "?"} ; ${transport} ; ${l.colis} colis`,
          `Adresse : ${l.adresse}`,
          "Lignes livrées :",
          ...l.lignes.map((x) => `${x.reference} | ${x.libelle} | ${x.quantite}`),
          `Réserves : ${l.reserves ?? "aucune"}`,
          `Signataire : ${l.signataire ?? "?"}`,
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "creer_commande",
    {
      title: "Créer une commande",
      annotations: { readOnlyHint: false },
      description:
        "Crée une commande en brouillon, chiffrée au tarif avec la remise de la catégorie du client et le barème par quantité, livrée à une adresse de la fiche du client.",
      inputSchema: {
        client: z.string().describe("code du client, par exemple c-0142"),
        lignes: z.array(ligneDemandee).describe("une ligne par référence"),
        livraison: z.string().describe("code d'une adresse de livraison de la fiche, par exemple L1"),
        mode: z.enum(["standard", "express"]).optional().describe("standard par défaut"),
        reference_client: z.string().optional().describe("référence du bon de commande du client"),
      },
    },
    ({ client: code, lignes, livraison, mode, reference_client }) =>
      avecRefus(() => {
        autoriserSaisie();
        const f = fiche(code);
        const adresse = adresseDeLaFiche(f, livraison);
        const chiffrees = chiffrerLignes(f, lignes);
        const date = heureSimulee(etat);
        const numero = numeroSuivant("CO", date.slice(0, 4), 5, numeros("commandes"));
        const brouillon: Commande = rechiffree(
          {
            numero,
            client: code,
            reference_client: reference_client?.trim() || null,
            cree_le: date,
            cree_par: personne.id,
            mode: mode ?? "standard",
            livraison: adresse,
            lignes: [chiffrees[0] as LigneCommande],
            port_ht_euros: 0,
            total_ht_euros: 0,
            total_tva_euros: 0,
            total_ttc_euros: 0,
            statut: "brouillon",
            motif_attente: null,
            reliquat_de: null,
            livraisons: [],
            facture: null,
            historique: [evenement("creee", "")],
          },
          chiffrees,
        );
        ecrireCommande(brouillon);
        const reservees = reservations();
        const dispo = brouillon.lignes.map((l) => `${l.reference} : ${disponible(reservees, l.reference)} disponibles`);
        return `${texteCommande(brouillon)}\nStock : ${dispo.join(" ; ")}`;
      }),
  );

  serveur.registerTool(
    "modifier_commande",
    {
      title: "Modifier une commande",
      annotations: { readOnlyHint: false },
      description:
        "Modifie les lignes, l'adresse de livraison de la fiche ou le mode d'une commande en brouillon, ou en attente de déblocage, qui revient alors en brouillon.",
      inputSchema: {
        numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873"),
        lignes: z.array(ligneDemandee).optional().describe("les nouvelles lignes, qui remplacent les anciennes"),
        livraison: z.string().optional().describe("code d'une adresse de livraison de la fiche, par exemple L2"),
        mode: z.enum(["standard", "express"]).optional(),
      },
    },
    ({ numero, lignes, livraison, mode }) =>
      avecRefus(() => {
        autoriserSaisie();
        const c = uneCommande(numero);
        if (c.statut !== "brouillon" && c.statut !== "en_attente_deblocage") {
          throw new ErreurOutil(`commande ${numero} ${STATUT_EN_CLAIR[c.statut]} : seul un brouillon se modifie`);
        }
        if (lignes === undefined && livraison === undefined && mode === undefined) {
          throw new ErreurOutil("rien à modifier");
        }
        const f = fiche(c.client);
        const changes: string[] = [];
        let modifiee: Commande = { ...c, statut: "brouillon", motif_attente: null };
        if (livraison !== undefined) {
          modifiee = { ...modifiee, livraison: adresseDeLaFiche(f, livraison) };
          changes.push(`livraison ${livraison}`);
        }
        if (mode !== undefined) {
          modifiee = { ...modifiee, mode };
          changes.push(`mode ${mode}`);
        }
        const nouvelles = lignes === undefined ? [...c.lignes] : chiffrerLignes(f, lignes, c.lignes);
        if (lignes !== undefined) {
          changes.push("lignes");
        }
        modifiee = rechiffree(
          { ...modifiee, historique: [...c.historique, evenement("modifiee", changes.join(", "))] },
          nouvelles,
        );
        ecrireCommande(modifiee);
        return texteCommande(modifiee);
      }),
  );

  serveur.registerTool(
    "valider_commande",
    {
      title: "Valider une commande",
      annotations: { readOnlyHint: false },
      description:
        "Valide une commande en brouillon et réserve son stock. Sans stock suffisant, refuse, sauf livraison partielle demandée : la commande garde le disponible et un reliquat attend le réassort. Un client bloqué ou un encours dépassé met la commande en attente de déblocage.",
      inputSchema: {
        numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873"),
        livraison_partielle: z
          .boolean()
          .optional()
          .describe("vrai pour livrer le disponible et mettre le reste en reliquat ; faux par défaut"),
      },
    },
    ({ numero, livraison_partielle }) =>
      avecRefus(() => {
        autoriserSaisie();
        let c = uneCommande(numero);
        if (c.statut !== "brouillon" && c.statut !== "en_attente_reassort") {
          throw new ErreurOutil(
            `commande ${numero} ${STATUT_EN_CLAIR[c.statut]} : seul un brouillon ou un reliquat se valide`,
          );
        }
        const f = fiche(c.client);
        const messages: string[] = [];
        if (f.statut === "bloque") {
          c = {
            ...c,
            statut: "en_attente_deblocage",
            motif_attente: `client bloqué : ${f.motif_blocage ?? "?"}`,
            historique: [...c.historique, evenement("mise_en_attente", "client bloqué")],
          };
          ecrireCommande(c);
          return `Commande ${numero} en attente de déblocage : le client ${f.code} est bloqué (${f.motif_blocage ?? "?"}).`;
        }
        const reservees = reservations();
        const manques = c.lignes
          .map((l) => ({ l, dispo: disponible(reservees, l.reference) }))
          .filter(({ l, dispo }) => l.quantite > dispo);
        if (manques.length > 0) {
          const detail = manques.map(({ l, dispo }) => `${l.reference} demandé ${l.quantite}, disponible ${dispo}`);
          if (livraison_partielle !== true) {
            throw new ErreurOutil(`stock insuffisant, rien n'est validé : ${detail.join(" ; ")}`);
          }
          const gardees: LigneCommande[] = [];
          const restes: LigneCommande[] = [];
          for (const l of c.lignes) {
            const a = article(l.reference);
            const livrable = Math.min(
              l.quantite,
              Math.floor(disponible(reservees, l.reference) / a.conditionnement) * a.conditionnement,
            );
            const prixAccorde = l.prix_derogatoire ? centimes(l.prix_net_ht_euros) : null;
            if (livrable > 0) {
              gardees.push(ligne(catalogue(), a, f.categorie_remise, livrable, prixAccorde));
            }
            if (l.quantite - livrable > 0) {
              restes.push(ligne(catalogue(), a, f.categorie_remise, l.quantite - livrable, prixAccorde));
            }
          }
          if (gardees.length === 0) {
            throw new ErreurOutil(`aucun article disponible, rien n'est validé : ${detail.join(" ; ")}`);
          }
          const reliquatNumero = numeroSuivant("CO", heureSimulee(etat).slice(0, 4), 5, numeros("commandes"));
          const reliquat = rechiffree(
            {
              ...c,
              numero: reliquatNumero,
              cree_le: heureSimulee(etat),
              cree_par: personne.id,
              statut: "en_attente_reassort",
              motif_attente: null,
              reliquat_de: c.numero,
              livraisons: [],
              facture: null,
              historique: [evenement("creee", `reliquat de ${c.numero}`)],
            },
            restes,
          );
          ecrireCommande(reliquat);
          // La partie livrée garde le port de la commande entière : le franco ne se perd pas sur
          // une rupture de la PME.
          c = rechiffree(
            { ...c, historique: [...c.historique, evenement("scindee", `reliquat ${reliquatNumero}`)] },
            gardees,
            centimes(c.port_ht_euros),
          );
          messages.push(
            `Livraison partielle : le reliquat ${reliquatNumero} attend le réassort (${detail.join(" ; ")}).`,
          );
        }
        const e = encours(c.client);
        const limite = centimes(f.limite_encours_euros);
        if (e.total + centimes(c.total_ttc_euros) > limite) {
          const motif = `encours ${euros(enEuros(e.total))} et commande ${euros(c.total_ttc_euros)} TTC pour une limite de ${euros(f.limite_encours_euros)}`;
          c = {
            ...c,
            statut: "en_attente_deblocage",
            motif_attente: `encours dépassé : ${motif}`,
            historique: [...c.historique, evenement("mise_en_attente", "encours dépassé")],
          };
          ecrireCommande(c);
          return [...messages, `Commande ${numero} en attente de déblocage : ${motif}.`].join("\n");
        }
        c = {
          ...c,
          statut: "validee",
          motif_attente: null,
          historique: [...c.historique, evenement("validee", "")],
        };
        ecrireCommande(c);
        return [...messages, `Commande ${numero} validée : ${euros(c.total_ttc_euros)} TTC, stock réservé.`].join("\n");
      }),
  );

  serveur.registerTool(
    "debloquer_commande",
    {
      title: "Débloquer une commande",
      annotations: { readOnlyHint: false },
      description: "Valide une commande en attente de déblocage et réserve son stock.",
      inputSchema: {
        numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873"),
        motif: z.string().describe("raison du déblocage"),
      },
    },
    ({ numero, motif }) =>
      avecRefus(() => {
        autoriserSaisie();
        const c = uneCommande(numero);
        if (c.statut !== "en_attente_deblocage") {
          throw new ErreurOutil(`commande ${numero} ${STATUT_EN_CLAIR[c.statut]} : rien à débloquer`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif du déblocage est obligatoire");
        }
        const reservees = reservations();
        const manques = c.lignes
          .map((l) => ({ l, dispo: disponible(reservees, l.reference) }))
          .filter(({ l, dispo }) => l.quantite > dispo);
        if (manques.length > 0) {
          const detail = manques.map(({ l, dispo }) => `${l.reference} demandé ${l.quantite}, disponible ${dispo}`);
          throw new ErreurOutil(`stock insuffisant, rien n'est débloqué : ${detail.join(" ; ")}`);
        }
        const debloquee: Commande = {
          ...c,
          statut: "validee",
          motif_attente: null,
          historique: [...c.historique, evenement("debloquee", motif.trim())],
        };
        ecrireCommande(debloquee);
        return `Commande ${numero} débloquée et validée : ${euros(debloquee.total_ttc_euros)} TTC, stock réservé.`;
      }),
  );

  serveur.registerTool(
    "accorder_prix",
    {
      title: "Accorder un prix",
      annotations: { readOnlyHint: false },
      description: "Fixe un prix net dérogatoire, hors taxes, sur une ligne d'une commande en brouillon.",
      inputSchema: {
        numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873"),
        reference: z.string().describe("référence de la ligne, par exemple VIS-01482"),
        prix_net_ht_euros: z.number().describe("prix unitaire net hors taxes, en euros, au centime"),
        motif: z.string().describe("raison du prix, et qui l'accorde"),
      },
    },
    ({ numero, reference, prix_net_ht_euros, motif }) =>
      avecRefus(() => {
        autoriserSaisie();
        const c = uneCommande(numero);
        if (c.statut !== "brouillon") {
          throw new ErreurOutil(
            `commande ${numero} ${STATUT_EN_CLAIR[c.statut]} : un prix ne s'accorde que sur un brouillon`,
          );
        }
        const visee = c.lignes.find((l) => l.reference === reference);
        if (visee === undefined) {
          throw new ErreurOutil(`la commande ${numero} n'a pas de ligne ${reference}`);
        }
        if (
          !(prix_net_ht_euros > 0) ||
          Math.abs(prix_net_ht_euros * 100 - Math.round(prix_net_ht_euros * 100)) > 1e-6
        ) {
          throw new ErreurOutil(`prix invalide : ${prix_net_ht_euros} (en euros, au centime, positif)`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif du prix est obligatoire");
        }
        const f = fiche(c.client);
        const lignes = c.lignes.map((l) =>
          l.reference === reference
            ? ligne(catalogue(), article(reference), f.categorie_remise, l.quantite, centimes(prix_net_ht_euros))
            : l,
        );
        const accordee = rechiffree(
          {
            ...c,
            historique: [
              ...c.historique,
              evenement("prix_accorde", `${reference} à ${euros(prix_net_ht_euros)} HT : ${motif.trim()}`),
            ],
          },
          lignes,
        );
        ecrireCommande(accordee);
        return texteCommande(accordee);
      }),
  );

  serveur.registerTool(
    "livrer_a_une_adresse_ponctuelle",
    {
      title: "Livrer à une adresse ponctuelle",
      annotations: { readOnlyHint: false },
      description:
        "Fait livrer une commande à une adresse qui n'est pas dans la fiche du client, un chantier par exemple.",
      inputSchema: {
        numero: z.string().describe("numéro de la commande, par exemple CO-2026-01873"),
        adresse: z.string().describe("l'adresse complète de livraison"),
        motif: z.string().describe("raison, et qui l'a demandée"),
      },
    },
    ({ numero, adresse, motif }) =>
      avecRefus(() => {
        autoriserSaisie();
        const c = uneCommande(numero);
        const modifiables: readonly Commande["statut"][] = [
          "brouillon",
          "en_attente_deblocage",
          "en_attente_reassort",
          "validee",
        ];
        if (!modifiables.includes(c.statut)) {
          throw new ErreurOutil(`commande ${numero} ${STATUT_EN_CLAIR[c.statut]} : son adresse ne change plus`);
        }
        if (adresse.trim() === "" || motif.trim() === "") {
          throw new ErreurOutil("l'adresse et le motif sont obligatoires");
        }
        const changee: Commande = {
          ...c,
          livraison: { code: null, adresse: adresse.trim() },
          historique: [...c.historique, evenement("adresse_ponctuelle", `${adresse.trim()} : ${motif.trim()}`)],
        };
        ecrireCommande(changee);
        return `Commande ${numero} : livraison à l'adresse ponctuelle ${adresse.trim()}.`;
      }),
  );

  serveur.registerTool(
    "enregistrer_retour",
    {
      title: "Enregistrer un retour",
      annotations: { readOnlyHint: false },
      description:
        "Enregistre des articles revenus d'une livraison : les revendables reviennent en stock, les autres vont au rebut. L'avoir se fait au service de facturation.",
      inputSchema: {
        livraison: z.string().describe("numéro du bon de livraison, par exemple BL-2026-01544"),
        lignes: z
          .array(
            z.object({
              reference: z.string(),
              quantite: z.number().int(),
              etat: z.enum(["revendable", "rebut"]),
            }),
          )
          .describe("les articles revenus"),
        motif: z.string().describe("raison du retour"),
      },
    },
    ({ livraison, lignes, motif }) =>
      avecRefus(() => {
        autoriserSaisie();
        const bl = uneLivraison(livraison);
        if (bl.statut === "en_cours") {
          throw new ErreurOutil(`la livraison ${livraison} est en cours : rien n'en revient encore`);
        }
        if (lignes.length === 0 || motif.trim() === "") {
          throw new ErreurOutil("au moins une ligne, et le motif du retour");
        }
        const deja = retours().filter((r) => r.livraison === livraison);
        for (const l of lignes) {
          const livree = bl.lignes.find((x) => x.reference === l.reference);
          if (livree === undefined) {
            throw new ErreurOutil(`${l.reference} n'est pas sur la livraison ${livraison}`);
          }
          const revenues =
            deja
              .flatMap((r) => r.lignes)
              .filter((x) => x.reference === l.reference)
              .reduce((s, x) => s + x.quantite, 0) +
            lignes.filter((x) => x.reference === l.reference).reduce((s, x) => s + x.quantite, 0);
          if (l.quantite < 1 || revenues > livree.quantite) {
            throw new ErreurOutil(
              `${l.reference} : ${livree.quantite} livrées, ${revenues} reviendraient en tout ; rien n'est enregistré`,
            );
          }
        }
        const date = heureSimulee(etat);
        const numero = numeroSuivant("RT", date.slice(0, 4), 4, numeros("retours"));
        const [premiere, ...autres] = lignes;
        if (premiere === undefined) {
          throw new ErreurOutil("au moins une ligne");
        }
        const retour: Retour = {
          numero,
          livraison,
          client: bl.client,
          date,
          lignes: [premiere, ...autres],
          motif: motif.trim(),
          enregistre_par: personne.id,
        };
        ecrireJson("retour", path.join(racine, "retours", `${numero}.json`), retour);
        const revendables = lignes.filter((l) => l.etat === "revendable");
        if (revendables.length > 0) {
          const courant = catalogue();
          const misAJour: Catalogue = {
            ...courant,
            articles: courant.articles.map((a) => {
              const remis = revendables.filter((l) => l.reference === a.reference).reduce((s, l) => s + l.quantite, 0);
              return remis === 0 ? a : { ...a, stock_physique: a.stock_physique + remis };
            }) as Catalogue["articles"],
          };
          ecrireJson("catalogue", cheminCatalogue, misAJour);
          catalogueEnMemoire = misAJour;
          index = new Map(misAJour.articles.map((a) => [a.reference, a]));
        }
        const detail = lignes.map((l) => `${l.reference} × ${l.quantite} (${l.etat})`).join(", ");
        return `Retour ${numero} enregistré sur ${livraison} : ${detail}.`;
      }),
  );

  serveur.registerTool(
    "bloquer_client",
    {
      title: "Bloquer un client",
      annotations: { readOnlyHint: false },
      description: "Met un client en statut bloqué : aucune de ses commandes ne se valide plus sans déblocage.",
      inputSchema: {
        client: z.string().describe("code du client, par exemple c-0142"),
        motif: z.string().describe("raison du blocage"),
      },
    },
    ({ client: code, motif }) =>
      avecRefus(() => {
        autoriserSaisie();
        const f = fiche(code);
        if (f.statut === "bloque") {
          throw new ErreurOutil(`le client ${code} est déjà bloqué (${f.motif_blocage ?? "?"})`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif du blocage est obligatoire");
        }
        const chemin = cheminFiche(code);
        const texte = readFileSync(chemin, "utf-8");
        if (!/^statut: .*$/mu.test(texte) || !/^motif_blocage: .*$/mu.test(texte)) {
          throw new Error(`fiche sans lignes statut et motif_blocage : ${chemin}`);
        }
        writeFileSync(
          chemin,
          texte
            .replace(/^statut: .*$/mu, 'statut: "bloque"')
            .replace(/^motif_blocage: .*$/mu, `motif_blocage: ${JSON.stringify(motif.trim())}`),
        );
        fiche(code);
        return `Client ${code} bloqué : ${motif.trim()}.`;
      }),
  );

  return serveur;
}
