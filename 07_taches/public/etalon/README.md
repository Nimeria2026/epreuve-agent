# Jeu étalon du juge

Le juge (étape 4) tranche les critères qu'une règle ne sait pas vérifier sur du texte libre. Il
n'entre au banc (règle 7 du BRIEF) que s'il répond sur ce jeu étalon comme les personnes qui
l'ont étiqueté : deux personnes, chacune de son côté ; le juge doit s'accorder avec chacune au
moins autant qu'elles s'accordent entre elles, et n'accepter aucune réponse écrite exprès que
toutes deux rejettent (`make etalonner QUI=... AVEC=...`).

- `criteres.yaml` : les critères, des affirmations vraies ou fausses sur le texte écrit par
  l'agent, tâche par tâche, avec les destinataires dont on juge les courriels. Une affirmation
  tient en une phrase et ne porte qu'un seul point : une seule réponse possible. Le contexte de chaque tâche dit ce que l'agent avait sous les yeux
  (le courriel reçu et sa date, les faits du dossier, la règle du manuel) : il est montré à la
  personne qui étiquette et donné au juge.
- `fausses.yaml` : des réponses écrites exprès, fausses pour au moins un critère, sauf une juste
  par tâche.
- `textes.json` : les textes à étiqueter, produits une seule fois par `make etalon` (textes réels
  tirés des runs du 2026-10-05, et réponses écrites exprès). Une tâche dont les critères arrivent
  plus tard y ajoute les siens par `make etalon AJOUTER=1`, sans toucher aux autres (t06 et t09,
  2026-10-07). Ce fichier dit d'où vient chaque texte : ne pas l'ouvrir avant d'avoir fini
  d'étiqueter.
- `etiquettes_<qui>.json` : les réponses d'une personne, posées à l'aveugle par
  `make etiqueter` (Alexandre par défaut, `QUI=<prénom>` pour une seconde personne), texte par
  texte : un texte, puis ses affirmations une à une ; on peut s'arrêter et reprendre. Chacun
  étiquette seul, sans en parler à l'autre avant la fin : c'est ce qui permet de mesurer
  l'accord entre humains. Une seconde personne pressée peut s'en tenir à la moitié des textes,
  tirée une fois pour toutes par tâche et par source (`MOITIE=1` : 30 textes, 68 questions).
- `relecture_<qui>.json` : après `make relire`, la décision de la personne sur chaque désaccord
  avec le juge. Les étiquettes d'origine ne sont jamais retouchées.
- `controle/` : le jeu de contrôle (`make controle`), les textes des runs où le juge a
  tranché, neufs pour lui, avec les critères de ce dossier (pour une tâche dont les critères
  arrivent plus tard : tous ses textes hors jeu étalon, `make controle AJOUTER=1`, et
  `make fausses-qwen TACHES=...`) ; étiquetés à l'aveugle
  (`make etiqueter CONTROLE=1`), puis comparés au juge (`make etalonner CONTROLE=1`). Il décide
  si le juge tient, l'étalonnage ayant servi de réglage. Un critère neuf peut s'étalonner par le seul contrôle (t48,
  JOURNAL, entrée 268) : `make controle AJOUTER=1 TACHES=t48` en tire les textes, des trois modèles
  mesurés, hors des réponses lues pour écrire sa consigne (`REGLAGE` dans `ease.etalon`) ;
  `make etiqueter CONTROLE=1 TACHES=t48` et `make etalonner CONTROLE=1 TACHES=t48` s'en tiennent à
  ses questions. Les modèles réussissant presque tout,
  des réponses fausses y sont ajoutées, quatre par tâche jugée, écrites par Qwen
  (`make fausses-qwen`, sans voir les critères) ou tapées par une personne
  (`make ecrire-fausses`), jamais par Claude ni par le juge ; elles vont dans
  `controle/fausses_<qui>.json`, l'erreur voulue notée à part et jamais montrée.
- `verdicts_temoins.json` : les verdicts du juge réel sur les textes des témoins du banc
  (parfait, toujours faux, tricheurs), écrits par `make verdicts-temoins` et rejoués sans appel
  par les tests et `make temoins`.
- `dure/` : le jeu des consignes de la tranche dure (JOURNAL, cent-quatre-vingt-neuvième entrée ;
  cadrage `00_docs/sources/2026-10-17_cadrage_etalonnage_consignes_tranche.md`). Son
  `criteres.yaml` ne dit que `jeu: dure` : les critères sont les vérifications `juge_requis` des
  tâches de `07_taches/public/dure/`, lues dans les tâches mêmes, chacune avec ses destinataires
  et ses faits ; un texte n'y croise que les consignes dont le juge lirait ce courriel. Les textes
  réels, ceux des runs à la version courante de chaque tâche, sont partagés une fois en deux
  moitiés par tâche (`make etalon JEU=dure`) : `dure/textes.json`, l'étalon, avec les réponses
  écrites exprès par Claude (`dure/fausses.yaml`, une fausse par consigne et une juste par tâche),
  où l'on règle les consignes ; `dure/controle/textes.json`, le contrôle, qui décide, avec les
  réponses fausses de Qwen. Mêmes commandes, avec `JEU=dure` : `make etiqueter`,
  `make etalonner`, `make relire`. Décision d'Alexandre du 2026-10-17 : seul le contrôle
  s'étiquette (`make etiqueter JEU=dure CONTROLE=1`), les consignes ayant déjà été réglées sur les
  échecs réels des runs ; l'étalon reste en réserve, pour revérifier une consigne réécrite. Avec
  `NEUVES=1`, `make etiqueter JEU=dure` et `make etalonner JEU=dure` ne posent que les questions
  des consignes que le contrôle n'a pas étiquetées (JOURNAL, deux-cent-unième entrée).

La clé d'un critère est l'empreinte de son affirmation et de son contexte : rien ne change une
fois étiqueté. Une nouvelle version des critères pose de nouvelles questions ; les étiquettes des
anciennes restent dans le fichier, sans compter. Tout est fictif.
