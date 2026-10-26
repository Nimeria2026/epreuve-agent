# 01_contrats

Les contrats de données du projet, écrits en JSON Schema. C'est la source de vérité : les modèles
Pydantic côté Python et les types côté TypeScript en sont générés, jamais écrits à la main.

Un fichier par contrat, nommé `nom.schema.json` (par exemple `fiche_de_run.schema.json`). Des
exemples valides peuvent vivre dans `exemples/`.

Génération : `make contrats`, par le script `09_outillage/scripts/generer_contrats.py`. Côté
Python, datamodel-code-generator écrit les modèles Pydantic dans `02_ease/src/ease/contrats/` ;
côté TypeScript, json-schema-to-typescript écrit les types dans `05_pme/commun/src/contrats/`, et
Ajv vérifie les données contre les mêmes schémas pendant l'exécution. `make tests` échoue si le
code généré n'est plus à jour, dans l'un ou l'autre langage.

Contrats présents :

- `tache.schema.json` : une tâche de la PME, dont l'agent ne voit que l'énoncé ; depuis la
  version 2, chaque contrôle porte ses vérifications exécutables ;
- `fiche_de_run.schema.json` : une campagne de mesure, de quoi la rejouer (règle 1 du BRIEF) ;
  le champ facultatif `banc_public` (étape 7) nomme le banc public d'un run hors de la PME, sa
  version, son domaine, son jeu et le simulateur d'utilisateur, avec ses jetons et son coût ;
- `resultat_execution.schema.json` : un passage du candidat sur une tâche, pour une répétition ;
- `fiche_candidat.schema.json` : le système mesuré, et ce qui permet ou non de le classer ;
- `courriel.schema.json` : un courriel de la PME, écrit par la messagerie (TypeScript) et relu par
  EASE (Python) ; les adresses sont toujours en `.example` ;
- `facture_client.schema.json` et `avoir.schema.json` : une facture d'un client et un avoir sur
  elle, gardés par le service facturation de la PME (étape 4) ;
- `tarif.schema.json` et `devis.schema.json` : la grille de prix et un devis chiffré par le
  service facturation, avec son statut (étape 5, tranche 5) ;
- `technicien.schema.json` et `intervention.schema.json` : un technicien et un rendez-vous du
  planning de la PME (étape 5) ;
- `sortie_candidat.schema.json` : ce qu'un candidat lancé dans son propre processus rend à EASE,
  sa fin, ses jetons et les modèles annoncés par les API ; ses actions, elles, passent par le
  relais et son journal ;
- `types_communs.schema.json` : le catalogue du socle commun, les types de tâches que toute
  entreprise rencontre (`07_taches/public/types_communs.yaml`) ; une tâche y renvoie par le champ
  `type_commun` de son classement (`classement.schema.json`) ;
- `catalogue.schema.json`, `commande.schema.json`, `bon_de_livraison.schema.json`,
  `retour.schema.json` et `fiche_client_negoce.schema.json` : le catalogue et ses conditions de
  vente, une commande chiffrée, un bon de livraison, un retour et la fiche d'un client, gardés ou
  lus par le service de ventes de Négovelle (cadrage du 2026-10-17) ;
- `parametres_societe.schema.json` : ce qu'un état déclare de sa société fictive dans
  `entreprise/societe.yaml`, son nom, son domaine et le dossier des fiches des achats, lu par les
  services et par EASE ; un état sans ce fichier est celui de Calorelle (ADR 0006) ;
- `lecture_document.schema.json` : ce qu'EKE rend d'un PDF de la PME, chaque texte avec sa page
  et sa zone (étape 6). EKE n'a pas de code généré : il valide sa sortie contre ce schéma et le
  déclare comme `outputSchema` de ses outils MCP. Pas d'exemple dans `exemples/` : les tests
  d'EKE valident chaque lecture des PDF de la PME.

Convention commune : « ? » signifie inconnu, et le rapport le montre ; `null` signifie sans
objet. Ce que JSON Schema ne sait pas exprimer (somme des poids, score recalculé, réussite,
dates en UTC, statut cohérent) est vérifié par EASE au chargement (`ease.taches`,
`ease.fiches`, `ease.courriels`).

`exemples/` contient un fichier valide par cas courant ; `make tests` les vérifie tous. Ce sont
des exemples : les empreintes y sont fictives.
