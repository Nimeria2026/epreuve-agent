/**
 * Appel d'outil refusé (chemin hors des dossiers, droit manquant, fichier absent).
 * Le serveur renvoie le message à l'agent comme une réponse d'outil en erreur.
 */
export class ErreurOutil extends Error {
  override readonly name = "ErreurOutil";
}
