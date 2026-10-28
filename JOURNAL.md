# Journal public d'Épreuve d'agent

Les décisions et les événements qui comptent pour qui lit nos chiffres : une version du protocole,
une publication, une correction, un modèle mesuré. Une entrée par événement, datée, numérotée
depuis 1, la plus récente en haut. Ce journal commence avec la version 1 du protocole ; les notes de
travail d'avant restent dans l'atelier, et les renvois du code à un « JOURNAL » numéroté désignent
ces notes internes.

Une entrée publiée ne se modifie pas : une erreur s'y corrige par une entrée nouvelle, qui cite
l'ancienne.

---

## 3. 2026-10-28 : le premier constat, octobre 2026

- Le premier constat d'Épreuve d'agent est publié : `08_publications/2026-10-28_constat/`, sous le
  protocole en version 1. Trois modèles sous le même agent : DeepSeek V4.1 Flash par son API, Qwen
  3.8 27B et Qwen3.8-Flash-Next en local. Ses chiffres, et les runs qui les fondent, sont dans le
  dossier ; sa page : https://nimeria.fr/epreuve-agent/2026-10/constat.
- Avec lui, la question d'entreprise, sur les tâches publiques seules :
  `08_publications/2026-10-28_premier_post/` ; sa page :
  https://nimeria.fr/epreuve-agent/2026-10/quel-travail-confier. Elle reprend le passage des témoins
  du constat, écrit sur le même code ; son manifeste le dit (`temoins_repris_de`).
- Qwen 3.8 27B est déclaré avec 102 400 jetons de contexte ; une partie de ses tâches, mesurées
  avant l'élargissement, l'ont été à 40 960 jetons. Le constat dit combien, et le protocole
  (partie 5) dit pourquoi le calcul l'accepte.
- Sur τ²-bench, le score publié de DeepSeek V4.1 Flash, sans écart type, sort de notre fourchette,
  qui est celle de Wilson et plus étroite qu'elle ne devrait ; celui de Qwen 3.8 27B, avec son écart
  type, y entre (protocole, partie 6).
- Ce dépôt devient public avec ces publications ; l'étiquette `publication-2026-10-28` désigne le
  commit qui les apporte, et les pages du site renvoient à elle.

## 2. 2026-10-27 : un troisième modèle mesuré, Qwen3.8-Flash-Next

- Qwen3.8-Flash-Next s'ajoute aux deux modèles du premier constat, sans rien changer à la méthode :
  le même agent, les mêmes tâches, les mêmes contrôles, le protocole en version 1.
- Sa configuration : en local, quantifié en IQ3_S (GSQ-RCO, d'ISTA-DASLab) et servi par Strata
  0.2.4.2, sur la même RTX 3090 et environ 50 Go de mémoire vive, avec un contexte de 131 072 jetons
  et les réglages de l'éditeur. Ses chiffres valent pour cette configuration (protocole, partie 7).
- Il n'a pas de score publié sur τ²-bench : sa ligne y donne notre mesure et ne contrôle rien
  (protocole, partie 6).

## 1. 2026-10-26 : le protocole de mesure, version 1

- Le protocole est figé en version 1 : `00_docs/protocole/README.md`, étiquette git `protocole-v1`.
  Toute mesure publiée sous cette version suit ce texte ; une méthode qui change donne une version 2.
- Le terrain : Calorelle, entreprise fictive de 18 salariés. Le socle compte 63 tâches publiques et
  20 cachées, la tranche dure 12 publiques et 3 cachées ; chaque tâche est refaite cinq fois. Les
  tâches cachées ne sont jamais publiées : elles mesurent ce qu'un modèle n'a pas pu voir.
- Deux modèles de référence pour le premier constat : DeepSeek V4.1 Flash, dans sa version du 17
  octobre 2026, par son API officielle ; Qwen 3.8 27B en local, sur une carte RTX 3090, avec 102 400
  jetons de contexte. Une partie de ses tâches, mesurées avant l'élargissement de son contexte, l'ont
  été à 40 960 jetons ; si l'un de leurs essais y avait été coupé par le contexte, le calcul
  s'arrêterait (protocole, partie 5).
- Le juge, qui tranche les points qu'un contrôle automatique ne peut pas lire, est DeepSeek V4.1
  Flash en version du 17 octobre 2026. Étalonné le 2026-10-26 : au socle, il s'accorde sur les 263
  questions de contrôle et n'accepte aucune réponse fausse ; à la tranche dure, il s'accorde sur
  95 % des 144 questions et accepte une réponse fausse. Ses limites : protocole, partie 4.
- Le banc se contrôle lui-même : des agents témoins au comportement connu doivent obtenir leur taux
  attendu, et sur τ²-bench, un banc public, nos fourchettes doivent contenir les scores publiés qui
  portent un écart type (protocole, partie 6).
- Un chiffre public ne vient que d'une publication de `08_publications/`, dont le manifeste liste
  les runs qui le fondent.
