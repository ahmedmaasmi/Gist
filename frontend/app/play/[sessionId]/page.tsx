"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { Detective } from "@/components/Detective";
import { Dossier } from "@/components/Dossier";
import { Inquiry } from "@/components/Inquiry";
import { api } from "@/lib/api";
import { lookupFor } from "@/lib/format";
import type { CaseSummary, ClaimRequest, PlayerBrief, ResultsView, SessionView, VerdictView } from "@/lib/types";

export default function Play({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const [session, setSession] = useState<SessionView | null>(null);
  const [brief, setBrief] = useState<PlayerBrief | null>(null);
  const [caseInfo, setCaseInfo] = useState<CaseSummary | null>(null);
  const [verdict, setVerdict] = useState<VerdictView | null>(null);
  const [results, setResults] = useState<ResultsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.session(sessionId), api.brief(sessionId), api.caseOf(sessionId)])
      .then(([s, b, c]) => { setSession(s); setBrief(b); setCaseInfo(c); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [sessionId]);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const lookup = useMemo(() => (caseInfo ? lookupFor(caseInfo) : { people: {}, rooms: {} }), [caseInfo]);
  const evidenceText = useCallback((id: string) => {
    const f = session?.facts.find((x) => x.fact_id === id);
    if (f) return f.description;
    const c = session?.claims.find((x) => x.claim_id === id);
    return c ? `${lookup.people[c.speaker_id] ?? c.speaker_id}: “${c.free_text ?? ""}”` : id;
  }, [session, lookup]);

  if (error && !session) return <main className="p-6" role="alert">Could not load this game: {error}. <Link className="underline" href="/">Back</Link></main>;
  if (!session || !brief || !caseInfo) return <main className="p-6">Opening the case file…</main>;

  return (
    <main className="mx-auto max-w-[1400px] px-4 py-4">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-[family-name:var(--font-title)] text-base text-amber">{caseInfo.title}</h1>
        <Link className="underline" href="/">All cases</Link>
      </header>
      <p className="mb-4 text-dim">{caseInfo.synopsis}</p>
      {error && <p role="alert" className="mb-3 text-stamp-red">{error}</p>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Dossier brief={brief} session={session} caseInfo={caseInfo} lookup={lookup} />
        <Inquiry session={session} caseInfo={caseInfo} lookup={lookup} busy={busy}
          onNext={() => run(() => api.nextQuestion(sessionId)).then((s) => s && setSession(s))}
          onAnswer={(a: ClaimRequest) => run(() => api.answer(sessionId, a)).then((s) => s && setSession(s))} />
        <Detective session={session} lookup={lookup} busy={busy} verdict={verdict} results={results} evidenceText={evidenceText}
          onVerdict={() => run(() => api.verdict(sessionId)).then(async (v) => {
            if (v) { setVerdict(v); setSession(await api.session(sessionId)); }
          })}
          onResults={() => run(() => api.results(sessionId)).then((r) => r && setResults(r))}
          onCounterfactual={async (id) => (await run(() => api.counterfactual(sessionId, id))) ?? {}} />
      </div>
    </main>
  );
}
