import type {
  AuthConfig,
  AuthMe,
  GamesResponse,
  ScanResponse,
  ScanAllResponse,
  PropsResponse,
  DashboardResponse,
  TrackedBet,
  BetDashboardResponse,
  PendingPick,
  ModelHealthResponse,
  SportLower,
} from "./types";

let _accessToken: string | null = null;
let _onUnauthorized: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function setOnUnauthorized(cb: () => void) {
  _onUnauthorized = cb;
}

async function authFetch(url: string, opts: RequestInit = {}): Promise<Response> {
  const headers = new Headers(opts.headers);
  if (_accessToken) {
    headers.set("Authorization", `Bearer ${_accessToken}`);
  }
  if (opts.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, { ...opts, headers });

  if (res.status === 401) {
    _onUnauthorized?.();
    throw new Error("Unauthorized");
  }

  return res;
}

async function get<T>(url: string): Promise<T> {
  const res = await authFetch(url);
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.error) detail = errBody.error;
    } catch { /* non-JSON response */ }
    throw new Error(`GET ${url}: ${detail}`);
  }
  return res.json();
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await authFetch(url, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.error) detail = errBody.error;
    } catch { /* non-JSON response */ }
    throw new Error(`POST ${url}: ${detail}`);
  }
  return res.json();
}

async function del<T>(url: string): Promise<T> {
  const res = await authFetch(url, { method: "DELETE" });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.error) detail = errBody.error;
    } catch { /* non-JSON response */ }
    throw new Error(`DELETE ${url}: ${detail}`);
  }
  return res.json();
}

// ─── Auth ──────────────────────────────────────────────
export function fetchAuthConfig() {
  return get<AuthConfig>("/api/auth/config");
}

export function fetchAuthMe() {
  return get<AuthMe>("/api/auth/me");
}

// ─── Games ─────────────────────────────────────────────
export function fetchGames(sport: SportLower) {
  return get<GamesResponse>(`/api/games?sport=${sport}`);
}

// ─── Scan ──────────────────────────────────────────────
export function scanSport(sport: SportLower) {
  return post<ScanResponse>("/api/scan", { sport });
}

export function scanAllSports() {
  return post<ScanAllResponse>("/api/scan", { sport: "all" });
}

// ─── Props ─────────────────────────────────────────────
export function fetchProps(eventId: string, sport: SportLower) {
  return get<PropsResponse>(`/api/props?event_id=${eventId}&sport=${sport}`);
}

export function fetchTopProps(sport: SportLower) {
  return get<PropsResponse>(`/api/top-props?sport=${sport}`);
}

// ─── Dashboard ─────────────────────────────────────────
export function fetchDashboard(sport?: SportLower) {
  const qs = sport ? `?sport=${sport}` : "";
  return get<DashboardResponse>(`/api/dashboard${qs}`);
}

export function gradePredictions(sport?: SportLower) {
  return post<{ success: boolean; graded: number; summary: Record<string, number> }>(
    "/api/grade",
    sport ? { sport } : {}
  );
}

// ─── Bets ──────────────────────────────────────────────
export function saveBets(bets: unknown[]) {
  return post<{ success: boolean; saved_count: number; bet_ids: number[] }>(
    "/api/bets/save",
    { bets }
  );
}

export function fetchBets(sport?: SportLower, status?: string) {
  const params = new URLSearchParams();
  if (sport) params.set("sport", sport);
  if (status) params.set("status", status);
  const qs = params.toString();
  return get<{ success: boolean; bets: TrackedBet[] }>(`/api/bets${qs ? `?${qs}` : ""}`);
}

export function gradeBets() {
  return post<{ success: boolean; graded: number; wins: number; losses: number; pushes: number; not_final: number }>("/api/bets/grade");
}

export function fetchBetsDashboard(sport?: SportLower) {
  const qs = sport ? `?sport=${sport}` : "";
  return get<BetDashboardResponse>(`/api/bets/dashboard${qs}`);
}

export function deleteBet(betId: number) {
  return del<{ success: boolean }>(`/api/bets/${betId}`);
}

// ─── Pick Curation ─────────────────────────────────────
export function fetchPendingPicks(sport: SportLower) {
  return get<{ success: boolean; picks: PendingPick[] }>(`/api/picks/pending?sport=${sport}`);
}

export function approvePick(eventId: string, sport: SportLower, opts?: { notes?: string; lean_override?: string; confidence_override?: number }) {
  return post<{ success: boolean }>("/api/picks/approve", {
    event_id: eventId,
    sport,
    ...opts,
  });
}

export function rejectPick(eventId: string, sport: SportLower, notes?: string) {
  return post<{ success: boolean }>("/api/picks/reject", {
    event_id: eventId,
    sport,
    notes,
  });
}

export function approveAllPicks(sport: SportLower) {
  return post<{ success: boolean }>("/api/picks/approve-all", { sport });
}

export function fetchPicksStatus(sport: SportLower) {
  return get<{ success: boolean; reviewed: boolean }>(`/api/picks/status?sport=${sport}`);
}

// ─── Model Health ──────────────────────────────────────
export function fetchModelHealth() {
  return get<ModelHealthResponse>("/api/model-health");
}
