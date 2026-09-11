// The typed HTTP surface. Every fetch in this app goes through this file.
// Route shapes are frozen by DP-API §3.4; nothing here invents an endpoint.

export type FixtureClip = {
  id: string;
  path: string;
  label: "nominal" | "warning" | "failure";
  onset_frame: number | null;
  frames: number;
  notes: string;
  ok: boolean;
};

export type StartRunRequest = {
  fixture_id?: string;
  source?: string;
  backend?: "cool" | "baseline";
  replay?: boolean;
  sample_every_n?: number;
  max_frames?: number;
};

export type StartRunResponse = { run_id: string; trace_id: string; stream: string };

export type Health = {
  status: "ok" | "degraded";
  build_marker: string;
  opencv_version: string;
  cool_version: string | null;
  arch: string;
  backend: string;
  evidence: { backend: "s3" | "local"; bucket: string | null; writable: boolean };
  uptime_s: number;
};

export type ToolManifestEntry = {
  name: string;
  description: string;
  input_schema: unknown;
  output_key: string;
};

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function checked(res: Response): Promise<unknown> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as Record<string, unknown>).detail)
        : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return body;
}

export async function getHealth(): Promise<Health> {
  const res = await fetch("/healthz");
  return (await checked(res)) as Health;
}

export async function getFixtures(): Promise<{ synthetic: boolean; clips: FixtureClip[] }> {
  const res = await fetch("/api/fixtures");
  return (await checked(res)) as { synthetic: boolean; clips: FixtureClip[] };
}

export async function getTools(): Promise<ToolManifestEntry[]> {
  const res = await fetch("/api/tools");
  return (await checked(res)) as ToolManifestEntry[];
}

export async function startRun(body: StartRunRequest): Promise<StartRunResponse> {
  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await checked(res)) as StartRunResponse;
}

export async function uploadRun(file: File): Promise<StartRunResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/runs/upload", { method: "POST", body: form });
  return (await checked(res)) as StartRunResponse;
}

export async function approve(runId: string, approvalId: string, approved: boolean): Promise<void> {
  const res = await fetch(`/api/runs/${runId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_id: approvalId, approved }),
  });
  await checked(res);
}
