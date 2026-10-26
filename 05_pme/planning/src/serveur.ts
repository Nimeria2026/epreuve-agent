import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { Intervention } from "@poa/commun/contrats/intervention";
import type { Technicien } from "@poa/commun/contrats/technicien";
import { chargerPersonne } from "@poa/commun/droits";
import { ErreurOutil } from "@poa/commun/erreurs";
import { ecartsContrat } from "@poa/commun/validation";
import { parse } from "yaml";
import { z } from "zod";

/** Où se trouve l'état de la PME, et pour qui l'agent travaille. */
export interface OptionsPlanning {
  readonly etat: string;
  readonly pour: string;
}

/** Droits qui ouvrent la lecture du planning. */
export const DROITS_LECTURE = ["planifier", "lire_planning", "acces_clients", "acces_direction"] as const;
/** Droit qui permet de planifier, déplacer et annuler. */
export const DROIT_ECRITURE = "planifier";

const NATURES = ["visite_annuelle", "depannage", "installation", "mise_en_service"] as const;
const COMPETENCES = ["chaudiere_gaz", "chaudiere_fioul", "pompe_a_chaleur", "climatisation", "ventilation"] as const;
const CODE_CLIENT = /^c-\d{4}$/u;
const NUMERO = /^INT-\d{4}-\d{4}$/u;
const JOUR = /^(\d{4})-(\d{2})-(\d{2})$/u;
const INSTANT = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:\d{2})?$/u;
const PAS_MINUTES = 30;
const CRENEAUX_MAX = 12;
/** Jours parcourus au plus par une recherche de créneaux. Sans borne, une durée qui ne tient dans
 * aucune plage, cherchée jusqu'en 9999, bouclait jour par jour jusqu'au délai du relais et finissait
 * en erreur technique (relecture de la tranche 5, B8). Dix ans : une recherche qui trouvait ses
 * créneaux avant ne change pas. */
const JOURS_PARCOURUS_MAX = 3660;
const NOMS_JOURS = ["", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

/** Heures d'intervention de la PME (planning/horaires.yaml de l'état). */
export interface Horaires {
  readonly jours: ReadonlySet<number>; // 1 = lundi
  readonly plages: readonly (readonly [number, number])[]; // minutes depuis minuit, heure de Paris
  readonly feries: ReadonlySet<string>; // AAAA-MM-JJ
}

// --- Heure de Paris ------------------------------------------------------------------------

const PARIS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  weekday: "short",
});
const JOURS_ANGLAIS: Record<string, number> = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 };

/** Date, minute du jour et jour de la semaine d'un instant, à l'heure de Paris. */
export function heureDeParis(instant: number): { date: string; minutes: number; jour: number; decalage: number } {
  const parts = Object.fromEntries(PARIS.formatToParts(new Date(instant)).map((p) => [p.type, p.value]));
  const [a, mo, j, h, mi, s] = [parts.year, parts.month, parts.day, parts.hour, parts.minute, parts.second].map(Number);
  const commeUtc = Date.UTC(a ?? 0, (mo ?? 1) - 1, j ?? 1, h ?? 0, mi ?? 0, s ?? 0);
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    minutes: (h ?? 0) * 60 + (mi ?? 0),
    jour: JOURS_ANGLAIS[parts.weekday ?? ""] ?? 0,
    decalage: Math.round((commeUtc - instant) / 60000),
  };
}

/** L'instant d'une date et d'une minute du jour, à l'heure de Paris. */
export function instantDeParis(date: string, minutes: number): number {
  const m = JOUR.exec(date);
  if (m === null) {
    throw new ErreurOutil(`date invalide : ${date} (format AAAA-MM-JJ)`);
  }
  const naif = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 0, minutes);
  let instant = naif - heureDeParis(naif).decalage * 60000;
  instant = naif - heureDeParis(instant).decalage * 60000;
  return instant;
}

/** Un instant au format RFC 3339, à l'heure de Paris, par exemple 2026-11-05T14:00:00+01:00. */
export function rfc3339(instant: number): string {
  const p = heureDeParis(instant);
  const signe = p.decalage >= 0 ? "+" : "-";
  const d = Math.abs(p.decalage);
  const hm = `${String(Math.floor(p.minutes / 60)).padStart(2, "0")}:${String(p.minutes % 60).padStart(2, "0")}`;
  return `${p.date}T${hm}:00${signe}${String(Math.floor(d / 60)).padStart(2, "0")}:${String(d % 60).padStart(2, "0")}`;
}

/** Lit une heure donnée par l'agent : RFC 3339, ou heure de Paris si aucun décalage n'est écrit. */
export function lireInstant(texte: string): number {
  const m = INSTANT.exec(texte.trim());
  if (m === null) {
    throw new ErreurOutil(`heure invalide : ${texte} (par exemple 2026-11-05T14:00:00+01:00)`);
  }
  const date = `${m[1]}-${m[2]}-${m[3]}`;
  const minutes = Number(m[4]) * 60 + Number(m[5]);
  if (m[7] === undefined) {
    return instantDeParis(date, minutes);
  }
  const instant = Date.parse(`${date}T${m[4]}:${m[5]}:${m[6] ?? "00"}${m[7]}`);
  if (Number.isNaN(instant)) {
    throw new ErreurOutil(`heure invalide : ${texte}`);
  }
  return instant;
}

function hhmm(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

function jourSuivant(date: string): string {
  const m = JOUR.exec(date);
  if (m === null) {
    throw new ErreurOutil(`date invalide : ${date}`);
  }
  const t = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + 1));
  return t.toISOString().slice(0, 10);
}

// --- Données -------------------------------------------------------------------------------

function reponse(texte: string): CallToolResult {
  return { content: [{ type: "text", text: texte }] };
}

function avecRefus(action: () => string): CallToolResult {
  try {
    return reponse(action());
  } catch (erreur) {
    if (erreur instanceof ErreurOutil) {
      return { content: [{ type: "text", text: erreur.message }], isError: true };
    }
    throw erreur;
  }
}

function lireContrat<T>(contrat: string, chemin: string): T {
  const donnees: unknown = JSON.parse(readFileSync(chemin, "utf-8"));
  const ecarts = ecartsContrat(contrat, donnees);
  if (ecarts.length > 0) {
    throw new Error(`${contrat} hors contrat : ${chemin}\n${ecarts.join("\n")}`);
  }
  return donnees as T;
}

function lireTous<T>(repertoire: string, contrat: string): T[] {
  if (!existsSync(repertoire)) {
    return [];
  }
  return readdirSync(repertoire)
    .filter((nom) => nom.endsWith(".json"))
    .sort()
    .map((nom) => lireContrat<T>(contrat, path.join(repertoire, nom)));
}

/** Lit planning/horaires.yaml : jours ouvrés, plages d'intervention, jours fériés. */
export function lireHoraires(etat: string): Horaires {
  const brut: unknown = parse(readFileSync(path.join(etat, "planning", "horaires.yaml"), "utf-8"));
  const objet = typeof brut === "object" && brut !== null ? (brut as Record<string, unknown>) : {};
  const jours = Array.isArray(objet.jours) ? objet.jours.filter((j): j is number => typeof j === "number") : [];
  const plages = (Array.isArray(objet.plages) ? objet.plages : []).map((p) => {
    const m = typeof p === "string" ? /^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/u.exec(p) : null;
    if (m === null) {
      throw new Error(`plage illisible dans planning/horaires.yaml : ${String(p)}`);
    }
    return [Number(m[1]) * 60 + Number(m[2]), Number(m[3]) * 60 + Number(m[4])] as const;
  });
  const feries = Array.isArray(objet.feries) ? objet.feries.filter((f): f is string => typeof f === "string") : [];
  if (jours.length === 0 || plages.length === 0) {
    throw new Error("planning/horaires.yaml : jours ou plages absents");
  }
  return { jours: new Set(jours), plages, feries: new Set(feries) };
}

function heureSimulee(etat: string): string {
  const horloge: unknown = parse(readFileSync(path.join(etat, "entreprise", "horloge.yaml"), "utf-8"));
  const debut = typeof horloge === "object" && horloge !== null && "debut" in horloge ? horloge.debut : undefined;
  if (typeof debut !== "string") {
    throw new Error("horloge simulée illisible");
  }
  return debut;
}

interface Periode {
  readonly debut: number;
  readonly fin: number;
}

/** Une liste de techniciens non vide et sans doublon, comme le contrat intervention la veut. */
function nonVide(ids: readonly string[]): [string, ...string[]] {
  const [premier, ...autres] = ids;
  if (premier === undefined || new Set(ids).size !== ids.length) {
    throw new ErreurOutil("au moins un technicien, sans doublon");
  }
  return [premier, ...autres];
}

function chevauche(a: Periode, b: Periode): boolean {
  return a.debut < b.fin && b.debut < a.fin;
}

// --- Serveur -------------------------------------------------------------------------------

/**
 * Serveur MCP du planning de la PME (étape 5). Il ne garde rien en mémoire : chaque technicien
 * est un fichier de <etat>/planning/techniciens/, chaque intervention un fichier de
 * <etat>/planning/interventions/, conformes aux contrats technicien et intervention ; les heures
 * d'intervention et les jours fériés sont dans <etat>/planning/horaires.yaml. Le logiciel refuse
 * un rendez-vous hors des heures, un jour férié ou en conflit ; il ne connaît pas le manuel :
 * qu'un apprenti parte seul, par exemple, il le laisse faire.
 */
export function creerServeurPlanning(options: OptionsPlanning): McpServer {
  const { etat } = options;
  const personne = chargerPersonne(etat, options.pour);
  const racine = path.join(etat, "planning");
  const horaires = (): Horaires => lireHoraires(etat);
  const techniciens = (): Technicien[] => lireTous<Technicien>(path.join(racine, "techniciens"), "technicien");
  const interventions = (): Intervention[] =>
    lireTous<Intervention>(path.join(racine, "interventions"), "intervention");

  function lire(): void {
    if (!DROITS_LECTURE.some((droit) => personne.droits.has(droit))) {
      throw new ErreurOutil(`accès refusé au planning pour ${personne.nom}`);
    }
  }

  function ecrire(): void {
    if (!personne.droits.has(DROIT_ECRITURE)) {
      throw new ErreurOutil(`${personne.nom} n'a pas le droit de modifier le planning`);
    }
  }

  function technicien(id: string): Technicien {
    const t = techniciens().find((x) => x.id === id);
    if (t === undefined) {
      throw new ErreurOutil(`technicien inconnu : ${id} (voir lister_techniciens)`);
    }
    return t;
  }

  function date(texte: string): string {
    if (!JOUR.test(texte)) {
      throw new ErreurOutil(`date invalide : ${texte} (format AAAA-MM-JJ)`);
    }
    return texte;
  }

  function periodesOccupees(id: string, sauf?: string): Periode[] {
    const t = technicien(id);
    const rdv = interventions()
      .filter((i) => i.statut === "planifiee" && i.techniciens.includes(id) && i.numero !== sauf)
      .map((i) => ({ debut: Date.parse(i.debut), fin: Date.parse(i.fin) }));
    const absences = t.indisponibilites.map((p) => ({ debut: Date.parse(p.debut), fin: Date.parse(p.fin) }));
    return [...rdv, ...absences];
  }

  /** Refuse un rendez-vous hors des heures d'intervention, un jour férié ou en conflit. */
  function verifierCreneau(ids: readonly string[], debut: number, duree: number, sauf?: string): Periode {
    if (!Number.isInteger(duree) || duree <= 0 || duree > 600) {
      throw new ErreurOutil(`durée invalide : ${duree} (en minutes, de 1 à 600)`);
    }
    const h = horaires();
    const local = heureDeParis(debut);
    if (!h.jours.has(local.jour)) {
      throw new ErreurOutil(`le ${NOMS_JOURS[local.jour]} ${local.date} n'est pas un jour d'intervention`);
    }
    if (h.feries.has(local.date)) {
      throw new ErreurOutil(`le ${local.date} est un jour férié`);
    }
    const plage = h.plages.find(([a, b]) => local.minutes >= a && local.minutes + duree <= b);
    if (plage === undefined) {
      const texte = h.plages.map(([a, b]) => `${hhmm(a)}-${hhmm(b)}`).join(", ");
      throw new ErreurOutil(
        `${hhmm(local.minutes)} pour ${duree} minutes sort des heures d'intervention (${texte}, heure de Paris)`,
      );
    }
    const voulu = { debut, fin: debut + duree * 60000 };
    for (const id of ids) {
      if (periodesOccupees(id, sauf).some((p) => chevauche(p, voulu))) {
        throw new ErreurOutil(`${technicien(id).nom} n'est pas libre le ${local.date} à ${hhmm(local.minutes)}`);
      }
    }
    return voulu;
  }

  function client(code: string): string {
    if (!CODE_CLIENT.test(code)) {
      throw new ErreurOutil(`code client invalide : ${code} (format c-0000)`);
    }
    if (!existsSync(path.join(etat, "dossiers", "clients", code, "fiche_client.yaml"))) {
      throw new ErreurOutil(`client inconnu : ${code}`);
    }
    return code;
  }

  function ecrireIntervention(intervention: Intervention): void {
    const ecarts = ecartsContrat("intervention", intervention);
    if (ecarts.length > 0) {
      throw new Error(`intervention hors contrat, non écrite : ${ecarts.join(" ; ")}`);
    }
    const chemin = path.join(racine, "interventions", `${intervention.numero}.json`);
    mkdirSync(path.dirname(chemin), { recursive: true });
    writeFileSync(chemin, `${JSON.stringify(intervention, null, 2)}\n`);
  }

  function ligne(i: Intervention): string {
    const debut = heureDeParis(Date.parse(i.debut));
    const fin = heureDeParis(Date.parse(i.fin));
    const statut = i.statut === "planifiee" ? "planifiée" : `annulée (${i.motif_annulation ?? "sans motif"})`;
    return [
      i.numero,
      `${debut.date} ${hhmm(debut.minutes)}-${hhmm(fin.minutes)}`,
      i.client,
      i.techniciens.join(", "),
      i.nature,
      i.objet,
      statut,
    ].join(" | ");
  }

  const serveur = new McpServer({ name: "pme-planning", version: "0.1.0" });

  serveur.registerTool(
    "lister_techniciens",
    {
      title: "Lister les techniciens",
      annotations: { readOnlyHint: true },
      description: "Les techniciens du planning, leurs compétences, et s'ils sont apprentis.",
      inputSchema: {},
    },
    () =>
      avecRefus(() => {
        lire();
        return techniciens()
          .map((t) => `${t.id} | ${t.nom} | ${t.competences.join(", ")}${t.apprenti ? " | apprenti" : ""}`)
          .join("\n");
      }),
  );

  serveur.registerTool(
    "consulter_planning",
    {
      title: "Consulter le planning",
      annotations: { readOnlyHint: true },
      description:
        "Les interventions et les indisponibilités entre deux dates incluses, heure de Paris, pour tous les techniciens ou pour un seul.",
      inputSchema: {
        du: z.string().describe("premier jour, AAAA-MM-JJ"),
        au: z.string().describe("dernier jour inclus, AAAA-MM-JJ"),
        technicien: z.string().optional().describe("identifiant d'un technicien, par exemple thomas.girard"),
      },
    },
    ({ du, au, technicien: id }) =>
      avecRefus(() => {
        lire();
        const periode = { debut: instantDeParis(date(du), 0), fin: instantDeParis(jourSuivant(date(au)), 0) };
        if (periode.fin <= periode.debut) {
          throw new ErreurOutil(`période vide : du ${du} au ${au}`);
        }
        if (id !== undefined) {
          technicien(id);
        }
        const rdv = interventions()
          .filter((i) => id === undefined || i.techniciens.includes(id))
          .filter((i) => chevauche({ debut: Date.parse(i.debut), fin: Date.parse(i.fin) }, periode))
          .sort((a, b) => Date.parse(a.debut) - Date.parse(b.debut) || a.numero.localeCompare(b.numero));
        const absences = techniciens()
          .filter((t) => id === undefined || t.id === id)
          .flatMap((t) =>
            t.indisponibilites
              .map((p) => ({ debut: Date.parse(p.debut), fin: Date.parse(p.fin) }))
              .filter((p) => chevauche(p, periode))
              .map((p) => `${t.id} indisponible du ${rfc3339(p.debut)} au ${rfc3339(p.fin)}`),
          );
        return [
          `Interventions du ${du} au ${au} :`,
          ...(rdv.length > 0 ? rdv.map(ligne) : ["(aucune)"]),
          "Indisponibilités :",
          ...(absences.length > 0 ? absences : ["(aucune)"]),
        ].join("\n");
      }),
  );

  serveur.registerTool(
    "chercher_creneaux",
    {
      title: "Chercher des créneaux libres",
      annotations: { readOnlyHint: true },
      description:
        "Les premiers créneaux libres d'une durée donnée, entre deux dates incluses, dans les heures d'intervention, par pas de 30 minutes.",
      inputSchema: {
        du: z.string().describe("premier jour, AAAA-MM-JJ"),
        au: z.string().describe("dernier jour inclus, AAAA-MM-JJ"),
        duree_minutes: z.number().describe("durée de l'intervention, en minutes"),
        competence: z.enum(COMPETENCES).optional().describe("compétence demandée"),
        technicien: z.string().optional().describe("un seul technicien"),
      },
    },
    ({ du, au, duree_minutes, competence, technicien: id }) =>
      avecRefus(() => {
        lire();
        date(du);
        date(au);
        if (!Number.isInteger(duree_minutes) || duree_minutes <= 0 || duree_minutes > 600) {
          throw new ErreurOutil(`durée invalide : ${duree_minutes} (en minutes, de 1 à 600)`);
        }
        const h = horaires();
        const candidats = techniciens()
          .filter((t) => id === undefined || t.id === id)
          .filter((t) => competence === undefined || t.competences.includes(competence));
        if (id !== undefined && candidats.length === 0) {
          technicien(id);
        }
        const trouves: string[] = [];
        let parcourus = 0;
        for (let jour = du; jour <= au && trouves.length < CRENEAUX_MAX; jour = jourSuivant(jour)) {
          if (++parcourus > JOURS_PARCOURUS_MAX) {
            throw new ErreurOutil(
              `recherche arrêtée au ${jour} : ${JOURS_PARCOURUS_MAX} jours parcourus, ${trouves.length} créneau(x) libre(s) ; resserrer la période`,
            );
          }
          const debutJour = heureDeParis(instantDeParis(jour, 12 * 60));
          if (!h.jours.has(debutJour.jour) || h.feries.has(jour)) {
            continue;
          }
          for (const [a, b] of h.plages) {
            for (let m = a; m + duree_minutes <= b && trouves.length < CRENEAUX_MAX; m += PAS_MINUTES) {
              const voulu = { debut: instantDeParis(jour, m), fin: instantDeParis(jour, m + duree_minutes) };
              for (const t of candidats) {
                if (trouves.length >= CRENEAUX_MAX) {
                  break;
                }
                if (!periodesOccupees(t.id).some((p) => chevauche(p, voulu))) {
                  const apprenti = t.apprenti ? " (apprenti)" : "";
                  trouves.push(`${jour} ${hhmm(m)}-${hhmm(m + duree_minutes)} | ${t.id}${apprenti}`);
                }
              }
            }
          }
        }
        return trouves.length > 0 ? trouves.join("\n") : "Aucun créneau libre sur cette période.";
      }),
  );

  serveur.registerTool(
    "planifier_intervention",
    {
      title: "Planifier une intervention",
      annotations: { readOnlyHint: false },
      description: "Planifie une intervention chez un client, avec un ou plusieurs techniciens.",
      inputSchema: {
        client: z.string().describe("code du client, par exemple c-0124"),
        techniciens: z.array(z.string()).describe('identifiants des techniciens, par exemple ["thomas.girard"]'),
        debut: z.string().describe("heure de début, par exemple 2026-11-05T14:00:00+01:00"),
        duree_minutes: z.number().describe("durée, en minutes"),
        nature: z.enum(NATURES).describe("nature de l'intervention"),
        objet: z.string().describe("ce qu'il y a à faire"),
      },
    },
    ({ client: code, techniciens: ids, debut, duree_minutes, nature, objet }) =>
      avecRefus(() => {
        ecrire();
        client(code);
        if (ids.length === 0 || new Set(ids).size !== ids.length) {
          throw new ErreurOutil("au moins un technicien, sans doublon");
        }
        for (const id of ids) {
          technicien(id);
        }
        if (objet.trim() === "") {
          throw new ErreurOutil("l'objet de l'intervention est obligatoire");
        }
        const p = verifierCreneau(ids, lireInstant(debut), duree_minutes);
        const annee = heureSimulee(etat).slice(0, 4);
        const numero = `INT-${annee}-${String(interventions().length + 1).padStart(4, "0")}`;
        ecrireIntervention({
          numero,
          client: code,
          techniciens: nonVide(ids),
          debut: rfc3339(p.debut),
          fin: rfc3339(p.fin),
          nature,
          objet: objet.trim(),
          statut: "planifiee",
          cree_par: personne.id,
        });
        const local = heureDeParis(p.debut);
        return `Intervention ${numero} planifiée le ${local.date} à ${hhmm(local.minutes)} chez ${code}, avec ${ids.join(", ")}`;
      }),
  );

  serveur.registerTool(
    "deplacer_intervention",
    {
      title: "Déplacer une intervention",
      annotations: { readOnlyHint: false },
      description:
        "Change l'heure d'une intervention planifiée, et ses techniciens si on les donne ; la durée reste la même.",
      inputSchema: {
        numero: z.string().describe("numéro de l'intervention, par exemple INT-2026-0012"),
        debut: z.string().describe("nouvelle heure de début, par exemple 2026-11-06T08:00:00+01:00"),
        techniciens: z.array(z.string()).optional().describe("nouveaux techniciens, sinon les mêmes"),
      },
    },
    ({ numero, debut, techniciens: ids }) =>
      avecRefus(() => {
        ecrire();
        if (!NUMERO.test(numero)) {
          throw new ErreurOutil(`numéro invalide : ${numero} (format INT-0000-0000)`);
        }
        const i = interventions().find((x) => x.numero === numero);
        if (i === undefined) {
          throw new ErreurOutil(`intervention inconnue : ${numero}`);
        }
        if (i.statut !== "planifiee") {
          throw new ErreurOutil(`l'intervention ${numero} est annulée`);
        }
        const nouveaux = ids ?? i.techniciens;
        if (nouveaux.length === 0 || new Set(nouveaux).size !== nouveaux.length) {
          throw new ErreurOutil("au moins un technicien, sans doublon");
        }
        for (const id of nouveaux) {
          technicien(id);
        }
        const duree = Math.round((Date.parse(i.fin) - Date.parse(i.debut)) / 60000);
        const p = verifierCreneau(nouveaux, lireInstant(debut), duree, numero);
        ecrireIntervention({ ...i, techniciens: nonVide(nouveaux), debut: rfc3339(p.debut), fin: rfc3339(p.fin) });
        const local = heureDeParis(p.debut);
        return `Intervention ${numero} déplacée au ${local.date} à ${hhmm(local.minutes)}, avec ${nouveaux.join(", ")}`;
      }),
  );

  serveur.registerTool(
    "annuler_intervention",
    {
      title: "Annuler une intervention",
      annotations: { readOnlyHint: false },
      description: "Annule une intervention planifiée ; elle reste au planning, avec son motif.",
      inputSchema: {
        numero: z.string().describe("numéro de l'intervention, par exemple INT-2026-0012"),
        motif: z.string().describe("motif de l'annulation"),
      },
    },
    ({ numero, motif }) =>
      avecRefus(() => {
        ecrire();
        const i = interventions().find((x) => x.numero === numero);
        if (i === undefined) {
          throw new ErreurOutil(`intervention inconnue : ${numero}`);
        }
        if (i.statut !== "planifiee") {
          throw new ErreurOutil(`l'intervention ${numero} est déjà annulée`);
        }
        if (motif.trim() === "") {
          throw new ErreurOutil("le motif de l'annulation est obligatoire");
        }
        ecrireIntervention({ ...i, statut: "annulee", motif_annulation: motif.trim() });
        return `Intervention ${numero} annulée`;
      }),
  );

  return serveur;
}
