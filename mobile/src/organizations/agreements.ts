import { apiRequest } from '@/src/api/client';
export type AgreementAction = { action: string; party: string };
export type Agreement = { id: number; roster_entry_id: number; organization_id: number; organization_name: string;
  talent_name: string; kind: string; status: string; title: string; terms: string; revision: number; end_round: number; ending_reason?: string | null;
  amount: string | null; currency: string; starts_on: string | null; ends_on: string | null;
  destination_id: number | null; destination_name: string | null; destination_tag: string; destination_roster: string;
  roster_snapshot: { name: string; roster: string; tag: string }; can_revise: boolean; actions: AgreementAction[];
  consents: { party: string; actor_name: string; purpose: string; revision: number; round: number }[] };
export type AgreementChoice = { id: number; organization_id: number; organization_name: string; name: string; tag: string; roster: string };
export type AgreementHistory = { id: number; action: string; actor_name: string; revision: number; reason: string; created_at: string; snapshot: { terms?: string } };
export const consentActions = new Set(['SUBMIT', 'ACCEPT', 'REQUEST_END', 'ACCEPT_END']);
export const reasonActions = new Set(['DECLINE', 'WITHDRAW', 'REQUEST_END', 'DECLINE_END']);
export const actionLabels: Record<string, string> = { SUBMIT: 'Submit and consent', ACCEPT: 'Accept terms', DECLINE: 'Decline',
  WITHDRAW: 'Withdraw', REQUEST_END: 'Request mutual ending', ACCEPT_END: 'Agree to end', DECLINE_END: 'Keep agreement active' };
export function agreementAction(row: Agreement, action: AgreementAction, consent: boolean, reason: string) {
  return apiRequest<Agreement>(`organizations/agreements/${row.id}/`, { method: 'POST', body: { ...action,
    expected_revision: row.revision, expected_end_round: row.end_round, consent, reason } });
}
