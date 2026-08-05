import { DownloadIcon, FolderIcon, HardDriveIcon, RefreshCwIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { QualityPicker } from "@/components/QualityPicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { bytes, longDuration } from "@/lib/format";
import { useStore } from "@/store";

export function SetupPanel() {
  const playlist = useStore((state) => state.playlist);
  const disk = useStore((state) => state.disk);
  const busy = useStore((state) => state.busy);
  const start = useStore((state) => state.start);
  const sync = useStore((state) => state.sync);

  const [startFrom, setStartFrom] = useState("");
  const [endAt, setEndAt] = useState("");
  const [redownload, setRedownload] = useState(false);

  if (!playlist) return null;

  const toNumber = (value: string) => {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  };

  const onStart = async () => {
    try {
      const queued = await start({
        startFrom: toNumber(startFrom),
        endAt: toNumber(endAt),
        redownload,
      });
      toast.success(
        queued > 0 ? `Queued ${queued} videos` : "Nothing new to queue",
        queued === 0
          ? { description: "Everything selected is already downloaded." }
          : undefined,
      );
    } catch (error) {
      toast.error("Could not start", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const onSync = async () => {
    try {
      const { found, queued } = await sync();
      toast.success(
        found === 0 ? "Already up to date" : `Found ${found} new videos`,
        found > 0 ? { description: `${queued} added to the queue.` } : undefined,
      );
    } catch (error) {
      toast.error("Sync failed", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{playlist.title}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {playlist.uploader && `${playlist.uploader} · `}
              {playlist.count} videos · {longDuration(playlist.totalDuration)} of video
              {playlist.newCount > 0 && ` · ${playlist.newCount} new since last time`}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onSync} disabled={busy}>
            <RefreshCwIcon />
            Check for new
          </Button>
        </div>

        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <FolderIcon className="size-3.5" />
            {playlist.outputDir}
          </span>
          {disk && (
            <span className="inline-flex items-center gap-1.5">
              <HardDriveIcon className="size-3.5" />
              {bytes(disk.free)} free
            </span>
          )}
        </div>

        <QualityPicker />

        <div className="flex flex-wrap items-end gap-4 border-t border-border pt-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="start-from" className="text-xs text-muted-foreground">
              Start from #
            </Label>
            <Input
              id="start-from"
              value={startFrom}
              onChange={(event) => setStartFrom(event.target.value)}
              placeholder="1"
              inputMode="numeric"
              className="h-8 w-24 tabular"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="end-at" className="text-xs text-muted-foreground">
              End at #
            </Label>
            <Input
              id="end-at"
              value={endAt}
              onChange={(event) => setEndAt(event.target.value)}
              placeholder={String(playlist.count)}
              inputMode="numeric"
              className="h-8 w-24 tabular"
            />
          </div>
          <Label className="mb-1.5 gap-2 text-xs text-muted-foreground">
            <Switch checked={redownload} onCheckedChange={setRedownload} />
            Re-download finished
          </Label>

          <Button onClick={onStart} disabled={busy} className="ml-auto" size="lg">
            <DownloadIcon />
            Download
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
