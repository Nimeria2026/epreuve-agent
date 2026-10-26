# 05_pme/messagerie

Serveur MCP de la messagerie de Calorelle. Sept outils : `lister_boites`, `lister_courriels`,
`lire_courriel`, `transferer`, `repondre`, `envoyer`, `enregistrer_piece_jointe`.

Chaque boîte est un dossier de `<etat>/messagerie/boites/<adresse>/`, avec `reception/` et
`envoyes/` ; chaque courriel est un fichier JSON conforme à `01_contrats/courriel.schema.json`,
vérifié à chaque écriture. Les pièces jointes sont rangées dans `<etat>/messagerie/pieces/`.

La personne servie n'ouvre que sa boîte et les boîtes partagées qu'elle gère (organigramme). Un
envoi est rangé dans `envoyes/` de la boîte d'envoi et déposé, non lu, dans la boîte de chaque
destinataire de Calorelle. Vers l'extérieur, rien ne part : seules les adresses en `.example`
sont acceptées. Les envois sont numérotés `m-env-001`, `m-env-002`, et ainsi de suite, et datés depuis l'heure
simulée (`entreprise/horloge.yaml`), une minute d'écart : deux exécutions identiques produisent
les mêmes fichiers.

Correspondants simulés (étape 4, `src/correspondants.ts`) : une personne extérieure dont les
réponses sont écrites d'avance dans `<etat>/messagerie/correspondants/<adresse>.yaml`. La
n-ième réponse arrive, non lue, après le n-ième courriel que Calorelle lui envoie, numérotée
`m-rep-001`, `m-rep-002`, datée trente secondes après ce courriel. Elle ne dépend pas de ce que
l'agent a écrit.

Lancement en stdio : `node src/principal.ts --etat <dossier de l'état> --pour <personne>`.
Tests, à travers le protocole MCP : `pnpm --filter @poa/pme-messagerie test`.
