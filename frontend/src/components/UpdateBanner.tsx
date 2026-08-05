import { DownloadIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useStore } from "@/store";

export function UpdateBanner() {
  const update = useStore((state) => state.appUpdate);
  const dismissUpdate = useStore((state) => state.dismissUpdate);

  if (!update) return null;

  const download = () => {
    void api.openUrl(update.url);
  };

  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-primary/20 bg-primary/10 px-6 py-2 text-sm">
      <span className="min-w-0 flex-1">
        A newer version (<span className="tabular font-medium">v{update.version}</span>) is available.
      </span>
      <Button size="sm" onClick={download}>
        <DownloadIcon />
        Download update
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={dismissUpdate} title="Dismiss">
        <XIcon />
      </Button>
    </div>
  );
}
