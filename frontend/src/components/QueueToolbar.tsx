import { PauseIcon, PlayIcon, RotateCcwIcon, SearchIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { JobState } from "@/lib/api";
import { bytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";

const FILTERS: { key: JobState | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "running", label: "Downloading" },
  { key: "queued", label: "Queued" },
  { key: "done", label: "Done" },
  { key: "failed", label: "Failed" },
  { key: "paused", label: "Paused" },
];

export function QueueToolbar() {
  const stats = useStore((state) => state.stats);
  const paused = useStore((state) => state.queuePaused);
  const filter = useStore((state) => state.filter);
  const search = useStore((state) => state.search);
  const progress = useStore((state) => state.progress);
  const toggleQueue = useStore((state) => state.toggleQueue);
  const retryFailed = useStore((state) => state.retryFailed);
  const setFilter = useStore((state) => state.setFilter);
  const setSearch = useStore((state) => state.setSearch);

  const combinedSpeed = Object.values(progress).reduce(
    (total, entry) => total + (entry.speed ?? 0),
    0,
  );

  const onRetry = async () => {
    const requeued = await retryFailed();
    toast[requeued > 0 ? "success" : "info"](
      requeued > 0 ? `Re-queued ${requeued} videos` : "Nothing to retry",
    );
  };

  const counts: Record<string, number> = {
    all: stats.total,
    running: stats.running,
    queued: stats.queued,
    done: stats.done,
    failed: stats.failed,
    paused: stats.paused,
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
        {FILTERS.map((entry) => (
          <button
            key={entry.key}
            type="button"
            onClick={() => setFilter(entry.key)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              filter === entry.key
                ? "bg-secondary text-secondary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {entry.label}
            <span className="tabular opacity-60">{counts[entry.key] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search titles"
          className="h-8 w-48 pl-8 text-xs"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        {combinedSpeed > 0 && (
          <Badge variant="running" className="tabular">
            {bytes(combinedSpeed)}/s
          </Badge>
        )}
        <Badge variant="outline" className="tabular">
          {bytes(
            useStore.getState().jobs.reduce((total, job) => total + (job.filesize ?? 0), 0),
          )}{" "}
          on disk
        </Badge>
        {stats.failed > 0 && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCcwIcon />
            Retry {stats.failed} failed
          </Button>
        )}
        <Button variant={paused ? "default" : "secondary"} size="sm" onClick={toggleQueue}>
          {paused ? <PlayIcon /> : <PauseIcon />}
          {paused ? "Resume all" : "Pause all"}
        </Button>
      </div>
    </div>
  );
}
