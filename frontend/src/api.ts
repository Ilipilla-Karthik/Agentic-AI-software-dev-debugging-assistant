import type {
  ProjectListItem,
  ProjectState,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function createProject(requirement: string): Promise<{ project_id: string; status: string; message: string }> {
  return http("/api/projects", { method: "POST", body: JSON.stringify({ requirement }) });
}

export function listProjects(): Promise<ProjectListItem[]> {
  return http("/api/projects");
}

export function getProject(id: string): Promise<ProjectState> {
  return http(`/api/projects/${id}`);
}

export function rerunProject(id: string): Promise<{ project_id: string; status: string }> {
  return http(`/api/projects/${id}/rerun`, { method: "POST" });
}

export function projectEventsUrl(id: string): string {
  return `${API_BASE}/api/projects/${id}/events`;
}

export function getMemory(id: string, agent?: string): Promise<Array<Record<string, unknown>>> {
  const q = agent ? `?agent=${encodeURIComponent(agent)}` : "";
  return http(`/api/projects/${id}/memory${q}`);
}