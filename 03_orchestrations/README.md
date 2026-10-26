# 03_orchestrations

Les orchestrations d'agents. Langage : Python.

Un sous-paquet par schéma d'orchestration : un agent seul, plusieurs agents qui se répartissent
le travail. Une orchestration appelle les modèles par une API compatible OpenAI et n'atteint la
PME qu'à travers le gardien. Elle n'a jamais accès aux contrôles ni aux solutions des tâches.

Entrées permises : `README.md`, `pyproject.toml`, `src/`, `tests/`.

Contenu actuel, depuis l'étape 3 (paquet `orchestrations`, membre de l'espace uv) :

- `src/orchestrations/agent_seul.py` : l'agent seul, une boucle entre un modèle et les outils.
  EASE le lance dans son propre processus avec `--mcp` (adresse du relais), `--enonce` et
  `--sortie` ; l'agent réécrit sa sortie (contrat `sortie_candidat`) après chaque appel de
  modèle ;
- `src/orchestrations/auteur_relecteur.py` : auteur et relecteur (étape 5, JOURNAL, entrées 80
  et 92). L'auteur travaille comme l'agent seul ; chaque action qu'il propose et que son service
  ne déclare pas en lecture seule (annotation MCP `readOnlyHint`) passe d'abord par le
  relecteur. Celui-ci reçoit l'énoncé et l'action, pas le raisonnement de l'auteur, lit ce qu'il
  veut avec les seuls outils en lecture seule, puis rend son verdict par l'outil `verdict` :
  accordée, l'action part ; renvoyée, l'auteur reçoit la raison. L'orchestration ne connaît
  aucun nom d'outil de la PME. Le budget d'étapes de la tâche reste celui de l'auteur : le
  relecteur lit par l'accès en lecture seule du relais (`--mcp-lecture`), compté à part par EASE
  (entrée 94). Lancement : `--configuration` (auteur) et `--relecteur` (relecteur), du même
  modèle ou d'un autre ;
- `src/orchestrations/modele.py` : appel d'un modèle par l'API HTTP compatible OpenAI, sans
  bibliothèque de fournisseur : vLLM en local, ou DeepSeek ; quelques nouveaux essais après une
  panne passagère ; lecture des jetons et du raisonnement dans les formats des fournisseurs ;
- `src/orchestrations/consignes/agent_seul.md` : la consigne système, courte et fixe ; son
  empreinte entre dans la fiche de run ; `auteur.md` (celle de l'agent seul, plus une phrase sur
  la relecture) et `relecteur.md` pour auteur et relecteur ;
- `src/orchestrations/configurations/` : comment joindre chaque modèle (`qwen_local.yaml`,
  `deepseek_flash.yaml`). Aucun paramètre ajouté : chaque modèle garde les réglages de son
  éditeur. La clé DeepSeek se lit dans la variable `DEEPSEEK_API_KEY` ou dans `.env`, hors git ;
- `tests/` : la boucle avec un modèle et des outils simulés, auteur et relecteur avec deux modèles
  simulés, et la règle qui interdit toute importation d'EASE.

Pour mesurer l'agent sur la PME : `make qwen` dans un terminal, puis
`make mesure CANDIDAT=agent_seul_qwen_local` dans un autre.
