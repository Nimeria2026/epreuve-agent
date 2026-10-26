# interface_web

L'interface web de la PME (ADR 0005) : le poste humain, qui chronomètre une personne sur une
tâche, dans les mêmes conditions qu'un agent. Conception :
`00_docs/sources/2026-10-13_conception_poste_humain.md` (JOURNAL, cent-vingt-et-unième entrée).

## Ce qu'il fait

EASE le lance comme un candidat externe (`02_ease/src/ease/candidats/humain_p1.yaml`), une fois
par essai, après avoir remis la PME à zéro. Le poste sert une page sur `127.0.0.1`, port 30200
(variable `POA_POSTE_HUMAIN_PORT`) :

1. « Commencer » : le chronomètre part, l'énoncé et la PME apparaissent ;
2. la personne travaille par les vues de chaque service : messagerie et dossiers dans des vues
   dédiées, planning, facturation et achats par des formulaires tirés du schéma de chaque outil ;
3. « J'ai fini », confirmé : le chronomètre s'arrête, le poste écrit sa sortie (contrat
   `sortie_candidat`, avec `duree_chronometree_secondes`) et s'arrête ; EASE passe les contrôles ;
4. la page attend le poste de la tâche suivante et s'ouvre d'elle-même.

« Abandonner l'essai » écrit une sortie en erreur : l'essai compte comme une erreur technique,
écartée des taux, et se refait plus tard. Aucun retour sur la réussite n'est donné pendant la
séance.

L'affichage passe par l'accès en lecture seule du relais d'EASE, hors budget ; les actions et la
lecture d'un courriel, qui le marque comme lu, passent par l'accès des actions et comptent des
étapes, comme pour un agent.

## Fichiers

- `src/principal.ts` : point d'entrée, arguments `--mcp`, `--mcp-lecture`, `--enonce`, `--sortie` ;
- `src/serveur.ts` : les états (attente, en cours, fini), les pages et le chronomètre ;
- `src/pme.ts` : les outils vus à travers le relais, leur service, leur titre, et le bon accès ;
- `src/formulaires.ts` : les formulaires tirés du schéma JSON des arguments, et leur lecture ;
- `src/vues.ts` : la boîte de réception, le courriel, le contenu d'un dossier ;
- `src/html.ts` : l'échappement et la page commune.

Pages rendues par le serveur, sans fichier `.html` ni `.css` : la zone garde ses extensions.

## Commandes

Une séance, depuis la racine du dépôt, puis ouvrir http://127.0.0.1:30200 :

    make humain PERSONNE=p1 TACHES=t19,t04,t36,t31,t14

Les tests et les types :

    pnpm --filter @poa/pme-interface-web test
    pnpm --filter @poa/pme-interface-web types
