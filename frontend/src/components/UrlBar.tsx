import { LoaderCircleIcon, SearchIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useStore } from "@/store";

export function UrlBar({ compact = false }: { compact?: boolean }) {
  const [url, setUrl] = useState("");
  const analyze = useStore((state) => state.analyze);
  const analyzing = useStore((state) => state.analyzing);
  const stage = useStore((state) => state.analyzeStage);
  const done = useStore((state) => state.analyzeDone);
  const total = useStore((state) => state.analyzeTotal);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!url.trim() || analyzing) return;
    try {
      await analyze(url.trim());
    } catch (error) {
      toast.error("Could not read that link", {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const label = total > 0 ? `${stage} ${done}/${total}` : stage || "Reading";

  return (
    <form onSubmit={submit} className="flex w-full gap-2">
      <Input
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="Paste a YouTube playlist link"
        className={compact ? "" : "h-11 text-base"}
        spellCheck={false}
        autoFocus={!compact}
      />
      <Button
        type="submit"
        size={compact ? "default" : "lg"}
        disabled={analyzing || !url.trim()}
        className="min-w-32"
      >
        {analyzing ? (
          <>
            <LoaderCircleIcon className="animate-spin" />
            {label}
          </>
        ) : (
          <>
            <SearchIcon />
            Analyze
          </>
        )}
      </Button>
    </form>
  );
}
