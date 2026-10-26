import type { Devis } from "@poa/commun/contrats/devis";
import type { Tarif } from "@poa/commun/contrats/tarif";
import { ErreurOutil } from "@poa/commun/erreurs";

/**
 * Le chiffrage d'un devis, en centimes entiers pour qu'aucun arrondi ne dépende des flottants.
 * Chaque ligne : quantité fois prix du tarif, arrondi au centime ; la remise s'applique à chaque
 * ligne, arrondie au centime ; la TVA se calcule par taux, sur la somme des lignes de ce taux,
 * arrondie au centime. Un arrondi va au plus proche, la moitié vers le haut. Même calcul dans
 * 09_outillage/scripts/generer_donnees_v3.py, pour les devis de l'état initial.
 */

export const TAUX_TVA = [5.5, 10, 20] as const;

/** Une ligne demandée par la personne qui chiffre : un code du tarif, une quantité, un taux. */
export interface LigneDemandee {
  readonly code: string;
  readonly quantite: number;
  readonly taux_tva: number;
}

type LigneDevis = Devis["lignes"][number];

export interface Chiffrage {
  readonly lignes: [LigneDevis, ...LigneDevis[]];
  readonly total_ht_euros: number;
  readonly total_tva_euros: number;
  readonly total_ttc_euros: number;
}

/** n / d arrondi au plus proche, la moitié vers le haut (entiers positifs). */
function diviserArrondi(n: number, d: number): number {
  return Math.floor((2 * n + d) / (2 * d));
}

/** Une valeur positive au centième près, en centièmes. */
function enCentiemes(valeur: number, quoi: string): number {
  const centiemes = Math.round(valeur * 100);
  if (!(valeur > 0) || Math.abs(valeur * 100 - centiemes) > 1e-6) {
    throw new ErreurOutil(`${quoi} invalide : ${valeur} (positive, au centième près)`);
  }
  return centiemes;
}

function estTaux(taux: number): taux is (typeof TAUX_TVA)[number] {
  return (TAUX_TVA as readonly number[]).includes(taux);
}

export function chiffrer(tarif: Tarif, demandees: readonly LigneDemandee[], remisePourcent: number): Chiffrage {
  if (
    !(remisePourcent >= 0 && remisePourcent < 100) ||
    Math.abs(remisePourcent * 100 - Math.round(remisePourcent * 100)) > 1e-6
  ) {
    throw new ErreurOutil(`remise invalide : ${remisePourcent} (en pour cent, de 0 à moins de 100, au centième)`);
  }
  const remise = Math.round(remisePourcent * 100);
  const basesParTaux = new Map<number, number>();
  const lignes = demandees.map((demandee): LigneDevis => {
    const article = tarif.lignes.find((l) => l.code === demandee.code);
    if (article === undefined) {
      throw new ErreurOutil(`code absent du tarif : ${demandee.code} (consulter_tarif)`);
    }
    if (!estTaux(demandee.taux_tva)) {
      throw new ErreurOutil(`taux de TVA invalide : ${demandee.taux_tva} (5.5, 10 ou 20)`);
    }
    const quantite = enCentiemes(demandee.quantite, "quantité");
    const prix = Math.round(article.prix_ht_euros * 100);
    const montant = diviserArrondi(quantite * prix, 100);
    const base = montant - diviserArrondi(montant * remise, 10000);
    const pourMille = Math.round(demandee.taux_tva * 10);
    basesParTaux.set(pourMille, (basesParTaux.get(pourMille) ?? 0) + base);
    return {
      code: article.code,
      libelle: article.libelle,
      quantite: quantite / 100,
      prix_unitaire_ht_euros: prix / 100,
      taux_tva: demandee.taux_tva,
      montant_ht_euros: montant / 100,
    };
  });
  const [premiere, ...suivantes] = lignes;
  if (premiere === undefined) {
    throw new ErreurOutil("un devis a au moins une ligne");
  }
  let ht = 0;
  let tva = 0;
  for (const [pourMille, base] of basesParTaux) {
    ht += base;
    tva += diviserArrondi(base * pourMille, 1000);
  }
  if (ht <= 0) {
    throw new ErreurOutil("le total hors taxes d'un devis doit être positif");
  }
  return {
    lignes: [premiere, ...suivantes],
    total_ht_euros: ht / 100,
    total_tva_euros: tva / 100,
    total_ttc_euros: (ht + tva) / 100,
  };
}
