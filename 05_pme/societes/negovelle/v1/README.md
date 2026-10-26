# État initial v1 de la PME fictive Négovelle

Statut : monde commun posé le 2026-10-17, avant l'écriture des tâches. `entreprise/` est écrit à
la main ; `dossiers/`, `messagerie/`, `facturation/` et `ventes/` sont produits par
`09_outillage/scripts/generer_negovelle_v1.py` (`make donnees`), d'après `inventaire.yaml`, à
l'octet près d'un passage à l'autre. Ne pas les modifier à la main : modifier le générateur, puis
régénérer. Tant qu'aucun run n'a tourné sur Négovelle, chaque tâche y fixe en s'écrivant les objets
dont elle a besoin ; ensuite, v1 ne change plus et un nouvel état prend la suite.

Date simulée dans la PME : lundi 6 juillet 2026, 8 h, premier jour ouvré après la fin du semestre.

## Conventions de fiction

Celles de Calorelle et de Domivelle :

- tout est fictif, et chaque PDF porte la mention « FICTIF » ;
- les adresses électroniques utilisent le domaine `negovelle.example`, et `*.example` pour les
  tiers, réservé par la RFC 2606 : aucun courriel ne peut partir vers une vraie boîte ;
- les numéros de téléphone sont pris dans les plages réservées aux œuvres de fiction, 02 61 91 xx
  xx et 06 39 98 xx xx ;
- les coordonnées bancaires portent le code banque 99999 ;
- Négovelle ne renvoie à aucune entreprise de l'annuaire des entreprises ni de l'INPI (vérifié par
  Alexandre le 2026-10-17) ; Vaumoreau-sur-Indre et les huit autres communes sont absentes de
  geo.api.gouv.fr (vérifié le 2026-10-17), toutes au code postal fictif 36999 ; le département,
  l'Indre, est réel ;
- aucune personne de Négovelle ne porte le nom de famille d'une personne de Calorelle ou de
  Domivelle (`02_ease/tests/test_negovelle_v1.py`).

Un agent ne lit que du texte : le corps des courriels et les documents en `.md`, `.yaml`, `.csv`,
`.txt` ou `.json`. Les PDF se rangent ou se transmettent, ils ne se lisent pas. Le catalogue, les
commandes, les livraisons et les retours se lisent par le service des ventes ; les factures et les
avoirs par celui de la facturation.

## Contenu

- `entreprise/` : `fiche_entreprise.md`, `organigramme.yaml` (22 salariés, quatre boîtes
  partagées), `acces_dossiers.yaml`, `horloge.yaml`, `manuel_procedures.md`,
  `conditions_generales_de_vente.md` et `societe.yaml`.
- `inventaire.yaml` : ce que l'état contient, et ce que chaque tâche y trouve.
- `ventes/` : le catalogue de 4 000 articles et ses conditions de vente, les commandes du 22 juin
  au 3 juillet, leurs bons de livraison, des retours.
- `facturation/` : les factures mensuelles de mai et de juin, les impayés plus anciens, des ventes
  au comptoir, des avoirs.
- `dossiers/` : `clients/` (350 fiches et leur liste, `liste.csv`), `fournisseurs/` (40
  fournisseurs et le transporteur, fiches avec RIB et factures de juin), `achats/` (commandes et
  réceptions de juin), `comptabilite/` (relevés, échéancier des fournisseurs), `courrier/`,
  `direction/`, `rh/` et `commun/`, ouvert à tout le personnel : le manuel, les conditions
  générales de vente, l'annuaire, la fiche de l'entreprise, les secteurs et les familles du
  catalogue.
- `messagerie/` : les quatre boîtes partagées et celles des 22 salariés, avec des courriels déjà
  lus des trois dernières semaines ; aucun non lu, ceux d'une tâche sont dans son complément.

Pas de `planning/` : aucune tâche ne s'en sert.
