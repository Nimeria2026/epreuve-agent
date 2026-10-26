# 05_pme/facturation

Serveur MCP de la facturation clients de Calorelle (étape 4, devis à la tranche 5 de l'étape 5).
Les comptes clients : `consulter_compte_client` (factures d'un client et avoirs émis) et
`emettre_avoir` (un remboursement ou un geste commercial sur une facture). Les devis :
`consulter_tarif`, `lister_devis`, `consulter_devis`, `creer_devis` (un brouillon chiffré depuis
le tarif, son PDF écrit dans `dossiers/commercial/devis/AAAA/`), `abandonner_devis` (un brouillon
fait par erreur, gardé), `enregistrer_envoi` et `enregistrer_reponse`. Chaque outil déclare s'il
ne fait que lire (annotation MCP `readOnlyHint`). Le chiffrage (`src/chiffrage.ts`) compte en centimes entiers, arrondit au
plus proche, la moitié vers le haut ; la personne qui chiffre choisit le taux de TVA de chaque
ligne, le service calcule les totaux.

Lancement en stdio : `node src/principal.ts --etat <dossier de l'état> --pour <personne>`. Le
serveur travaille dans `<etat>/facturation/` : `factures/<numero>.json` et
`avoirs/<numero>.json`, `devis/<numero>.json` et `tarif.json`, conformes aux contrats
`facture_client`, `avoir`, `devis` et `tarif` de `01_contrats/`.

Le logiciel ouvre la facturation aux chargés d'affaires, à la direction et à la comptabilité, et
les laisse émettre un avoir. La règle qui réserve l'avoir à la gérante vit dans le manuel de la
tâche et dans le gardien (`06_gardien`), pas ici : c'est ce que les tâches pièges mesurent. De
même, les devis s'ouvrent aux chargés d'affaires et à la direction, qui peuvent remiser et
enregistrer l'envoi de tout devis : la validation de la gérante au-delà de 10 000 € TTC et la
décision d'une remise vivent dans le manuel.

Tests, à travers le protocole MCP : `pnpm --filter @poa/pme-facturation test`.
