"use client";

import { Portrait, Stamp } from "@/components/ui";
import { clock, humanize, type Lookup } from "@/lib/format";
import type { CaseSummary, PlayerBrief, SessionView } from "@/lib/types";

export function Dossier({ brief, session, caseInfo, lookup }: {
  brief: PlayerBrief; session: SessionView; caseInfo: CaseSummary; lookup: Lookup;
}) {
  const window = (m: number) => m >= caseInfo.crime_window_start - 30 && m <= caseInfo.crime_window_end + 30;
  return (
    <div className="flex flex-col gap-4">
      <section className="pixel-paper p-3" aria-label="Your case file">
        <h2 className="font-[family-name:var(--font-title)] text-[11px] uppercase">Case file: {caseInfo.case_id}</h2>
        <div className="mt-2 flex gap-3">
          <Portrait name={brief.character.name} size={88} />
          <div>
            <p className="text-2xl">{brief.character.name}</p>
            <p>{brief.character.occupation}</p>
            <p className={`mt-1 inline-block border-2 px-1 uppercase ${brief.you_are_the_culprit ? "border-stamp-red text-stamp-red" : "border-stamp-green text-stamp-green"}`}>
              {brief.you_are_the_culprit ? "You are the culprit" : "You are innocent"}
            </p>
          </div>
        </div>
        <h3 className="mt-3 underline">Where you really were (around the murder)</h3>
        <ul>
          {brief.where_you_really_were.filter((e) => window(e.minute)).map((e) => (
            <li key={`${e.minute}-${e.location_id}`}>{clock(e.minute)} · {lookup.rooms[e.location_id] ?? e.location_id}</li>
          ))}
        </ul>
        {brief.your_secrets.length > 0 && (
          <>
            <h3 className="mt-2 underline">What you are hiding</h3>
            <ul className="list-disc pl-5">{brief.your_secrets.map((s) => <li key={s}>{s}</li>)}</ul>
          </>
        )}
        {brief.your_statement_so_far && (
          <p className="mt-2"><span className="underline">You already told the police:</span> “{humanize(brief.your_statement_so_far, lookup)}”</p>
        )}
      </section>

      <section className="pixel-panel p-3" aria-label="Evidence found">
        <h2 className="mb-2 font-[family-name:var(--font-title)] text-[11px] text-amber uppercase">Evidence found ({session.facts.length})</h2>
        <ul className="max-h-72 space-y-1 overflow-y-auto pr-1">
          {session.facts.map((f) => (
            <li key={f.fact_id} id={f.fact_id}>
              {humanize(f.description, lookup)}
              <span className="text-dim"> ({f.provenance.toLowerCase()}, reliability {f.reliability.toFixed(2)})</span>
              <Stamp status={f.status} />
            </li>
          ))}
        </ul>
      </section>

      <section className="pixel-panel p-3" aria-label="Statements">
        <h2 className="mb-2 font-[family-name:var(--font-title)] text-[11px] text-amber uppercase">Statements ({session.claims.length})</h2>
        <ul className="max-h-60 space-y-1 overflow-y-auto pr-1">
          {session.claims.map((c) => (
            <li key={c.claim_id} id={c.claim_id}>
              <span className="text-amber">{lookup.people[c.speaker_id] ?? c.speaker_id}:</span>{" "}
              “{humanize(c.free_text ?? "", lookup)}”<Stamp status={c.status} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
