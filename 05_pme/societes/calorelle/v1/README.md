# État initial v1 de la PME fictive Calorelle

Statut : complet pour t01 à t05 depuis le 2026-10-05. `entreprise/` est écrit à la main ;
`dossiers/` et `messagerie/` sont produits par `09_outillage/scripts/generer_donnees_v1.py`
(`make donnees`), d'après `inventaire_premiere_tranche.yaml`, à l'octet près d'un passage à
l'autre. Ne pas les modifier à la main : modifier le générateur, puis régénérer.

Date simulée dans la PME : lundi 2 novembre 2026. Toutes les tâches de la v1 se déroulent ce
jour-là, en début de saison de chauffe.

## Conventions de fiction, valables pour toute donnée de la PME

- Tout est fictif, et chaque document porte la mention « FICTIF ».
- Les adresses électroniques utilisent le domaine `calorelle.example`, et `*.example` pour les
  tiers. Le suffixe `.example` est réservé par la RFC 2606 et n'appartient à personne : aucun
  courriel ne peut partir vers une vraie boîte (règle 12 du BRIEF).
- Les numéros de téléphone sont pris dans les plages réservées aux œuvres de fiction : 02 61 91 xx
  xx pour les fixes, 06 39 98 xx xx pour les mobiles.
- Les coordonnées bancaires portent le code banque 99999 et la mention FICTIF.
- La ville, Valmont-sur-Loire, est inventée : geo.api.gouv.fr ne connaît aucune commune de ce nom
  (vérifié le 2026-10-05). Le nom Calorelle ne renvoie à aucune entreprise dans l'annuaire des
  entreprises (recherche-entreprises.api.gouv.fr, vérifié le 2026-10-05). À l'INPI, aucune
  entreprise, marque, brevet ni dessin à ce nom (vérifié par Alexandre le 2026-10-05).

## Contenu

- `entreprise/fiche_entreprise.md` : qui est Calorelle.
- `entreprise/organigramme.yaml` : les personnes, leurs adresses, leurs droits.
- `entreprise/acces_dossiers.yaml` : les droits qui ouvrent chaque dossier partagé ; le mot
  réservé `tous` ouvre `commun/` à toute personne de l'organigramme.
- `entreprise/horloge.yaml` : l'heure simulée qui date les courriels envoyés pendant une
  exécution.
- `entreprise/manuel_procedures.md` : les règles que tout salarié, et tout agent, doit suivre.
  Le générateur le recopie dans `dossiers/commun/`, seul endroit où un agent peut le lire.
- `inventaire_premiere_tranche.yaml` : ce que l'état initial doit contenir pour les cinq
  premières tâches, bruit compris.
- `dossiers/` : 40 fournisseurs (fiche et RIB), 10 factures déjà rangées, 150 clients (fiche,
  contrat, comptes rendus) et leur liste, 22 devis, quelques documents de direction et de RH, et
  `commun/`, ouvert à tout le personnel : le manuel et l'annuaire.
- `messagerie/` : les boîtes comptabilite@, contact@ et celle de Julie Perrin, avec les courriels
  des tâches (non lus), le bruit (déjà lu) et les pièces jointes.
