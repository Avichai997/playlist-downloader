import { useVirtualizer } from "@tanstack/react-virtual";
import {
  FolderOpenIcon,
  PauseIcon,
  PlayIcon,
  RotateCcwIcon,
  SkipForwardIcon,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { ThumbnailPreviewDialog } from "@/components/ThumbnailPreviewDialog";
import { VideoThumbnail } from "@/components/VideoThumbnail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api, type Job, type JobState } from "@/lib/api";
import { bytes, duration, padNumber, speed } from "@/lib/format";
import { useStore } from "@/store";

const ROW_HEIGHT = 64;

const STATE_LABEL: Record<JobState, string> = {
  queued: "Queued",
  running: "Downloading",
  paused: "Paused",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

const STATE_VARIANT: Record<JobState, "default" | "running" | "done" | "failed" | "paused"> = {
  queued: "default",
  running: "running",
  paused: "paused",
  done: "done",
  failed: "failed",
  skipped: "default",
};

function JobRow({
  job,
  onPreview,
}: {
  job: Job;
  onPreview: (job: Job) => void;
}) {
  const live = useStore((state) => state.progress[job.id]);
  const jobAction = useStore((state) => state.jobAction);

  const act = async (action: "pause" | "resume" | "skip" | "retry") => {
    try {
      await jobAction(job.id, action);
    } catch (error) {
      toast.error("That did not work", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const reveal = async () => {
    if (!job.filepath) return;
    try {
      await api.reveal(job.filepath);
    } catch {
      toast.error("That file is no longer there");
    }
  };

  return (
    <div className="flex h-[64px] items-center gap-3 border-b border-border px-4 text-sm">
      <span className="tabular w-12 shrink-0 text-xs text-muted-foreground">
        {padNumber(job.number, job.total_count)}
      </span>

      <button
        type="button"
        className="shrink-0 rounded-md ring-offset-background transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        onClick={() => onPreview(job)}
        title={`Preview ${job.title}`}
      >
        <VideoThumbnail videoId={job.video_id} title={job.title} size="sm" />
      </button>

      <div className="min-w-0 flex-1">
        <div className="truncate" title={job.title}>
          {job.title}
        </div>
        {job.state === "running" && live ? (
          <div className="mt-1 flex items-center gap-2">
            <Progress
              value={live.percent ?? 0}
              indeterminate={live.percent === null}
              className="h-1 max-w-56"
            />
            <span className="tabular text-[0.68rem] text-muted-foreground">
              {live.percent !== null && `${live.percent.toFixed(0)}% · `}
              {speed(live.speed)}
              {live.eta ? ` · ${duration(live.eta)} left` : ""}
            </span>
          </div>
        ) : (
          job.error && (
            <div className="mt-0.5 truncate text-[0.7rem] text-destructive" title={job.error}>
              {job.error}
            </div>
          )
        )}
      </div>

      <span className="tabular w-20 shrink-0 text-right text-xs text-muted-foreground">
        {job.state === "done"
          ? bytes(job.filesize)
          : live?.totalBytes
            ? bytes(live.totalBytes)
            : duration(job.duration)}
      </span>

      <Badge variant={STATE_VARIANT[job.state]} className="w-24 shrink-0 justify-center">
        {STATE_LABEL[job.state]}
      </Badge>

      <div className="flex w-24 shrink-0 justify-end gap-0.5">
        {job.state === "running" && (
          <>
            <Button variant="ghost" size="icon-sm" onClick={() => act("pause")} title="Pause">
              <PauseIcon />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={() => act("skip")} title="Skip">
              <SkipForwardIcon />
            </Button>
          </>
        )}
        {(job.state === "paused" || job.state === "skipped") && (
          <Button variant="ghost" size="icon-sm" onClick={() => act("resume")} title="Resume">
            <PlayIcon />
          </Button>
        )}
        {job.state === "queued" && (
          <Button variant="ghost" size="icon-sm" onClick={() => act("pause")} title="Hold">
            <PauseIcon />
          </Button>
        )}
        {job.state === "failed" && (
          <Button variant="ghost" size="icon-sm" onClick={() => act("retry")} title="Retry">
            <RotateCcwIcon />
          </Button>
        )}
        {job.state === "done" && job.filepath && (
          <Button variant="ghost" size="icon-sm" onClick={reveal} title="Show in folder">
            <FolderOpenIcon />
          </Button>
        )}
      </div>
    </div>
  );
}

export function JobTable() {
  const jobs = useStore((state) => state.jobs);
  const container = useRef<HTMLDivElement>(null);
  const [previewJob, setPreviewJob] = useState<Job | null>(null);

  const virtualizer = useVirtualizer({
    count: jobs.length,
    getScrollElement: () => container.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  if (jobs.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border">
        <p className="text-sm text-muted-foreground">
          Nothing queued yet. Pick a quality and press Download.
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        ref={container}
        className="flex-1 overflow-y-auto rounded-xl border border-border bg-card"
      >
        <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((item) => (
            <div
              key={item.key}
              className="absolute left-0 top-0 w-full"
              style={{ transform: `translateY(${item.start}px)` }}
            >
              <JobRow job={jobs[item.index]} onPreview={setPreviewJob} />
            </div>
          ))}
        </div>
      </div>

      {previewJob && (
        <ThumbnailPreviewDialog
          open={Boolean(previewJob)}
          onOpenChange={(open) => {
            if (!open) setPreviewJob(null);
          }}
          videoId={previewJob.video_id}
          title={previewJob.title}
        />
      )}
    </>
  );
}
