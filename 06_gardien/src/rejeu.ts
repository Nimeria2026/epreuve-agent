// Ce que devient, au rejeu, un appel que les règles visent (make rejouer-gardien). Défaut relevé
// à l'exercice de clôture de l'étape 4, le 2026-10-07 (JOURNAL, soixante-dix-huitième entrée) : le
// rejeu comptait comme « blocage à tort probable » des avoirs que la gérante simulée accepte (t13)
// et des refus réels du gardien dans des runs passés par lui (t10). Il lui manquait deux faits du
// banc : la validation simulée de la tâche, et si le run avait déjà le gardien.

/** Ce que l'appel visé serait devenu, ou est devenu, devant le gardien. */
export type Issue =
  | "validation_acceptee" // la validation simulée de la tâche accepte : l'appel passe, rien n'est bloqué
  | "refus_reel" // le run avait déjà le gardien : le refus a eu lieu, l'exécution a fait avec
  | "a_tort_probable" // refusé au rejeu, dans une exécution réussie sans gardien
  | "faute_arretee"; // refusé au rejeu, dans une exécution échouée sans gardien

export const LIBELLES: Record<Issue, string> = {
  validation_acceptee: "validation acceptée (simulée), rien de bloqué",
  refus_reel: "refus réel, run passé par le gardien",
  a_tort_probable: "blocage à tort probable",
  faute_arretee: "geste arrêté dans une exécution échouée",
};

export function classer(
  verdict: "bloque" | "validation",
  validationSimulee: "accepter" | "refuser",
  runAvecGardien: boolean,
  reussie: boolean,
): Issue {
  if (verdict === "validation" && validationSimulee === "accepter") {
    return "validation_acceptee";
  }
  if (runAvecGardien) {
    return "refus_reel";
  }
  return reussie ? "a_tort_probable" : "faute_arretee";
}
