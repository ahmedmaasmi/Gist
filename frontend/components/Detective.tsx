"use client";

import { useState } from "react";
import { Panel, Portrait } from "@/components/ui";
import { featureText, humanize, type Lookup, percent } from "@/lib/format";
import type { ResultsView, SessionView, VerdictView } from "@/lib/types";

export function Detective({ session, lookup, busy, verdict, results, evidenceText, onVerdict, onResults, onCounterfactual }: {
  session: SessionView; lookup: Lookup; busy: boolean; verdict: VerdictView | null; results: ResultsView | null;
  evidenceText: (id: string) => string; onVerdict: () => void; onResults: () => void;
  onCounterfactual: (evidenceId: string) => Promise<Record<string, number>>;
}) {
  const r = session.ranking;
  const ranked = Object.entries(r.probabilities).sort((a, b) => b[1] - a[1]);
  const [open, setOpen] = useState<string | null>(null);
  const [whatIf, setWhatIf] = useState<{ id: string; deltas: Record<string, number> } | null>(null);
  const expl = r.explanations.find((e) => e.suspect_id === open);

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Machine detective">
        <p className="text-sm text-dim">{r.label}</p>
        {r.fallback_used && <p role="status" className="mt-1 text-amber">{r.notice}</p>}
        <ul className="mt-2 space-y-2" aria-live="polite">
          {ranked.map(([sid, p], i) => {
            const before = session.previous_ranking?.[sid];
            const leading = sid === r.leading_suspect_id;
            return (
              <li key={sid}>
                <button className="w-full text-left" onClick={() => setOpen(open === sid ? null : sid)} aria-expanded={open === sid}>
                  <div className="flex items-center justify-between">
                    <span>{i + 1}. {lookup.people[sid]}{sid === session.your_character_id && " (you)"}{leading && <span className="ml-2 text-amber">◆ LEADING</span>}</span>
                    <span>{percent(p)}{before !== undefined && Math.abs(before - p) >= 0.005 && (
                      <span className="text-dim"> (was {percent(before)})</span>)}</span>
                  </div>
                  <div className="mt-1 h-3 border-2 border-edge" aria-hidden>
                    <div className={leading ? "h-full bg-amber" : "h-full bg-dim"} style={{ width: `${Math.max(2, p * 100)}%` }} />
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
        {r.abstain && <p className="mt-2 text-amber">⚠ {r.abstain_reason}</p>}
        <p className="mt-2 text-sm text-dim">Click a suspect to see why. Model {r.model_version}, features {r.feature_spec_version}.</p>
      </Panel>

      {expl && (
        <Panel title={`Why: ${lookup.people[expl.suspect_id]}`}>
          <p className="text-sm text-dim">What pushes this suspect's score up (+) or down (−). Evidence links open the record.</p>
          <ul className="mt-2 space-y-2">
            {Object.entries(expl.contributions).filter(([, v]) => Math.abs(v) >= 0.05)
              .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 6).map(([name, v]) => (
                <li key={name}>
                  <span className={v > 0 ? "text-amber" : "text-dim"}>{v > 0 ? "▲ +" : "▼ "}{v.toFixed(2)}</span> {featureText(name)}
                  <ul className="pl-4">
                    {(expl.evidence[name] ?? []).slice(0, 3).map((id) => (
                      <li key={id} className="text-sm">
                        <a className="underline" href={`#${id}`}>{humanize(evidenceText(id), lookup)}</a>{" "}
                        <button className="pixel-button secondary text-sm" disabled={busy}
                          onClick={async () => setWhatIf({ id, deltas: await onCounterfactual(id) })}>
                          without this?
                        </button>
                        {whatIf?.id === id && (
                          <span className="block text-dim">
                            Without it: {Object.entries(whatIf.deltas).filter(([, d]) => Math.abs(d) >= 0.01)
                              .map(([s, d]) => `${lookup.people[s]} ${d > 0 ? "+" : ""}${Math.round(d * 100)} pts`).join(", ") || "no real change"}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
          </ul>
        </Panel>
      )}

      <Panel title="Verdict">
        {!verdict ? (
          <button className="pixel-button" onClick={onVerdict} disabled={busy || session.status === "awaiting_your_answer"}>
            Ask for the verdict
          </button>
        ) : (
          <div>
            <p className="text-sm text-dim">{verdict.label}</p>
            {verdict.abstained ? (
              <p className="mt-2 text-xl text-amber">No accusation: {verdict.abstain_reason}</p>
            ) : (
              <div className="mt-2 flex items-center gap-3">
                <Portrait name={lookup.people[verdict.leading_suspect_id!]} size={64} />
                <p className="text-xl">The detective names <span className="text-amber">{lookup.people[verdict.leading_suspect_id!]}</span> ({percent(verdict.leading_probability ?? 0)})</p>
              </div>
            )}
            {verdict.supporting_evidence.length > 0 && (
              <><h3 className="mt-2 underline">Because</h3>
                <ul className="list-disc pl-5 text-sm">{verdict.supporting_evidence.map((e) => <li key={e.evidence_id}>{humanize(e.text, lookup)}</li>)}</ul></>
            )}
            <p className="mt-2 text-sm text-dim">Alternatives: {Object.entries(verdict.alternatives).map(([s, p]) => `${lookup.people[s]} ${percent(p)}`).join(", ")}</p>
            {!results && <button className="pixel-button mt-3" onClick={onResults} disabled={busy}>Reveal the truth</button>}
          </div>
        )}
        {results && (
          <div className="pixel-paper mt-3 p-3">
            <h3 className="font-[family-name:var(--font-title)] text-[11px] uppercase">The truth</h3>
            <p className="mt-1 text-xl">{results.solution}</p>
            <p className="mt-1">
              {results.machine_was_right === null ? "The detective abstained." : results.machine_was_right ? "The detective was right." : "The detective was wrong."}
            </p>
            {results.lies.length > 0 && (
              <><h4 className="mt-2 underline">Who lied</h4>
                <ul className="list-disc pl-5">{results.lies.map((l) => <li key={l.suspect_id + l.kind}>{lookup.people[l.suspect_id]}: {l.kind.replaceAll("_", " ").toLowerCase()}</li>)}</ul></>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
