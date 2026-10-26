# 11_bancs_publics

Les bancs publics d'agents construits par d'autres, servis à EASE par MCP (ADR 0004). Langage :
Python. Règle 11 du BRIEF : une orchestration d'Alexandre n'est jamais classée sur les seules
tâches de sa PME ; règle 4 : sur un banc public importé, EASE doit retrouver les scores publiés.

EASE n'importe rien d'ici (règle 6, test de frontière d'EASE) ; ce paquet n'importe ni EASE ni
une orchestration. Les données des bancs vivent dans `99_local/`, hors git.

Entrées permises : `README.md`, `pyproject.toml`, `src/`, `tests/`.

## τ²-bench (étape 7, ouverte le 2026-10-08)

τ²-bench de Sierra, version 1.0.1 (commit `fc0055d`), licence MIT, entré par son commit dans
`pyproject.toml` ; domaine airline, avec deux jeux de tâches : celui de Sierra et celui de
τ²-bench-Verified d'Amazon AGI (commit `864350a`, licence MIT), mêmes base et politique. Faits,
sources et choix : `00_docs/sources/2026-10-08_faits_tau2_bench.md` et
`2026-10-08_journal_tau2.md`.

- `src/bancs_publics/tau2_bench/donnees.py` : récupère les fichiers d'airline aux commits figés,
  empreinte sha256 vérifiée, dans `99_local/tau2/` (bibliothèque standard seule), dont les 800
  conversations airline de référence que publie Sierra (4 agents), et en tire le jeu `publie`, les
  tâches embarquées qui les ont notées ;
- `src/bancs_publics/tau2_bench/pont.py` : le seul module qui importe `tau2`. Il joue une
  conversation pas à pas dans le gymnase de τ²-bench (son orchestrateur, ses limites de 200
  messages et de 10 erreurs d'outil, ses fins de conversation), avec un utilisateur écrit d'avance,
  un utilisateur rejoué qui redit les messages d'une conversation publiée, ou un modèle de
  simulateur, et la note avec l'évaluateur de τ²-bench ; sous l'utilisateur rejoué, la note dit
  aussi si la conversation a divergé de la publiée (messages, réponses d'outil, fin) ;
- `src/bancs_publics/tau2_bench/serveur.py` : le serveur MCP. Il annonce les 14 outils d'airline
  tels que τ²-bench les présente à son agent (lecture seule annoncée selon leur type chez
  τ²-bench), `send_message_to_user` pour parler au client, et deux outils réservés à EASE,
  `poa_ouvrir` et `poa_cloturer`, que l'environnement d'EASE ne montre jamais à l'agent ;
- `src/bancs_publics/tau2_bench/__main__.py` : lancement en stdio ;
- `src/bancs_publics/tau2_bench/evaluer.py` : réévalue une simulation écrite sur le disque, dans
  un processus neuf ;
- `tests/` : données, outils, conversations jouées avec les gestes de référence, note, limites de
  τ²-bench, serveur par MCP, frontière ; conversations publiées rejouées, divergences vues.

Commandes, depuis la racine du dépôt :

```
uv run --all-packages python -m bancs_publics.tau2_bench.donnees      # données, une fois (réseau)
uv run --all-packages python -m ease.temoins_tau2                     # quatre témoins, 50 tâches de Sierra
uv run --all-packages python -m ease.temoins_tau2 --jeu verified --taches 0,14 --repetitions 2
uv run --all-packages python -m ease.rejeu_tau2                       # 800 conversations publiées, rejouées
uv run --all-packages python -m ease.rejeu_tau2 --agents gpt_4_1 --taches 0,14 --dans-le-processus
uv run --all-packages pytest 11_bancs_publics/tests 02_ease/tests/test_terrain_tau2.py 02_ease/tests/test_rejeu_tau2.py
```

Ce qui reste hors de ce paquet : les runs avec un modèle (clé du simulateur gemini-2.5-flash,
estimation du coût avant le run, règle 14), l'agent de reproduction qui remet son texte dans
`send_message_to_user`, un champ du contrat de fiche de run propre aux bancs publics.
