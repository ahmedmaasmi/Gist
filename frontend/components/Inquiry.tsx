"use client";

import { useState } from "react";
import { Panel } from "@/components/ui";
import { clock, humanize, type Lookup } from "@/lib/format";
import type { CaseSummary, ClaimRequest, SessionView } from "@/lib/types";

export function Inquiry({ session, caseInfo, lookup, busy, onNext, onAnswer }: {
  session: SessionView; caseInfo: CaseSummary; lookup: Lookup; busy: boolean;
  onNext: () => void; onAnswer: (a: ClaimRequest) => void;
}) {
  const q = session.pending_question;
  return (
    <div className="flex flex-col gap-4">
      <Panel title={`Inquiry · move ${session.turn}/${session.budget}`}>
        <p aria-live="polite" className="text-dim">
          {session.status === "awaiting_your_answer" && "The detective is questioning you."}
          {session.status === "investigating" && "The detective is ready for its next move."}
          {session.status === "ready_for_verdict" && "The detective has used all its moves. Ask for the verdict."}
          {session.status === "verdict_given" && "The case is closed."}
        </p>
        {q?.for_you ? (
          <ClaimBuilder key={`${session.turn}-${q.minute}`} question={`Where were you at ${clock(q.minute ?? caseInfo.crime_window_start)}?`}
            caseInfo={caseInfo} you={session.your_character_id} busy={busy} onAnswer={onAnswer} />
        ) : (
          <button className="pixel-button mt-3" onClick={onNext} disabled={busy || session.status !== "investigating"}>
            Detective: next move
          </button>
        )}
      </Panel>

      <Panel title="Detective's moves">
        {session.detective_log.length === 0 && <p className="text-dim">No moves yet.</p>}
        <ol className="space-y-2">
          {[...session.detective_log].reverse().map((a) => (
            <li key={a.turn + a.action}>
              <span className="text-amber">#{a.turn}</span> {humanize(a.action, lookup)}
              {a.outcome && <span className="text-dim"> → {a.outcome.replaceAll("_", " ")}</span>}
              {a.alternatives.length > 0 && (
                <details className="text-dim">
                  <summary className="cursor-pointer">why this question</summary>
                  <ul className="pl-4">
                    {a.alternatives.map(([label, gain]) => (
                      <li key={label}>{humanize(label, lookup)}: expected uncertainty drop {gain.toFixed(3)}</li>
                    ))}
                  </ul>
                </details>
              )}
            </li>
          ))}
        </ol>
      </Panel>

      <Panel title="Consistency engine">
        {session.contradictions.length + session.disagreements.length === 0 && <p className="text-dim">No contradictions found yet.</p>}
        <ul className="space-y-2">
          {session.contradictions.map((f) => (
            <li key={f.flag_id}><span className="border-2 border-stamp-red px-1 text-stamp-red">CONTRADICTION</span>{" "}
              {lookup.people[f.suspect_id]}: {humanize(f.explanation, lookup)}</li>
          ))}
          {session.disagreements.map((d) => (
            <li key={d.disagreement_id}><span className="border-2 border-amber px-1 text-amber">DISAGREEMENT</span>{" "}
              {humanize(d.explanation, lookup)}</li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-dim">A contradiction shows an inconsistency, not guilt: innocent people misremember and hide unrelated secrets.</p>
      </Panel>
    </div>
  );
}

function ClaimBuilder({ question, caseInfo, you, busy, onAnswer }: {
  question: string; caseInfo: CaseSummary; you: string; busy: boolean; onAnswer: (a: ClaimRequest) => void;
}) {
  const [room, setRoom] = useState(caseInfo.locations[0]?.location_id ?? "");
  const [seen, setSeen] = useState<string[]>([]);
  const [forgot, setForgot] = useState(false);
  const [vouch, setVouch] = useState(false);
  const [text, setText] = useState("");
  const people = [caseInfo.victim, ...caseInfo.suspects].filter((p) => p.character_id !== you);
  return (
    <form className="mt-3 flex flex-col gap-2" onSubmit={(e) => {
      e.preventDefault();
      onAnswer(forgot ? { dont_remember: true, free_text: text || null }
        : { location_id: room, observed_character_ids: seen, has_corroboration: vouch, free_text: text || null });
    }}>
      <p className="text-xl text-amber">“{question}”</p>
      <label className="flex flex-col">Where were you?
        <select className="border-2 border-edge bg-desk p-1" value={room} disabled={forgot} onChange={(e) => setRoom(e.target.value)}>
          {caseInfo.locations.map((l) => <option key={l.location_id} value={l.location_id}>{l.name}</option>)}
        </select>
      </label>
      <fieldset disabled={forgot}>
        <legend>Who did you see there?</legend>
        <div className="flex flex-wrap gap-x-4">
          {people.map((p) => (
            <label key={p.character_id}><input type="checkbox" checked={seen.includes(p.character_id)}
              onChange={(e) => setSeen(e.target.checked ? [...seen, p.character_id] : seen.filter((x) => x !== p.character_id))} /> {p.name}</label>
          ))}
        </div>
      </fieldset>
      <label><input type="checkbox" checked={vouch} disabled={forgot} onChange={(e) => setVouch(e.target.checked)} /> Someone can vouch for me</label>
      <label><input type="checkbox" checked={forgot} onChange={(e) => setForgot(e.target.checked)} /> “I don’t remember.”</label>
      <label className="flex flex-col">Anything to add? (optional, not analysed)
        <input className="border-2 border-edge bg-desk p-1" maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <button className="pixel-button self-start" type="submit" disabled={busy}>Answer</button>
    </form>
  );
}
