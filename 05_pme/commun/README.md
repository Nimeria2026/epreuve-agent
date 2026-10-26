# 05_pme/commun

Code partagé par les services de la PME. Aucun serveur ici.

- `src/contrats/` : types TypeScript générés depuis `01_contrats/` par `make contrats`, à ne pas
  modifier à la main ;
- `src/validation.ts` : vérifie des données contre un contrat de `01_contrats/` (Ajv) ;
- `src/chemins.ts` : résout un chemin donné par un agent sans jamais sortir de l'état de la PME ;
- `src/droits.ts` : personne servie, boîtes qu'elle ouvre et droits d'accès aux dossiers, lus
  dans l'état ;
- `src/dossiers.ts` : accès d'une personne aux dossiers partagés, droits et confinement compris ;
- `src/courriels.ts` : lecture et écriture des courriels, vérifiés par leur contrat, identifiants
  et dates des envois tirés de l'horloge simulée.

Tests : `pnpm --filter @poa/commun test`.
