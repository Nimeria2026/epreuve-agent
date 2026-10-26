import type { Article, Catalogue } from "@poa/commun/contrats/catalogue";
import type { Commande, LigneCommande } from "@poa/commun/contrats/commande";

/**
 * Le chiffrage d'une commande, en centimes entiers : aucun calcul ne passe par un flottant
 * arrondi au hasard. Chaque arrondi se fait au plus proche, la moitié vers le haut, comme dans le
 * service de facturation.
 */

/** Centimes d'un montant en euros donné au centime. */
export function centimes(euros: number): number {
  return Math.round(euros * 100);
}

/** Euros d'un montant en centimes. */
export function enEuros(centimesEntiers: number): number {
  return centimesEntiers / 100;
}

/** Un taux en pour cent, en centièmes de point entiers : 4 % vaut 400, 5,5 % vaut 550. */
function pointsDeBase(pourcent: number): number {
  return Math.round(pourcent * 100);
}

/** La remise du barème par quantité atteinte par une ligne, 0 sans palier atteint. */
export function remiseQuantite(article: Article, quantite: number): number {
  let remise = 0;
  for (const palier of article.bareme_quantite) {
    if (quantite >= palier.a_partir_de && palier.remise_pourcent > remise) {
      remise = palier.remise_pourcent;
    }
  }
  return remise;
}

/**
 * Prix unitaire net d'un article pour une catégorie de client et une quantité : le prix du tarif,
 * diminué de la remise de la catégorie, puis du barème par quantité ; arrondi au centime. Un
 * article « prix net » ne prend aucune remise.
 */
export function prixNet(
  catalogue: Catalogue,
  article: Article,
  categorie: "A" | "B" | "C",
  quantite: number,
): { prixCentimes: number; remisePourcent: number } {
  const tarif = centimes(article.prix_vente_ht_euros);
  if (article.prix_net) {
    return { prixCentimes: tarif, remisePourcent: 0 };
  }
  const a = 10_000 - pointsDeBase(catalogue.conditions.remises_categories[categorie]);
  const b = 10_000 - pointsDeBase(remiseQuantite(article, quantite));
  const prixCentimes = Math.floor((tarif * a * b + 50_000_000) / 100_000_000);
  // Remise composée, en pour cent, au centième : 4 % puis 3 % font 6,88 %.
  const remisePourcent = (100_000_000 - a * b) / 1_000_000;
  return { prixCentimes, remisePourcent: Math.round(remisePourcent * 100) / 100 };
}

/** Une ligne chiffrée, au prix calculé ou à un prix dérogatoire accordé. */
export function ligne(
  catalogue: Catalogue,
  article: Article,
  categorie: "A" | "B" | "C",
  quantite: number,
  derogatoireCentimes: number | null,
): LigneCommande {
  const calcule = prixNet(catalogue, article, categorie, quantite);
  const prix = derogatoireCentimes ?? calcule.prixCentimes;
  return {
    reference: article.reference,
    libelle: article.libelle,
    quantite,
    prix_tarif_ht_euros: article.prix_vente_ht_euros,
    remise_pourcent: derogatoireCentimes === null ? calcule.remisePourcent : 0,
    prix_net_ht_euros: enEuros(prix),
    prix_derogatoire: derogatoireCentimes !== null,
    taux_tva: article.taux_tva,
    montant_ht_euros: enEuros(prix * quantite),
  };
}

/** TVA d'une base en centimes à un taux en pour cent, arrondie au centime, la moitié vers le haut. */
function tva(baseCentimes: number, taux: number): number {
  return Math.floor((baseCentimes * Math.round(taux * 10) + 500) / 1000);
}

export interface Totaux {
  readonly port_ht_euros: number;
  readonly total_ht_euros: number;
  readonly total_tva_euros: number;
  readonly total_ttc_euros: number;
}

/**
 * Le port et les totaux d'une commande. Express : le forfait. Standard : rien à partir du franco,
 * le port standard en dessous. Un reliquat part sans port, celui de sa commande étant déjà
 * compté ; un port imposé, en centimes, remplace ces règles. La TVA se calcule par taux, sur la
 * somme des lignes de ce taux, port compris au sien.
 */
export function totaux(
  catalogue: Catalogue,
  lignes: readonly LigneCommande[],
  mode: Commande["mode"],
  reliquat: boolean,
  portImpose: number | null = null,
): Totaux {
  const conditions = catalogue.conditions;
  const lignesCentimes = lignes.reduce((somme, l) => somme + centimes(l.montant_ht_euros), 0);
  let port = 0;
  if (portImpose !== null) {
    port = portImpose;
  } else if (!reliquat) {
    if (mode === "express") {
      port = centimes(conditions.forfait_express_ht_euros);
    } else if (lignesCentimes < centimes(conditions.franco_a_partir_de_ht_euros)) {
      port = centimes(conditions.port_standard_ht_euros);
    }
  }
  const bases = new Map<number, number>();
  for (const l of lignes) {
    bases.set(l.taux_tva, (bases.get(l.taux_tva) ?? 0) + centimes(l.montant_ht_euros));
  }
  if (port > 0) {
    bases.set(conditions.taux_tva_port, (bases.get(conditions.taux_tva_port) ?? 0) + port);
  }
  const totalTva = [...bases.entries()].reduce((somme, [taux, base]) => somme + tva(base, taux), 0);
  const totalHt = lignesCentimes + port;
  return {
    port_ht_euros: enEuros(port),
    total_ht_euros: enEuros(totalHt),
    total_tva_euros: enEuros(totalTva),
    total_ttc_euros: enEuros(totalHt + totalTva),
  };
}
