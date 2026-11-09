"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { clock } from "@/lib/format";
import type { CaseSummary } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.cases().then(setCases).catch((e) => setError(String(e.message ?? e)));
  }, []);

  async function start(caseId: string, role: string) {
    setBusy(true);
    try {
      const created = await api.createSession(caseId, role);
      router.push(`/play/${created.session.session_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <h1 className="font-[family-name:var(--font-title)] text-xl text-amber">CaseMind</h1>
      <p className="mt-2 max-w-3xl text-dim">
        You are one of the suspects. A machine detective questions everyone, checks the records and estimates who did
        it. Play the culprit and try to stay hidden, or play an innocent and try not to look guilty.
      </p>
      <p className="mt-1 text-sm text-dim">
        Famous names are used as fictional characters; any guilt is decided by the simulation and is not historical.
      </p>
      {error && <p role="alert" className="mt-4 text-stamp-red">Could not reach the game server: {error}</p>}
      {!cases && !error && <p className="mt-4">Loading cases…</p>}
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {cases?.map((c) => (
          <Panel key={c.case_id} title={c.title}>
            <p>{c.synopsis}</p>
            <p className="mt-1 text-dim">
              Victim: {c.victim.name} · Window {clock(c.crime_window_start)}–{clock(c.crime_window_end)}
            </p>
            <p className="mt-1 text-dim">Suspects: {c.suspects.map((s) => s.name).join(", ")}</p>
            <div className="mt-3 flex flex-wrap gap-3">
              <button className="pixel-button" disabled={busy} onClick={() => start(c.case_id, "culprit")}>
                Play the culprit
              </button>
              <button className="pixel-button secondary" disabled={busy} onClick={() => start(c.case_id, "innocent")}>
                Play an innocent
              </button>
            </div>
          </Panel>
        ))}
      </div>
    </main>
  );
}
