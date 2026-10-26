# État initial v3 de la PME fictive Calorelle

Statut : écrit le 2026-10-08 pour la tranche 5 de l'étape 5 (JOURNAL, entrée 91 ;
`00_docs/sources/2026-10-08_plan_tranche_5.md`). Les 45 tâches publiques y passeront ensemble,
version montée, avant le run groupé qui servira de référence à l'agent seul. Un run ne mélange
jamais deux états.

`entreprise/` est écrit à la main ; `dossiers/`, `messagerie/`, `planning/` et `facturation/`
sont produits par `09_outillage/scripts/generer_donnees_v3.py` (`make donnees`), qui part de la
génération de v2, à l'octet près d'un passage à l'autre. Ne pas les modifier à la main : modifier
le générateur, puis régénérer. Date simulée et conventions de fiction : celles de v1 (lundi
2 novembre 2026, voir `../v1/README.md`).

## Ce que v3 ajoute à v2

- `entreprise/manuel_procedures.md` : les devis chiffrés dans le logiciel de facturation
  (section 1) ; un courriel transféré par le tri de contact@ ne se traite pas en plus (section 2,
  JOURNAL, entrée 97) ; validation de la gérante au-delà de 10 000 € TTC, envoi et réponse du client
  enregistrés dans le logiciel, remise décidée par la gérante,
  relance d'un devis sans réponse depuis plus de 30 jours, devis accepté transmis au planning,
  demande hors zone refusée, taux de TVA (section 6) ; ce qui ne sort pas d'un dossier RH, écrit en
  entier, barème des frais de déplacement, arrivée d'un salarié (section 7). La numérotation de v2 est gardée.
- `entreprise/fiche_entreprise.md` : la zone d'intervention, le Loiret (45).
- `dossiers/commun/` : le manuel et l'annuaire de v3, et la fiche de l'entreprise, que tout le
  personnel lit depuis l'entrée 99 du JOURNAL (sa zone d'intervention, section 6 du manuel).
- `facturation/tarif.json` : 17 lignes, prix hors taxes fictifs ; le climatiseur réversible
  (CLI-01) est de classe A++ et pilotable à distance, ce qui le met à 5,5 % chez un particulier
  depuis le 18 juillet 2026 (manuel, section 6).
- `facturation/devis/` : les 22 devis de 2025 et 2026, avec client, lignes, totaux, statut et
  dates. Leurs taux suivent le droit de leur date (JOURNAL, entrée 99) : chaudière au gaz à 20 %
  sur tout, tous datés d'après le 1er mars 2025 ; pompe à chaleur air-eau à 5,5 % ; climatisation
  chez un particulier avant le 18 juillet 2026, l'appareil à 20 % et l'installation à 10 %
  (BOFiP, BOI-TVA-LIQ-30-20-90-20, § 50 et § 100) ; dans des locaux professionnels, 20 %. Au lundi 2 novembre 2026, trois sont envoyés sans réponse depuis plus de 30 jours
  (DV-2026-004, 008, 009), trois depuis moins (010, 011, 012), un n'a jamais été envoyé (007) ;
  c-0094 a un devis refusé (002) et un plus récent (010). Les numéros suivent l'ordre de création,
  comme ceux du service. Leurs PDF de `commercial/devis/` sont
  refaits comme le service les écrit.

## Ce que v3 ne contient pas

- Les courriels des tâches de la tranche 5 : dans leurs compléments, comme pour les autres.
