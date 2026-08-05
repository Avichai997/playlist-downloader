import { create } from "zustand";
import {
  api,
  type Analysis,
  type AppUpdateInfo,
  type Disk,
  type Job,
  type JobState,
  type PlaylistInfo,
  type Quality,
  type ServerEvent,
  type Settings,
  type Stats,
} from "@/lib/api";
import type { VideoContainer } from "@/lib/containers";

export interface LiveProgress {
  percent: number | null;
  downloadedBytes: number | null;
  totalBytes: number | null;
  speed: number | null;
  eta: number | null;
  status: string;
}

const EMPTY_STATS: Stats = {
  queued: 0,
  running: 0,
  paused: 0,
  done: 0,
  failed: 0,
  skipped: 0,
  total: 0,
};

interface AppState {
  playlist: PlaylistInfo | null;
  qualities: Quality[];
  disk: Disk | null;
  selectedHeight: number | null;
  selectedContainer: VideoContainer;

  jobs: Job[];
  progress: Record<number, LiveProgress>;
  stats: Stats;
  queuePaused: boolean;
  throttleNotice: string;

  settings: Settings | null;
  engineVersion: string;
  appVersion: string;
  appUpdate: AppUpdateInfo | null;

  analyzing: boolean;
  analyzeStage: string;
  analyzeDone: number;
  analyzeTotal: number;
  busy: boolean;

  filter: JobState | "all";
  search: string;

  bootstrap: () => Promise<void>;
  analyze: (url: string) => Promise<void>;
  selectHeight: (height: number) => void;
  setContainer: (container: VideoContainer) => Promise<void>;
  setOutputDir: (path: string) => Promise<void>;
  pickOutputFolder: () => Promise<void>;
  start: (options: { startFrom: number | null; endAt: number | null; redownload: boolean }) => Promise<number>;
  sync: () => Promise<{ found: number; queued: number }>;
  refreshJobs: () => Promise<void>;
  toggleQueue: () => Promise<void>;
  retryFailed: () => Promise<number>;
  jobAction: (jobId: number, action: "pause" | "resume" | "skip" | "retry") => Promise<void>;
  saveSettings: (changes: Partial<Settings>) => Promise<void>;
  setFilter: (filter: JobState | "all") => void;
  setSearch: (search: string) => void;
  clearPlaylist: () => void;
  dismissUpdate: () => void;
  handleEvent: (event: ServerEvent) => void;
}

export const useStore = create<AppState>((set, get) => ({
  playlist: null,
  qualities: [],
  disk: null,
  selectedHeight: null,
  selectedContainer: "mkv",

  jobs: [],
  progress: {},
  stats: EMPTY_STATS,
  queuePaused: false,
  throttleNotice: "",

  settings: null,
  engineVersion: "",
  appVersion: "",
  appUpdate: null,

  analyzing: false,
  analyzeStage: "",
  analyzeDone: 0,
  analyzeTotal: 0,
  busy: false,

  filter: "all",
  search: "",

  async bootstrap() {
    const [settings, engine, health, update] = await Promise.all([
      api.getSettings(),
      api.engine(),
      api.health(),
      api.checkUpdate(),
    ]);
    set({
      settings,
      engineVersion: engine.ytdlp,
      appVersion: health.version,
      appUpdate:
        update.available && update.version && update.url
          ? { version: update.version, url: update.url }
          : null,
      selectedHeight: settings.max_height,
      selectedContainer: (settings.container as VideoContainer) || "mkv",
    });
  },

  async analyze(url) {
    set({ analyzing: true, analyzeStage: "reading playlist", analyzeDone: 0, analyzeTotal: 0 });
    try {
      const analysis: Analysis = await api.analyze(url);
      const preferred = get().settings?.max_height ?? 1080;
      const best =
        analysis.qualities.find((quality) => quality.height === preferred) ??
        analysis.qualities.find((quality) => quality.height <= preferred) ??
        analysis.qualities.at(-1);
      set({
        playlist: analysis.playlist,
        qualities: analysis.qualities,
        disk: analysis.disk,
        stats: analysis.stats,
        selectedHeight: best?.height ?? null,
        selectedContainer: (get().settings?.container as VideoContainer) || "mkv",
      });
      await get().refreshJobs();
    } finally {
      set({ analyzing: false, analyzeStage: "" });
    }
  },

  selectHeight(height) {
    set({ selectedHeight: height });
  },

  async setContainer(container) {
    const { playlist, busy } = get();
    if (busy) return;
    set({ busy: true, selectedContainer: container });
    try {
      if (playlist) {
        const result = await api.refreshQualities(playlist.id, container);
        set({
          qualities: result.qualities,
          disk: result.disk,
          playlist: { ...playlist, outputDir: playlist.outputDir },
          settings: { ...(get().settings as Settings), container },
        });
      } else {
        const settings = await api.putSettings({ container });
        set({ settings });
      }
    } finally {
      set({ busy: false });
    }
  },

  async setOutputDir(path) {
    const { playlist } = get();
    if (!playlist) return;
    const result = await api.setPlaylistOutput(playlist.id, path);
    set({
      playlist: { ...playlist, outputDir: result.outputDir },
      disk: result.disk,
    });
  },

  async pickOutputFolder() {
    const { playlist } = get();
    if (!playlist) return;
    const chosen = await api.pickFolder(playlist.outputDir);
    if (chosen) await get().setOutputDir(chosen);
  },

  async start({ startFrom, endAt, redownload }) {
    const { playlist, selectedHeight, selectedContainer } = get();
    if (!playlist) return 0;
    set({ busy: true });
    try {
      const result = await api.start(playlist.id, {
        height: selectedHeight ?? undefined,
        container: selectedContainer,
        outputDir: playlist.outputDir,
        startFrom,
        endAt,
        redownload,
      });
      set({ stats: result.stats });
      await get().refreshJobs();
      return result.queued;
    } finally {
      set({ busy: false });
    }
  },

  async sync() {
    const { playlist } = get();
    if (!playlist) return { found: 0, queued: 0 };
    set({ busy: true });
    try {
      const result = await api.sync(playlist.id);
      await get().refreshJobs();
      return result;
    } finally {
      set({ busy: false });
    }
  },

  async refreshJobs() {
    const { playlist, filter, search } = get();
    if (!playlist) return;
    const { jobs, stats } = await api.listJobs(playlist.id, {
      state: filter === "all" ? undefined : filter,
      search: search || undefined,
    });
    set({ jobs, stats });
  },

  async toggleQueue() {
    const paused = get().queuePaused;
    const result = paused ? await api.resumeQueue() : await api.pauseQueue();
    set({ queuePaused: result.paused });
    await get().refreshJobs();
  },

  async retryFailed() {
    const { playlist } = get();
    if (!playlist) return 0;
    const { requeued } = await api.retryFailed(playlist.id);
    await get().refreshJobs();
    return requeued;
  },

  async jobAction(jobId, action) {
    const { job } = await api.jobAction(jobId, action);
    set((state) => ({
      jobs: state.jobs.map((candidate) => (candidate.id === job.id ? job : candidate)),
    }));
  },

  async saveSettings(changes) {
    const settings = await api.putSettings(changes);
    set({ settings });
  },

  setFilter(filter) {
    set({ filter });
    void get().refreshJobs();
  },

  setSearch(search) {
    set({ search });
    void get().refreshJobs();
  },

  clearPlaylist() {
    set({
      playlist: null,
      qualities: [],
      disk: null,
      jobs: [],
      progress: {},
      stats: EMPTY_STATS,
      filter: "all",
      search: "",
      selectedContainer: (get().settings?.container as VideoContainer) || "mkv",
    });
  },

  dismissUpdate() {
    set({ appUpdate: null });
  },

  handleEvent(event) {
    switch (event.type) {
      case "stats":
        set({ stats: event.stats, queuePaused: event.paused });
        break;
      case "job_progress":
        set((state) => ({
          progress: {
            ...state.progress,
            [event.jobId]: {
              percent: event.percent,
              downloadedBytes: event.downloadedBytes,
              totalBytes: event.totalBytes,
              speed: event.speed,
              eta: event.eta,
              status: event.status,
            },
          },
        }));
        break;
      case "job_started":
        set((state) => ({
          jobs: state.jobs.map((job) =>
            job.id === event.jobId ? { ...job, state: "running" as JobState } : job,
          ),
        }));
        break;
      case "job_done":
        set((state) => {
          const { [event.jobId]: _removed, ...progress } = state.progress;
          return {
            progress,
            jobs: state.jobs.map((job) =>
              job.id === event.jobId
                ? { ...job, state: "done" as JobState, filepath: event.filepath, filesize: event.filesize }
                : job,
            ),
          };
        });
        break;
      case "job_failed":
        set((state) => {
          const { [event.jobId]: _removed, ...progress } = state.progress;
          return {
            progress,
            jobs: state.jobs.map((job) =>
              job.id === event.jobId ? { ...job, state: "failed" as JobState, error: event.error } : job,
            ),
          };
        });
        break;
      case "job_state":
        set((state) => ({
          jobs: state.jobs.map((job) => (job.id === event.job.id ? event.job : job)),
        }));
        break;
      case "throttled":
        set({ throttleNotice: event.message });
        break;
      case "analyze_stage":
        set({ analyzeStage: event.stage });
        break;
      case "analyze_progress":
        set({ analyzeDone: event.done, analyzeTotal: event.total });
        break;
      case "settings":
        set({ settings: event.settings });
        break;
      case "ytdlp_update":
        if (event.version) set({ engineVersion: event.version });
        break;
      case "app_update":
        set({ appUpdate: { version: event.version, url: event.url } });
        break;
      default:
        break;
    }
  },
}));
