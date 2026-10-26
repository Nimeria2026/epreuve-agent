# État initial v2 de la PME fictive Calorelle

Statut : écrit le 2026-10-07 pour la tranche 4 de l'étape 5 (JOURNAL, entrées 81 et 82). Les 35
tâches publiques en partent : les treize des étapes 2 à 4 y sont passées ensemble, version
montée, le 2026-10-08 (entrée 90). Un run ne mélange jamais deux états.

`entreprise/` est écrit à la main ; `dossiers/`, `messagerie/` et `planning/` sont produits par
`09_outillage/scripts/generer_donnees_v2.py` (`make donnees`), qui part de la génération de v1, à
l'octet près d'un passage à l'autre. Ne pas les modifier à la main : modifier le générateur, puis
régénérer. Date simulée et conventions de fiction : celles de v1 (lundi 2 novembre 2026, voir
`../v1/README.md`).

## Ce que v2 ajoute à v1

- `entreprise/organigramme.yaml` : les neuf techniciens, droits `lire_planning` et
  `rediger_compte_rendu` ; 18 personnes en tout, comme le dit la fiche de l'entreprise.
- `entreprise/manuel_procedures.md` : les six règles de l'entrée 82, dans les sections 4, 7 et 9 ;
  l'échéancier et le logiciel de planning dans la section 1. La numérotation de v1 est gardée :
  les devis de v1 citent la section 6.
- `dossiers/commun/` : le manuel et l'annuaire de v2.
- `dossiers/administration/` : les conditions de paiement de dix fournisseurs (à réception, à
  30 jours) ; huit factures de fin septembre et d'octobre ; `echeancier_fournisseurs.md`, tenu par
  le comptable, à jour au jeudi 29 octobre : 18 factures, leur échéance et leur règlement.
- `dossiers/rh/conges_2026.txt` : les congés et absences validés de fin 2026, avec leur motif ;
  jamais plus de deux techniciens absents le même jour.
- `planning/`, lu et écrit par le service de planning (`05_pme/planning`) :
  - `horaires.yaml` : jours et plages d'intervention ; les onze jours fériés légaux de 2026 et
    2027 (Code du travail, article L3133-1), calculés par le générateur ;
  - `techniciens/` : onze fiches, compétences, apprenti, indisponibilités sans motif ;
  - `interventions/` : 39 rendez-vous du 2 au 26 novembre, dont un annulé. Le mardi 3 novembre,
    lendemain de l'horloge, en compte neuf, dont trois de Thomas Girard, deux avec l'apprenti.
    Quatre clients du mois anniversaire de novembre attendent leur visite (c-0066, c-0135,
    c-0307, c-0536). Les clients des tâches des étapes 2 à 4 n'y figurent pas.

## Ce que v2 ne contient pas

- Les devis dans la facturation : tranche 5.
- Les courriels des tâches de la tranche 4 : dans leurs compléments, comme pour t06 à t13.
