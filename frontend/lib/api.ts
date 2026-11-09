import type { CaseSummary, ClaimRequest, PlayerBrief, ResultsView, SessionCreated, SessionView, VerdictView } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit & { idempotencyKey?: string }): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init?.idempotencyKey) headers["Idempotency-Key"] = init.idempotencyKey;
  const res = await fetch(`/api${path}`, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`);
  return body as T;
}

// One key per user action, so a double click or a retried request cannot act twice (PRD 13).
const key = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);

export const api = {
  cases: () => call<CaseSummary[]>("/cases"),
  createSession: (case_id: string, role: string) =>
    call<SessionCreated>("/sessions", { method: "POST", body: JSON.stringify({ case_id, role }) }),
  session: (id: string) => call<SessionView>(`/sessions/${id}`),
  brief: (id: string) => call<PlayerBrief>(`/sessions/${id}/you`),
  caseOf: (id: string) => call<CaseSummary>(`/sessions/${id}/case`),
  nextQuestion: (id: string) => call<SessionView>(`/sessions/${id}/next-question`, { method: "POST", idempotencyKey: key() }),
  answer: (id: string, body: ClaimRequest) =>
    call<SessionView>(`/sessions/${id}/claims`, { method: "POST", body: JSON.stringify(body), idempotencyKey: key() }),
  counterfactual: (id: string, evidenceId: string) =>
    call<Record<string, number>>(`/sessions/${id}/counterfactual?evidence_id=${encodeURIComponent(evidenceId)}`),
  verdict: (id: string) => call<VerdictView>(`/sessions/${id}/verdict`, { method: "POST", idempotencyKey: key() }),
  results: (id: string) => call<ResultsView>(`/sessions/${id}/results`),
};
