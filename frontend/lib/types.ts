// Mirrors backend/app/api/schemas.py (the API contract). Nothing here can carry the hidden solution
// before the verdict: the backend never sends it.

export interface LocationView { location_id: string; name: string; restricted: boolean; x: number | null; y: number | null }
export interface CharacterView { character_id: string; name: string; occupation: string }
export interface CaseSummary {
  case_id: string; title: string; map_name: string; synopsis: string; victim: CharacterView;
  suspects: CharacterView[]; locations: LocationView[]; crime_location_id: string;
  crime_window_start: number; crime_window_end: number; role_variants: string[];
}
export interface PlayerBrief {
  character: CharacterView; role: string; you_are_the_culprit: boolean;
  where_you_really_were: { minute: number; location_id: string }[];
  your_secrets: string[]; your_statement_so_far: string | null;
}
export interface FactView {
  fact_id: string; description: string; subject_id: string | null; location_id: string | null; minute: number | null;
  category: string; provenance: string; reliability: number; status: string;
}
export interface ClaimView {
  claim_id: string; speaker_id: string; location_id: string | null; minute_start: number | null; minute_end: number | null;
  observed_character_ids: string[]; free_text: string | null; provenance: string; status: string; turn: number;
}
export interface ContradictionView { flag_id: string; type: string; suspect_id: string; claim_id: string; source_ids: string[]; explanation: string }
export interface DisagreementView { disagreement_id: string; suspect_ids: string[]; claim_ids: string[]; explanation: string }
export interface QuestionView { kind: string; suspect_id: string; minute: number | null; text: string; for_you: boolean }
export interface DetectiveAction { turn: number; action: string; outcome: string | null; alternatives: [string, number][] }
export interface SuspectExplanation {
  suspect_id: string; probability: number; contributions: Record<string, number>; baseline_score: number;
  evidence: Record<string, string[]>;
}
export interface RankingResult {
  label: string; probabilities: Record<string, number>; explanations: SuspectExplanation[];
  leading_suspect_id: string | null; abstain: boolean; abstain_reason: string | null;
  model_version: string; feature_spec_version: string; fallback_used: boolean; notice: string | null;
}
export interface SessionView {
  session_id: string; case_id: string; your_character_id: string; turn: number; budget: number; status: string;
  pending_question: QuestionView | null; facts: FactView[]; claims: ClaimView[];
  contradictions: ContradictionView[]; disagreements: DisagreementView[]; ranking: RankingResult;
  previous_ranking: Record<string, number> | null; detective_log: DetectiveAction[];
}
export interface SessionCreated { session: SessionView; case: CaseSummary; you: PlayerBrief }
export interface EvidenceItem { evidence_id: string; text: string }
export interface VerdictView {
  label: string; abstained: boolean; abstain_reason: string | null; leading_suspect_id: string | null;
  leading_probability: number | null; supporting_evidence: EvidenceItem[]; contradictions: ContradictionView[];
  alternatives: Record<string, number>; model_version: string;
}
export interface ResultsView {
  culprit_id: string; culprit_name: string; solution: string; machine_verdict: VerdictView;
  machine_was_right: boolean | null; your_role: string; lies: { suspect_id: string; kind: string; note: string }[];
}
export interface ClaimRequest {
  location_id?: string | null; dont_remember?: boolean; observed_character_ids?: string[];
  has_corroboration?: boolean; free_text?: string | null;
}
