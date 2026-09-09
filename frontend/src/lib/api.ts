// All API calls go through this. Handles CSRF automatically.

const BASE = "";

async function getCsrf(): Promise<string> {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  if (match) return match[1];
  // Fetch a page to get the cookie set
  await fetch("/api/auth/me/", { credentials: "include" });
  const m2 = document.cookie.match(/csrftoken=([^;]+)/);
  return m2 ? m2[1] : "";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") {
    headers["X-CSRFToken"] = await getCsrf();
  }
  const res = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail || err.error || "Request failed"), { status: res.status, data: err });
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
};

// Auth
export const authApi = {
  login: (username: string, password: string) =>
    api.post<User>("/api/auth/login/", { username, password }),
  logout: () => api.post("/api/auth/logout/"),
  me: () => api.get<User>("/api/auth/me/"),
};

// Ingest
export const ingestApi = {
  items: (state?: string) =>
    api.get<RawItem[]>(`/api/ingest/items/${state ? `?state=${state}` : ""}`),
  sources: () => api.get<Source[]>("/api/ingest/sources/"),
  screenshot: async (file: File) => {
    const csrf = await getCsrf();
    const fd = new FormData();
    fd.append("image", file);
    const res = await fetch("/api/ingest/screenshot/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": csrf },
      body: fd,
    });
    if (!res.ok) throw new Error("Screenshot upload failed");
    return res.json() as Promise<{ headline: string; body: string; llm_available: boolean }>;
  },
  manual: (data: { headline: string; body: string; source_slug: string; url?: string }) =>
    api.post<RawItem>("/api/ingest/manual/", data),
};

// Desk
export const deskApi = {
  stories: (status?: string) =>
    api.get<Story[]>(`/api/desk/stories/${status ? `?status=${status}` : ""}`),
  story: (id: number) => api.get<StoryDetail>(`/api/desk/stories/${id}/`),
  claim: (id: number) => api.post<Story>(`/api/desk/stories/${id}/claim/`),
  revise: (id: number, data: { headline: string; body: string; subject?: string; change_note?: string }) =>
    api.post(`/api/desk/stories/${id}/revise/`, data),
  submit: (id: number) => api.post<Story>(`/api/desk/stories/${id}/submit/`),
  publish: (id: number) => api.post(`/api/desk/stories/${id}/publish/`),
  correct: (id: number, data: { headline: string; body: string; change_note: string }) =>
    api.post(`/api/desk/stories/${id}/correct/`, data),
  merge: (id: number, into_story_id: number, reason: string) =>
    api.post(`/api/desk/stories/${id}/merge/`, { into_story_id, reason }),
  spike: (id: number) => api.post<Story>(`/api/desk/stories/${id}/spike/`),
  detach: (id: number, item_id: number) =>
    api.post(`/api/desk/stories/${id}/detach/`, { item_id }),
  cluster: () => api.post<ClusterResult>("/api/desk/cluster/"),
  published: (slug: string) => api.get<StoryDetail>(`/api/desk/published/${slug}/`),
  audit: () => api.get<AuditEvent[]>("/api/desk/audit/"),
};

// Analytics
export const analyticsApi = {
  dashboard: (date?: string) =>
    api.get<DashboardData>(`/api/analytics/dashboard/${date ? `?date=${date}` : ""}`),
};

// Types
export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "REPORTER" | "EDITOR" | "DESK_HEAD";
}

export interface Source {
  id: number;
  slug: string;
  name: string;
  kind: string;
  handle: string;
  trust_tier: number;
}

export interface RawItem {
  id: number;
  source: Source;
  external_id: string;
  headline: string;
  body: string;
  url: string;
  published_at: string | null;
  received_at: string;
  ingest_method: string;
  state: string;
  created_at: string;
}

export interface BriefRevision {
  id: number;
  version: number;
  headline: string;
  body: string;
  subject: string;
  author: User | null;
  kind: string;
  change_note: string;
  model: string;
  created_at: string;
}

export interface Publication {
  id: number;
  revision: BriefRevision;
  published_by: User;
  published_at: string;
  version_no: number;
  status: "LIVE" | "SUPERSEDED" | "CORRECTED";
}

export interface Story {
  id: number;
  slug: string;
  status: string;
  subject: string;
  assigned_to: User | null;
  cluster_confidence: number | null;
  clustered_by: string;
  latest_headline: string;
  item_count: number;
  first_item_received_at: string | null;
  created_at: string;
  claimed_at: string | null;
  submitted_at: string | null;
  first_published_at: string | null;
}

export interface StoryItem {
  id: number;
  item: RawItem;
  similarity_score: number | null;
  attached_at: string;
  detached_at: string | null;
}

export interface StoryDetail extends Story {
  revisions: BriefRevision[];
  story_items: StoryItem[];
  publications: Publication[];
}

export interface ClusterResult {
  stories_created: number;
  items_clustered: number;
  suggestions: { left: string; right: string; score: number; reason: string; confident: boolean }[];
}

export interface AuditEvent {
  id: number;
  actor: User | null;
  verb: string;
  target_type: string;
  target_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DashboardData {
  date: string;
  published_count: number;
  by_subject: Record<string, number>;
  dwell: { median_minutes: number | null; p90_minutes: number | null; slowest: { id: number; subject: string; dwell_minutes: number } | null };
  stages: { ingest_to_claim_median_min: number | null; claim_to_submit_median_min: number | null; submit_to_publish_median_min: number | null };
  rewrite_rate_pct: number | null;
  dedup: { items_in: number; briefs_out: number; saved: number };
}
