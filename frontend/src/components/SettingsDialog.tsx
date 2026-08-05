import { SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { Settings } from "@/lib/api";
import { useStore } from "@/store";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h4>
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <Label className="font-normal">{label}</Label>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function SettingsDialog() {
  const settings = useStore((state) => state.settings);
  const saveSettings = useStore((state) => state.saveSettings);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Settings | null>(settings);

  useEffect(() => {
    if (open) setDraft(settings);
  }, [open, settings]);

  if (!draft) return null;

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));

  const save = async () => {
    try {
      await saveSettings(draft);
      toast.success("Settings saved");
      setOpen(false);
    } catch (error) {
      toast.error("Could not save", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" title="Settings">
          <SettingsIcon />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Changes apply to videos queued from now on.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 flex flex-col gap-6 overflow-y-auto pr-2">
          <Section title="Files">
            <Row label="Download folder">
              <Input
                value={draft.output_root}
                onChange={(event) => update("output_root", event.target.value)}
                className="h-8 w-64 text-xs"
              />
            </Row>
            <Row label="Container" hint="MKV holds multiple subtitle tracks cleanly">
              <Select value={draft.container} onValueChange={(value) => update("container", value)}>
                <SelectTrigger className="h-8 w-28 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mp4">MP4 — plays everywhere</SelectItem>
                  <SelectItem value="mkv">MKV — best for subtitles</SelectItem>
                  <SelectItem value="webm">WebM — smaller VP9 files</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Numbering" hint="Padded keeps 882 videos in order in Finder">
              <Select value={draft.numbering} onValueChange={(value) => update("numbering", value)}>
                <SelectTrigger className="h-8 w-36 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="padded">001. Title</SelectItem>
                  <SelectItem value="plain">1. Title</SelectItem>
                  <SelectItem value="none">Title only</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Windows-safe filenames" hint="Keeps files portable to a PC">
              <Switch
                checked={draft.windows_safe_filenames}
                onCheckedChange={(value) => update("windows_safe_filenames", value)}
              />
            </Row>
          </Section>

          <Section title="Speed">
            <Row label="Videos at once" hint="4 saturates most home connections">
              <Input
                type="number"
                min={1}
                max={8}
                value={draft.parallel_videos}
                onChange={(event) => update("parallel_videos", Number(event.target.value))}
                className="tabular h-8 w-20 text-xs"
              />
            </Row>
            <Row label="Fragments per video" hint="The main speed lever on YouTube">
              <Input
                type="number"
                min={1}
                max={64}
                value={draft.fragments_per_video}
                onChange={(event) => update("fragments_per_video", Number(event.target.value))}
                className="tabular h-8 w-20 text-xs"
              />
            </Row>
            <Row label="Speed limit" hint="Per connection, e.g. 2M. Blank for unlimited">
              <Input
                value={draft.rate_limit}
                onChange={(event) => update("rate_limit", event.target.value)}
                placeholder="unlimited"
                className="h-8 w-24 text-xs"
              />
            </Row>
            <Row label="Only download between" hint="e.g. 01:00-08:00. Blank for any time">
              <Input
                value={draft.night_window}
                onChange={(event) => update("night_window", event.target.value)}
                placeholder="any time"
                className="h-8 w-28 text-xs"
              />
            </Row>
          </Section>

          <Section title="Subtitles">
            <Row label="Download subtitles" hint="Embedded in the file as selectable tracks">
              <Switch
                checked={draft.subtitles}
                onCheckedChange={(value) => update("subtitles", value)}
              />
            </Row>
            <Row label="Languages" hint="Comma separated, e.g. en, he">
              <Input
                value={draft.sub_langs.join(", ")}
                onChange={(event) =>
                  update(
                    "sub_langs",
                    event.target.value
                      .split(",")
                      .map((part) => part.trim())
                      .filter(Boolean),
                  )
                }
                className="h-8 w-32 text-xs"
              />
            </Row>
            <Row label="Fall back to auto-generated">
              <Switch
                checked={draft.auto_subs}
                onCheckedChange={(value) => update("auto_subs", value)}
              />
            </Row>
            <Row label="Also keep .srt files alongside">
              <Switch
                checked={draft.keep_sub_files}
                onCheckedChange={(value) => update("keep_sub_files", value)}
              />
            </Row>
          </Section>

          <Section title="Extras">
            <Row label="Embed thumbnail, metadata and chapters">
              <Switch
                checked={draft.embed_thumbnail && draft.embed_metadata && draft.embed_chapters}
                onCheckedChange={(value) => {
                  update("embed_thumbnail", value);
                  update("embed_metadata", value);
                  update("embed_chapters", value);
                }}
              />
            </Row>
            <Row label="Sponsor segments">
              <Select
                value={draft.sponsorblock}
                onValueChange={(value) => update("sponsorblock", value)}
              >
                <SelectTrigger className="h-8 w-32 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="off">Leave alone</SelectItem>
                  <SelectItem value="mark">Mark as chapters</SelectItem>
                  <SelectItem value="remove">Cut out</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Audio only" hint="Extract audio instead of keeping video">
              <Switch
                checked={draft.audio_only}
                onCheckedChange={(value) => update("audio_only", value)}
              />
            </Row>
          </Section>

          <Section title="Reliability">
            <Row label="Verify every file" hint="Re-checks length with ffprobe and retries if short">
              <Switch
                checked={draft.verify_downloads}
                onCheckedChange={(value) => update("verify_downloads", value)}
              />
            </Row>
            <Row label="Update yt-dlp on launch" hint="The most common cause of failures is a stale copy">
              <Switch
                checked={draft.update_ytdlp_on_launch}
                onCheckedChange={(value) => update("update_ytdlp_on_launch", value)}
              />
            </Row>
            <Row label="Use cookies from" hint="Needed for members-only or age-gated videos">
              <Select
                value={draft.cookies_browser || "none"}
                onValueChange={(value) => update("cookies_browser", value === "none" ? "" : value)}
              >
                <SelectTrigger className="h-8 w-32 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No browser</SelectItem>
                  <SelectItem value="chrome">Chrome</SelectItem>
                  <SelectItem value="safari">Safari</SelectItem>
                  <SelectItem value="firefox">Firefox</SelectItem>
                  <SelectItem value="edge">Edge</SelectItem>
                  <SelectItem value="brave">Brave</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Check for new videos every" hint="0 turns the background check off">
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  min={0}
                  max={168}
                  value={draft.watch_interval_hours}
                  onChange={(event) => update("watch_interval_hours", Number(event.target.value))}
                  className="tabular h-8 w-16 text-xs"
                />
                <span className="text-xs text-muted-foreground">hours</span>
              </div>
            </Row>
          </Section>
        </div>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={save}>Save</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
