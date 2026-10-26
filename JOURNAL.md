# Journal public d'Épreuve d'agent

Les décisions et les événements qui comptent pour qui lit nos chiffres : une version du protocole,
une publication, une correction, un modèle mesuré. Une entrée par événement, datée, numérotée
depuis 1, la plus récente en haut. Ce journal commence avec la version 1 du protocole ; les notes de
travail d'avant restent dans l'atelier, et les renvois du code à un « JOURNAL » numéroté désignent
ces notes internes.

Une entrée publiée ne se modifie pas : une erreur s'y corrige par une entrée nouvelle, qui cite
l'ancienne.

---

## 1. 2026-10-26 : le protocole de mesure, version 1

- Le protocole est figé en version 1 : `00_docs/protocole/README.md`, étiquette git `protocole-v1`.
  Toute mesure publiée sous cette version suit ce texte ; une méthode qui change donne une version 2.
- Le terrain : Calorelle, entreprise fictive de 18 salariés. Le socle compte 63 tâches publiques et
  20 cachées, la tranche dure 12 publiques et 3 cachées ; chaque tâche est refaite cinq fois. Les
  tâches cachées ne sont jamais publiées : elles mesurent ce qu'un modèle n'a pas pu voir.
- Deux modèles de référence pour le premier constat : DeepSeek V4.1 Flash, dans sa version du 17
  octobre 2026, par son API officielle ; Qwen 3.8 27B en local, sur une carte RTX 3090, avec 102 400
  jetons de contexte. Les tâches de Qwen mesurées avant l'élargissement de son contexte, à 40 960
  jetons, ne comptent que si aucun de leurs essais n'y a été coupé par le contexte.
- Le juge, qui tranche les points qu'un contrôle automatique ne peut pas lire, est DeepSeek V4.1
  Flash en version du 17 octobre 2026. Étalonné le 2026-10-26 : au socle, il s'accorde sur les 263
  questions de contrôle et n'accepte aucune réponse fausse ; à la tranche dure, il s'accorde sur
  95 % des 144 questions et accepte une réponse fausse. Ses limites : protocole, partie 4.
- Le banc se contrôle lui-même : des agents témoins au comportement connu doivent obtenir leur taux
  attendu, et τ²-bench, un banc public, doit retrouver les scores publiés des deux modèles.
- Un chiffre public ne vient que d'une publication de `08_publications/`, dont le manifeste liste
  les runs qui le fondent.
