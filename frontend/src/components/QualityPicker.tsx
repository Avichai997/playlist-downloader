import { CheckIcon, TriangleAlertIcon } from "lucide-react";
import { bytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";

export function QualityPicker() {
  const qualities = useStore((state) => state.qualities);
  const selected = useStore((state) => state.selectedHeight);
  const selectHeight = useStore((state) => state.selectHeight);
  const disk = useStore((state) => state.disk);

  if (qualities.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {qualities.map((quality) => {
        const active = quality.height === selected;
        const tooBig = disk ? quality.estimatedTotalBytes > disk.free : false;
        const partial = quality.coverage < 0.9;
        return (
          <button
            key={quality.height}
            type="button"
            onClick={() => selectHeight(quality.height)}
            className={cn(
              "relative flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors",
              active
                ? "border-primary bg-primary/8 ring-[3px] ring-ring"
                : "border-border hover:border-input hover:bg-accent/50",
            )}
          >
            <div className="flex w-full items-center justify-between">
              <span className="text-sm font-semibold">{quality.label}</span>
              {active && <CheckIcon className="size-4 text-primary" />}
            </div>
            <span className="text-xs text-muted-foreground">{quality.vcodec || "video"}</span>
            <span className="tabular text-sm font-medium">
              ~{bytes(quality.estimatedTotalBytes)}
            </span>
            {(tooBig || partial) && (
              <span
                className={cn(
                  "mt-0.5 inline-flex items-center gap-1 text-[0.68rem]",
                  tooBig ? "text-destructive" : "text-warning",
                )}
              >
                <TriangleAlertIcon className="size-3" />
                {tooBig ? "more than free space" : `only ${Math.round(quality.coverage * 100)}% have it`}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
