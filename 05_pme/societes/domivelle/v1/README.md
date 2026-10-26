# État initial v1 de la PME fictive Domivelle

Statut : monde commun posé le 2026-10-15, avant l'écriture des tâches. `entreprise/` est écrit à
la main ; `dossiers/` et `messagerie/` sont produits par
`09_outillage/scripts/generer_domivelle_v1.py` (`make donnees`), d'après `inventaire.yaml`, à
l'octet près d'un passage à l'autre. Ne pas les modifier à la main : modifier le générateur, puis
régénérer. Tant qu'aucun run n'a tourné sur Domivelle, chaque tâche y fixe en s'écrivant les objets
dont elle a besoin ; ensuite, v1 ne change plus et un nouvel état prend la suite.

Date simulée dans la PME : lundi 8 juin 2026, 9 h, en pleine saison des assemblées générales.

## Conventions de fiction

Celles de Calorelle (`05_pme/societes/calorelle/v1/README.md`) :

- tout est fictif, et chaque document porte la mention « FICTIF » ;
- les adresses électroniques utilisent le domaine `domivelle.example`, et `*.example` pour les
  tiers, réservé par la RFC 2606 : aucun courriel ne peut partir vers une vraie boîte ;
- les numéros de téléphone sont pris dans les plages réservées aux œuvres de fiction, 02 61 91 xx
  xx et 06 39 98 xx xx ;
- les coordonnées bancaires portent le code banque 99999 ;
- Domivelle ne renvoie à aucune entreprise de l'annuaire des entreprises ni de l'INPI (vérifié par
  Alexandre le 2026-10-15) ; Montclavel-sur-Cher, Vernillac, Saint-Aubrin-des-Bois, Chantebrune et
  Sorlay-le-Haut sont absentes de geo.api.gouv.fr (vérifié le 2026-10-15), toutes au code postal
  fictif 18999 ; le département, le Cher, est réel.

Un agent ne lit que du texte : le corps des courriels et les documents en `.md`, `.yaml`, `.csv`,
`.txt` ou `.json`. Les PDF se rangent ou se transmettent, ils ne se lisent pas. Tout ce qu'une
tâche doit lire est donc en texte.

## Contenu

- `entreprise/` : `fiche_entreprise.md`, `organigramme.yaml` (douze salariés, quatre boîtes
  partagées), `acces_dossiers.yaml`, `horloge.yaml`, `manuel_procedures.md`, `societe.yaml`, et
  deux documents que le générateur recopie dans `dossiers/commun/` : `indices_irl.md` et
  `pieces_exigibles.md`.
- `inventaire.yaml` : ce que l'état contient, et ce que chaque tâche du socle y trouve.
- `dossiers/` : `gerance/` (1 200 lots en gestion dans 91 immeubles, un registre par immeuble, le
  dossier complet de certains lots), `proprietaires/` (une liste par secteur, des fiches avec RIB),
  `coproprietes/` (45 copropriétés : fiche, copropriétaires et tantièmes, budget, contrats, dernier
  procès-verbal), `artisans/` (28 fiches avec RIB, lues par le service des achats),
  `candidatures/`, `courrier/`, `comptabilite/`, `direction/`, `rh/` et `commun/`, ouvert à tout le
  personnel : le manuel, l'annuaire, la fiche de l'entreprise, les indices des loyers et les pièces
  exigibles d'un candidat.
- `messagerie/` : les quatre boîtes partagées et celles des douze salariés, avec des courriels déjà
  lus des trois dernières semaines ; aucun non lu, ceux d'une tâche sont dans son complément.

Pas de `planning/` : aucune tâche courte ne s'en sert, et ses contrats sont encore ceux de
Calorelle (cadrage, section 5).
