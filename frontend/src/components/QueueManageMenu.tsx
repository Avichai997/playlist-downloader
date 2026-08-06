import { MoreHorizontalIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useStore } from "@/store";

type ResetMode = "queue" | "files" | null;

export function QueueManageMenu() {
  const busy = useStore((state) => state.busy);
  const verifyFiles = useStore((state) => state.verifyFiles);
  const resetPlaylist = useStore((state) => state.resetPlaylist);
  const [open, setOpen] = useState(false);
  const [resetMode, setResetMode] = useState<ResetMode>(null);
  const [working, setWorking] = useState(false);

  const onVerify = async () => {
    setOpen(false);
    setWorking(true);
    try {
      const { requeued } = await verifyFiles();
      toast[requeued > 0 ? "success" : "info"](
        requeued > 0 ? `Re-queued ${requeued} missing downloads` : "All finished files are still on disk",
      );
    } catch (error) {
      toast.error("Could not verify files", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setWorking(false);
    }
  };

  const onReset = async () => {
    if (!resetMode) return;
    setWorking(true);
    try {
      const result = await resetPlaylist({
        deleteFiles: resetMode === "files",
        refetch: true,
      });
      setResetMode(null);
      setOpen(false);
      toast.success("Playlist reset", {
        description: `${result.videoCount} videos loaded. Press Download when you are ready.`,
      });
    } catch (error) {
      toast.error("Reset failed", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setWorking(false);
    }
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={busy || working}>
        <MoreHorizontalIcon />
        Manage
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Manage playlist</DialogTitle>
            <DialogDescription>
              Verify downloads, reset the queue, or start over from scratch.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <Button variant="outline" className="justify-start" onClick={() => void onVerify()} disabled={working}>
              Verify downloads
              <span className="ml-auto text-xs font-normal text-muted-foreground">
                Re-queue missing files
              </span>
            </Button>
            <Button
              variant="outline"
              className="justify-start"
              onClick={() => setResetMode("queue")}
              disabled={working}
            >
              Reset queue
              <span className="ml-auto text-xs font-normal text-muted-foreground">
                Keep files on disk
              </span>
            </Button>
            <Button
              variant="destructive"
              className="justify-start"
              onClick={() => setResetMode("files")}
              disabled={working}
            >
              Start over
              <span className="ml-auto text-xs font-normal text-white/80">
                Delete files + reset
              </span>
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={resetMode === "queue"}
        onOpenChange={(next) => {
          if (!next) setResetMode(null);
        }}
        title="Reset the download queue?"
        description="All progress flags are cleared and every video goes back to Not queued. Files already on disk are kept."
        confirmLabel="Reset queue"
        destructive
        busy={working}
        onConfirm={onReset}
      />

      <ConfirmDialog
        open={resetMode === "files"}
        onOpenChange={(next) => {
          if (!next) setResetMode(null);
        }}
        title="Start over from scratch?"
        description="This deletes downloaded files for this playlist, clears all queue state, and re-loads the full playlist from YouTube. This cannot be undone."
        confirmLabel="Delete files and reset"
        destructive
        busy={working}
        onConfirm={onReset}
      />
    </>
  );
}
