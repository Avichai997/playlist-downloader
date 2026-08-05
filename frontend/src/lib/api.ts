export type JobState = "queued" | "running" | "paused" | "done" | "failed" | "skipped";

export interface Job {
  id: number;
  playlist_id: string;
  video_id: string;
  state: JobState;
  priority: number;
  strategy: number;
  attempts: number;
  filepath: string | null;
  filesize: number | null;
  verified: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  number: number;
  title: string;
  duration: number | null;
  position: number | null;
  output_dir: string;
  max_height: number;
  total_count: number;
}

export interface Quality {
  height: number;
  label: string;
  vcodec: string;
  bytesPerSecond: number;
  estimatedTotalBytes: number;
  coverage: number;
}

export interface PlaylistInfo {
  id: string;
  url: string;
  title: string;
  uploader: string;
  count: number;
  newCount: number;
  totalDuration: number;
  outputDir: string;
}

export interface Stats {
  queued: number;
  running: number;
  paused: number;
  done: number;
  failed: number;
  skipped: number;
  total: number;
}

export interface Disk {
  free: number;
  total: number;
}

export interface Analysis {
  playlist: PlaylistInfo;
  qualities: Quality[];
  disk: Disk;
  stats: Stats;
}

export interface Settings {
  output_root: string;
  container: string;
  max_height: number;
  audio_only: boolean;
  audio_format: string;
  parallel_videos: number;
  fragments_per_video: number;
  rate_limit: string;
  night_window: string;
  numbering: string;
  pad_width: number;
  windows_safe_filenames: boolean;
  subtitles: boolean;
  sub_langs: string[];
  auto_subs: boolean;
  keep_sub_files: boolean;
  embed_thumbnail: boolean;
  embed_metadata: boolean;
  embed_chapters: boolean;
  sponsorblock: string;
  cookies_browser: string;
  verify_downloads: boolean;
  update_ytdlp_on_launch: boolean;
  watch_interval_hours: number;
}

export interface StartOptions {
  height?: number;
  container?: string;
  outputDir?: string;
  startFrom?: number | null;
  endAt?: number | null;
  redownload?: boolean;
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* keep the status-based message */
    }
    throw new ApiError(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/api/health"),
  engine: () => request<{ ytdlp: string; error?: string }>("/api/engine"),

  analyze: (url: string) => post<Analysis>("/api/analyze", { url }),

  listPlaylists: () => request<Record<string, unknown>[]>("/api/playlists"),

  listJobs: (playlistId: string, params: { state?: string; search?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.state) query.set("state", params.state);
    if (params.search) query.set("search", params.search);
    const suffix = query.toString() ? `?${query}` : "";
    return request<{ jobs: Job[]; stats: Stats }>(
      `/api/playlists/${encodeURIComponent(playlistId)}/jobs${suffix}`,
    );
  },

  start: (playlistId: string, options: StartOptions) =>
    post<{ selected: number; queued: number; stats: Stats }>(
      `/api/playlists/${encodeURIComponent(playlistId)}/start`,
      options,
    ),

  sync: (playlistId: string) =>
    post<{ found: number; queued: number; total: number }>(
      `/api/playlists/${encodeURIComponent(playlistId)}/sync`,
    ),

  pauseQueue: () => post<{ paused: boolean }>("/api/queue/pause"),
  resumeQueue: () => post<{ paused: boolean }>("/api/queue/resume"),
  retryFailed: (playlistId: string) =>
    post<{ requeued: number }>(`/api/queue/retry-failed?playlist_id=${encodeURIComponent(playlistId)}`),

  jobAction: (jobId: number, action: "pause" | "resume" | "skip" | "retry" | "prioritise") =>
    post<{ ok: boolean; job: Job }>(`/api/jobs/${jobId}/${action}`),

  attempts: (jobId: number) =>
    request<{ attempts: { strategy: string; ok: number; error: string | null; at: string }[] }>(
      `/api/jobs/${jobId}/attempts`,
    ),

  getSettings: () => request<Settings>("/api/settings"),
  putSettings: (changes: Partial<Settings>) =>
    request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(changes) }),

  reveal: (path: string) => post<{ ok: boolean }>("/api/reveal", { path }),

  pickFolder: async (initial?: string): Promise<string | null> => {
    if (window.pywebview?.api?.pick_folder) {
      const chosen = window.pywebview.api.pick_folder(initial ?? "");
      return chosen || null;
    }
    const result = await post<{ path: string | null }>("/api/pick-folder", {
      initial: initial ?? "",
    });
    return result.path;
  },

  setPlaylistOutput: (playlistId: string, outputDir: string) =>
    request<{ outputDir: string; disk: Disk }>(
      `/api/playlists/${encodeURIComponent(playlistId)}/output`,
      { method: "PUT", body: JSON.stringify({ outputDir }) },
    ),

  refreshQualities: (playlistId: string, container: string) =>
    post<{ qualities: Quality[]; container: string; disk: Disk }>(
      `/api/playlists/${encodeURIComponent(playlistId)}/qualities`,
      { container },
    ),
};

export type ServerEvent =
  | { type: "stats"; stats: Stats; paused: boolean; concurrency: number }
  | { type: "job_started"; jobId: number; number: number; title: string; videoId: string }
  | {
      type: "job_progress";
      jobId: number;
      status: string;
      percent: number | null;
      downloadedBytes: number | null;
      totalBytes: number | null;
      speed: number | null;
      eta: number | null;
    }
  | { type: "job_done"; jobId: number; filepath: string; filesize: number; title: string }
  | { type: "job_failed"; jobId: number; error: string }
  | { type: "job_state"; job: Job }
  | { type: "throttled"; concurrency: number; message: string }
  | { type: "analyze_stage"; stage: string }
  | { type: "analyze_progress"; done: number; total: number }
  | { type: "analyze_done"; playlist: PlaylistInfo; qualities: Quality[]; disk: Disk; stats: Stats }
  | { type: "queued"; playlistId: string; queued: number; stats: Stats }
  | { type: "synced"; playlistId: string; found: number; queued: number }
  | { type: "settings"; settings: Settings }
  | { type: "ytdlp_update"; ok: boolean; message: string; version?: string }
  | { type: "watch_error"; playlistId: string; message: string };

/** Keeps a WebSocket to the local server open, reconnecting if it drops. */
export function connectEvents(onEvent: (event: ServerEvent) => void): () => void {
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const open = () => {
    if (closed) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${scheme}://${location.host}/ws`);
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data as string) as ServerEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onclose = () => {
      if (!closed) retry = setTimeout(open, 1000);
    };
  };

  open();
  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    socket?.close();
  };
}
