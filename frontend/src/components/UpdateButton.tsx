import { DownloadIcon, RefreshCwIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useStore } from "@/store";

export function UpdateButton() {
  const appVersion = useStore((state) => state.appVersion);
  const update = useStore((state) => state.appUpdate);
  const checkForUpdate = useStore((state) => state.checkForUpdate);
  const [checking, setChecking] = useState(false);

  const download = () => {
    if (update?.url) {
      void api.openUrl(update.url);
      return;
    }
    void api.openUrl("https://github.com/Avichai997/playlist-downloader/releases/latest");
  };

  const onCheck = async () => {
    setChecking(true);
    try {
      const result = await checkForUpdate();
      if (result.available && result.version) {
        toast.success(`Update available: v${result.version}`, {
          description: "Click “Download update” to get the latest build.",
        });
      } else {
        toast.info("You’re up to date", {
          description: appVersion ? `Playlist Downloader v${appVersion}` : undefined,
        });
      }
    } catch (error) {
      toast.error("Could not check for updates", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <span className="tabular hidden text-xs text-muted-foreground sm:inline">
        v{appVersion || "…"}
      </span>
      {update ? (
        <Button variant="default" size="sm" className="text-xs" onClick={download}>
          <DownloadIcon />
          Download update
        </Button>
      ) : null}
      <Button
        variant="outline"
        size="sm"
        className="text-xs"
        onClick={() => void onCheck()}
        disabled={checking}
      >
        <RefreshCwIcon className={checking ? "animate-spin" : undefined} />
        Check for updates
      </Button>
    </div>
  );
}
