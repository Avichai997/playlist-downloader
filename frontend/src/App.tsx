import { ListVideoIcon, MoonIcon, SunIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { JobTable } from "@/components/JobTable";
import { QueueToolbar } from "@/components/QueueToolbar";
import { SettingsDialog } from "@/components/SettingsDialog";
import { SetupPanel } from "@/components/SetupPanel";
import { UpdateBanner } from "@/components/UpdateBanner";
import { UpdateButton } from "@/components/UpdateButton";
import { UrlBar } from "@/components/UrlBar";
import { Button } from "@/components/ui/button";
import { connectEvents } from "@/lib/api";
import { useStore } from "@/store";

const THEME_KEY = "pldl-theme";

function useTheme() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((value) => !value) };
}

export default function App() {
  const { dark, toggle } = useTheme();
  const playlist = useStore((state) => state.playlist);
  const engineVersion = useStore((state) => state.engineVersion);
  const throttleNotice = useStore((state) => state.throttleNotice);
  const bootstrap = useStore((state) => state.bootstrap);
  const handleEvent = useStore((state) => state.handleEvent);

  useEffect(() => {
    void bootstrap();
    return connectEvents(handleEvent);
  }, [bootstrap, handleEvent]);

  useEffect(() => {
    if (throttleNotice) toast.warning("Slowing down", { description: throttleNotice });
  }, [throttleNotice]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3">
        <ListVideoIcon className="size-5 text-primary" />
        <h1 className="text-sm font-semibold">Playlist Downloader</h1>
        {engineVersion && (
          <span className="tabular text-xs text-muted-foreground">yt-dlp {engineVersion}</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <UpdateButton />
          {playlist && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs"
              onClick={() => useStore.getState().clearPlaylist()}
            >
              New playlist
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={toggle} title="Toggle theme">
            {dark ? <SunIcon /> : <MoonIcon />}
          </Button>
          <SettingsDialog />
        </div>
      </header>

      <UpdateBanner />

      {playlist ? (
        <main className="flex min-h-0 flex-1 flex-col gap-4 p-6">
          <SetupPanel />
          <QueueToolbar />
          <JobTable />
        </main>
      ) : (
        <main className="flex flex-1 items-center justify-center p-6">
          <div className="flex w-full max-w-xl flex-col items-center gap-6 text-center">
            <div className="flex flex-col gap-2">
              <h2 className="text-2xl font-semibold tracking-tight">
                Download a whole playlist
              </h2>
              <p className="text-sm text-muted-foreground">
                Numbered in order, subtitles embedded, many at a time. Stop whenever you like and
                come back — it picks up exactly where it left off.
              </p>
            </div>
            <UrlBar />
          </div>
        </main>
      )}
    </div>
  );
}
