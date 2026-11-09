import type { CaseSummary } from "./types";

/** Minutes since midnight -> "21:30". */
export function clock(minute: number): string {
  const h = Math.floor(minute / 60) % 24;
  const m = minute % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Same rule as docs/art/portraits.csv: ASCII-fold, lower-case, non-alphanumerics -> "_" (e.g. "Arsène Lupin" -> "arsene_lupin"). */
export function portraitSlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export interface Lookup {
  people: Record<string, string>;
  rooms: Record<string, string>;
}

export function lookupFor(c: CaseSummary): Lookup {
  const people: Record<string, string> = { [c.victim.character_id]: c.victim.name };
  for (const s of c.suspects) people[s.character_id] = s.name;
  const rooms: Record<string, string> = {};
  for (const l of c.locations) rooms[l.location_id] = l.name;
  return { people, rooms };
}

/** Server text uses IDs and minutes; show names, rooms and clock times instead. */
export function humanize(text: string, lookup: Lookup): string {
  return text
    .replace(/\b(suspect_\d{2}|victim_\d{2})\b/g, (id) => lookup.people[id] ?? id)
    .replace(/\bloc_[a-z_]+\b/g, (id) => lookup.rooms[id] ?? id.replace(/^loc_/, "").replaceAll("_", " "))
    .replace(/\bminute (\d{3,4})\b/g, (_, m) => clock(Number(m)))
    .replace(/\b(1[0-4]\d{2})\b/g, (m) => (Number(m) >= 1080 && Number(m) <= 1440 ? clock(Number(m)) : m));
}

const FEATURE_TEXT: Record<string, string> = {
  motive_evidence: "motive records involving the victim",
  victim_relationship_records: "known relationship with the victim",
  access_evidence: "records placing them at the crime scene",
  opportunity_overlap: "could have reached the scene in time",
  scene_presence_in_window: "seen at the scene during the murder window",
  alibi_strength: "independent support for their alibi",
  claimed_corroboration_share: "says someone can vouch for them",
  claim_fact_conflicts: "statements contradicted by records",
  claim_claim_conflicts: "contradicted their own earlier statements",
  disagreement_count: "statements that clash with someone else's",
  unverified_claim_share: "statements nothing supports",
  interview_answers: "answers given to the detective",
  evasive_answer_share: "\"I don't remember\" answers",
  answers_refuted: "answers contradicted by records",
  evidence_coverage: "how much of the evidence has been found",
};

export function featureText(name: string): string {
  return FEATURE_TEXT[name] ?? name.replaceAll("_", " ");
}

export function percent(p: number): string {
  return `${Math.round(p * 100)}%`;
}
