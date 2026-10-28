# Fiche du moteur : Strata, Qwen3.8-Flash-Next (IQ3_S)

Fiche officielle du serveur de modèle des candidats `agent_seul_qwen_flash_next_strata` et
`reproduction_tau2_qwen_flash_next_strata`. Relevée le 2026-10-26 sur le poste de mesure, par
`strata --version`, `strata launch --plan` et `strata presets show flash-next` (JOURNAL, entrée 296).
Le préréglage tel que Strata l'exporte est à côté : `strata_flash_next.json`, les chemins du dossier
personnel écrits « ~ ».

## Le modèle et le moteur

- Modèle : Qwen3.8-Flash-Next, quantifié en IQ3_S (GSQ-RCO), 84 Go en deux fichiers
  (`Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf`, 54 817 524 224 octets, et son second
  fichier, la couche PLE). Empreinte du premier fichier, calculée par Strata sur des extraits du
  début, du milieu et de la fin : `a4f39bff…216c`.
- Strata 0.2.4.2 (build 0.1.49.2), qui lance son moteur 0.1.48, CUDA 13 (build `6f8800aefe27`,
  empreinte `211a9084…ad38`). Le moteur tient le modèle entre la carte et la mémoire vive.
- Machine : AMD Ryzen 9 7950X3D (16 cœurs, 32 fils), 60 Gio de mémoire vive, NVIDIA GeForce RTX 3090
  (24 Gio), pilote 595.99.02, noyau Linux 7.0.0-34, Ubuntu 24.04.

## Le préréglage « flash-next »

Créé le 2026-10-24 par `strata launch`, avec le réglage rapide de Strata :

| Choix | Valeur |
|---|---|
| Contexte | 131 072 jetons |
| Cache de la conversation | int8 |
| Images | coupées |
| Prédiction des jetons | MTP |
| Réglage | rapide ; issue « default_confirmed » : aucun réglage essayé n'a été plus rapide, le moteur garde ses réglages standard (aucun argument ni variable ajoutés) |
| Accès | cet ordinateur seul, port 30001, clé d'API |

Ce que le réglage a mesuré : 112,9 jetons par seconde au décodage, 2 054,5 au préremplissage d'un
texte de 4 096 jetons ; au plus 23 803 Mio sur la carte et 50 125 Mio de mémoire vive.

Ce que le moteur exécute alors, relevé dans son journal le 2026-10-25 :

```
strata --serve --pack ~/Modeles/strata/packs/iq3_s \
  --native ~/Modeles/strata/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf \
  --ple-gguf ~/Modeles/strata/models/IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf \
  --expert-profile ~/.local/share/strata/terminal/0.1.49.2/data/expert-profile.bin \
  --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp ~/Modeles/strata/mtp/rt \
  --max-context 131072 --kv int8 --batch 3
```

## Lancer, vérifier, arrêter

```
make strata                                  # vérifie, montre le plan, lance avec le moniteur
strata launch --status                       # ce qui tourne
strata launch --stop --preset flash-next     # l'arrêter
```

`make strata` (`09_outillage/scripts/servir_strata.sh`) lance le préréglage en redisant ses choix
(contexte, images, cache, MTP, accès, port) et en fixant trois créneaux, que le préréglage laisse à
Strata (« fit to card ») et qui étaient trois le 2026-10-25. Avant, il refuse :

- un Strata d'une autre version, ou un préréglage qui diffère de `strata_flash_next.json` par son
  identité, ses choix, ses réglages, l'issue de son réglage, son moteur ou son modèle
  (`09_outillage/scripts/verifier_strata.py`) ;
- une carte qui n'a pas 23 000 Mio libres, moins de 51 200 Mio de mémoire vive disponibles, ou un
  port 30001 déjà pris.

## Ce que les runs en gardent

- La fiche de chaque run note la machine (« Strata 0.2.4.2, contexte de 131 072 jetons ») et
  l'empreinte des consignes, qui compte la configuration de l'agent et `strata_flash_next.json`.
  Un préréglage nouveau change donc cette empreinte : ses runs ne s'assemblent pas avec les anciens.
- L'électricité relevée est celle de la carte seule ; la mémoire vive et le processeur, qui portent
  une part du modèle, n'y sont pas.

## Limites

- Un run à la fois. En parallèle, l'essai du 2026-10-25 a manqué de mémoire et reçu des refus HTTP
  503 ; le moteur occupe à lui seul près de 50 Gio des 60 de mémoire vive.
- Le moteur réserve d'un bloc une zone de 46 Gio de mémoire vive pour les experts. Le 2026-10-26,
  avec 41,3 Gio disponibles, il s'est arrêté pendant le chargement, sans autre message que
  « runtime control is unavailable » : il faut fermer ce qui occupe la mémoire avant de le lancer.
- Sous Ubuntu, `systemd-oomd` ferme tout un terminal quand la pression sur la mémoire de la session
  dépasse 50 % pendant 20 s. Le chargement du moteur l'a déclenché le 2026-10-26, à 71 %. Pendant les
  mesures : `sudo systemctl stop systemd-oomd`, puis `sudo systemctl start systemd-oomd` après ;
  `make strata` prévient tant qu'il est actif.
- Les réglages de l'agent (température 1,0, top_p 0,95, top_k 20) sont écrits dans sa
  configuration : ce que Strata applique sans eux n'est pas relevé.
- Le moteur 0.1.48 a le défaut du ticket #1503 de Strata, corrigé en 0.2.7 : avec `--batch`, une
  conversation restaurée du cache, puis remplacée par celle qu'un créneau rend, pouvait être remise
  de côté avec la mémoire de la première. Vérifié le 2026-10-27 dans le journal du moteur
  (`~/.local/state/strata/launch/flash-next.engine.log`, toutes les mises en route depuis le
  2026-10-24) : le cache ne met des conversations de côté qu'à partir du 2026-10-27 à 06 h 28 ; 11
  mises de côté réutilisent une mémoire restaurée, chacune trois ou quatre lignes après la
  restauration de la même conversation, sans créneau rendu entre les deux. Le cas du ticket
  n'apparaît pas.
