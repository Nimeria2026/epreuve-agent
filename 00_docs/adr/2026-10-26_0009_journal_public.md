# ADR 0009 : un journal public, distinct du journal de l'atelier

Date : 2026-10-26
Statut : accepté

## Problème rencontré

Le dépôt public s'ouvre à la première publication (cadrage du dépôt public et de l'organisation,
section 3). Le code et les tâches y renvoient environ 900 fois à `JOURNAL.md`, le journal de
l'atelier, qui ne sort pas : il contient des notes internes et des passages personnels. Relevé du
2026-10-26 : au moins 107 entrées différentes y sont citées par leur numéro. Alexandre, le même jour :
« ce sont plein de données internes, ça sert à rien de publier tout ça ; il faut un vrai journal
public en commençant par la v1 ».

## Décision

- Un fichier nouveau à la racine, `JOURNAL_PUBLIC.md` : les décisions et les événements qui
  comptent pour qui lit les chiffres (une version du protocole, une publication, une correction, un
  modèle mesuré), écrits pour le public dès le départ, numérotés depuis 1, en commençant par la v1.
  L'export le publie sous le nom `JOURNAL.md`.
- Les renvois du code au journal de l'atelier restent tels quels ; le `README` public et le journal
  public disent qu'ils désignent des notes internes.

## Alternatives écartées

- Publier le journal de l'atelier après un tri : plus de deux cent quatre-vingt-dix entrées, des
  notes de travail et des passages personnels, sans intérêt pour le public.
- Une version publique de chaque entrée citée par le code : plus d'une centaine d'entrées à
  réécrire et à relire, pour des renvois que le public n'a pas besoin de suivre.
- Retirer les renvois à l'export : le code perdrait ses explications.

## Conséquences

- `arborescence.toml` passe en version 9 et cite l'ADR 0009 : la racine permet `JOURNAL_PUBLIC.md`,
  aussi en exception de nommage.
- Chaque publication, chaque version du protocole et chaque correction publique ajoutent une entrée
  au journal public ; `AGENTS.md` le dit.
