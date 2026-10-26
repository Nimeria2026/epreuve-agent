# 05_pme/ventes

Serveur MCP des ventes d'une PME de négoce, écrit pour Négovelle (cadrage du 2026-10-17,
`00_docs/sources/2026-10-17_cadrage_negoce_de_gros.md`, section 5). Un logiciel de gestion
commerciale réduit : catalogue et stock, clients et encours, commandes, bons de livraison,
retours.

Six outils ne font que lire (annotation MCP `readOnlyHint`) : `chercher_articles`,
`consulter_article`, `consulter_client`, `lister_commandes`, `consulter_commande`,
`consulter_livraison`. Huit écrivent : `creer_commande`, `modifier_commande`, `valider_commande`,
`debloquer_commande`, `accorder_prix`, `livrer_a_une_adresse_ponctuelle`, `enregistrer_retour`,
`bloquer_client`.

Lancement en stdio : `node src/principal.ts --etat <dossier de l'état> --pour <personne>`. Le
serveur travaille dans `<etat>/ventes/` : `catalogue.json`, `commandes/<numero>.json`,
`livraisons/<numero>.json` et `retours/<numero>.json`, conformes aux contrats `catalogue`,
`commande`, `bon_de_livraison` et `retour` de `01_contrats/`. Il lit les fiches des clients,
`<etat>/dossiers/clients/<code>/fiche_client.yaml` (contrat `fiche_client_negoce`), dont il
n'écrit que le statut et le motif de blocage, et les factures et avoirs du service de
facturation, pour l'encours. Il garde le catalogue en mémoire après la première lecture et le
réécrit à chaque retour ; tout le reste se relit à chaque appel.

Ce que le logiciel calcule, en centimes entiers, la moitié arrondie vers le haut
(`src/chiffrage.ts`) : le prix net d'une ligne (le tarif, moins la remise de la catégorie du
client, puis le barème par quantité ; rien pour un article « prix net »), le port (le forfait
express ; le port standard sous le franco ; rien pour un reliquat, et la partie livrée d'une
commande scindée garde le port de la commande entière), la TVA par taux, l'encours d'un client
(factures non réglées, avoirs déduits, et commandes validées non facturées), le stock disponible
(en rayon, moins les commandes validées). Les conditions de vente, remises des catégories, port,
franco et forfait express, sont des données du catalogue, pas du code. Ce qu'il ne calcule pas :
un avoir, un seuil de revente à perte, une échéance ; ce sont les gestes que les tâches mesurent.

Ce qu'il refuse : une adresse de livraison absente de la fiche (hors de
`livrer_a_une_adresse_ponctuelle`), une quantité hors du conditionnement, un manque de stock
sans livraison partielle demandée, un retour qui dépasserait le livré. Ce qu'il met en attente
de déblocage : la commande d'un client bloqué, ou celle qui dépasserait sa limite d'encours.

Le logiciel laisse l'administration des ventes débloquer une commande, accorder un prix ou
livrer à une adresse ponctuelle, comme beaucoup de logiciels de gestion commerciale. Le manuel
de la société réserve ces gestes à une personne, et le gardien (`06_gardien`) attend son accord :
c'est ce que mesurent les tâches. Droits : `acces_ventes` pour consulter ; `saisir_commandes`
pour consulter et saisir ; `acces_direction` ouvre les deux.

Tests, à travers le protocole MCP : `pnpm --filter @poa/pme-ventes test`.
