# 05_pme

Les PME fictives. Langage : TypeScript.

Un sous-dossier par service, chacun étant un serveur MCP autonome (`messagerie/`, `dossiers/`,
puis `clients/` et les suivants), avec son `package.json`, son `src/` et ses `tests/`. L'interface
web de la PME (`interface_web/`, ADR 0005) suit la même forme.

`societes/` contient un dossier par société fictive (ADR 0006), avec ses données et rien
d'autre : l'état de départ versionné (salariés, clients, courriels, documents) et les
compléments d'état des tâches. Toutes ces données sont fictives et présentées comme telles. Les
services, eux, servent toutes les sociétés ; ce que le code porte encore de propre à Calorelle
est listé dans `societes/README.md`.

N'y met pas les tâches (`07_taches/`) ni le gardien (`06_gardien/`). Un service ne connaît ni les
agents ni les contrôles.

Contenu actuel :

- `commun/` : code partagé par les services, sans serveur : types générés depuis `01_contrats/`,
  validation par Ajv, chemins confinés à l'état, droits de la personne servie, PDF d'une page ;
- `dossiers/` : serveur MCP des dossiers partagés (lister, lire, déplacer, copier) ;
- `messagerie/` : serveur MCP de la messagerie (boîtes, lecture, transfert, réponse, envoi,
  enregistrement d'une pièce jointe dans les dossiers), avec ses correspondants simulés ;
- `facturation/` : serveur MCP de la facturation clients (compte d'un client, avoir), étape 4 ;
  devis chiffrés depuis le tarif, tranche 5 de l'étape 5 ;
- `achats/` : serveur MCP des fiches fournisseurs (consulter, changer un RIB), étape 4 ;
- `planning/` : serveur MCP du planning (techniciens, rendez-vous, créneaux), étape 5 ;
- `ventes/` : serveur MCP des ventes d'une PME de négoce (catalogue et stock, clients et encours,
  commandes, livraisons, retours), écrit pour Négovelle (cadrage du 2026-10-17) ;
- `interface_web/` : l'interface web de la PME, le poste humain qui chronomètre une personne sur
  une tâche (ADR 0005, JOURNAL, entrée 121) ; un client des services, pas un serveur MCP ;
- `societes/calorelle/` : les données de Calorelle, la PME du banc depuis l'étape 2 (jusqu'au
  2026-10-15 dans `donnees_initiales/`) ; états de départ v1, v2 et v3, dont
  `entreprise/acces_dossiers.yaml` pour les droits et `entreprise/horloge.yaml` pour l'heure
  simulée ; v2 ajoute `planning/`, les données du service de planning ; v3 ajoute le tarif et les
  devis de la facturation ; et `complements/`, propres à chaque tâche.
- `societes/domivelle/` : les données de Domivelle, seconde PME fictive, en administration de
  biens (ADR 0006 ; JOURNAL, entrée 155) ; état de départ v1, qui se déclare aux services par
  `entreprise/societe.yaml`.
- `societes/negovelle/` : les données de Négovelle, troisième PME fictive, en négoce de gros
  (cadrage du 2026-10-17) ; état de départ v1, dont `ventes/`, les données du service des ventes.

Chaque outil déclare s'il ne fait que lire (annotation MCP `readOnlyHint`) : une orchestration
s'en sert pour savoir quoi faire relire, sans connaître les noms des outils. `lire_courriel`
marque le courriel comme lu, et se déclare pourtant en lecture seule : ce marquage n'est pas une
action de l'entreprise. Un appel de l'accès en lecture seule d'EASE porte la clé
`poa/lecture_seule` dans son `_meta` MCP, que le gardien laisse passer : `lire_courriel` ne marque
alors rien, et le relecteur regarde sans rien changer.

Chaque serveur se lance en stdio, pour une personne de l'organigramme, sur un dossier d'état :

    node 05_pme/dossiers/src/principal.ts --etat <dossier de l'état> --pour patrick.roux

Il ne garde rien en mémoire : EASE remet l'état à zéro avant chaque exécution, lance lui-même les
serveurs dont la tâche a besoin, pour la personne qu'elle désigne, et leur parle par un client
MCP (`ease.pme`), comme le ferait n'importe quel agent. Il lit ensuite l'état final directement
pour ses contrôles (règle 3 du BRIEF). Node 24 exécute le TypeScript sans
compilation ; `tsc` ne sert qu'à vérifier les types (`make qualite`).
