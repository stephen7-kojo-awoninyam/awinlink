import { apiRequest } from '@/src/api/client';

export type TalentTag = { id: number; name: string; talent_details: string; tag: string; roster: string;
  status: string; talent_id: number | null; organization_id: number; organization_name: string; actions?: string[] };
export type Workspace = { id: number; name: string; can_manage: boolean };
export type RosterEvent = { id: number; action: string; reason: string; created_at: string };

export async function rosterPages<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let page = 1;
  for (;;) {
    // Keep requests relative to the API client; never forward auth to a next URL.
    const result = await apiRequest<{ results: T[]; next: string | null }>(`${path}${path.includes('?') ? '&' : '?'}page=${page}`);
    rows.push(...result.results);
    if (!result.next) return rows;
    page += 1;
  }
}

export function updateTag(id: number, action: string, username = '', reason = '') {
  return apiRequest<TalentTag>(`organizations/talent-tags/${id}/`, { method: 'POST', body: { action, username, reason } });
}
