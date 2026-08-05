import { CheckIcon } from "lucide-react";
import { VIDEO_FORMATS } from "@/lib/containers";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";

export function FormatPicker() {
  const selected = useStore((state) => state.selectedContainer);
  const setContainer = useStore((state) => state.setContainer);
  const busy = useStore((state) => state.busy);

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium text-muted-foreground">File format</span>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {VIDEO_FORMATS.map((format) => {
          const active = selected === format.id;
          return (
            <button
              key={format.id}
              type="button"
              disabled={busy}
              onClick={() => void setContainer(format.id)}
              className={cn(
                "flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors",
                active
                  ? "border-primary bg-primary/8 ring-[3px] ring-ring"
                  : "border-border hover:border-input hover:bg-accent/50",
                busy && "opacity-60",
              )}
            >
              <div className="flex w-full items-center justify-between">
                <span className="text-sm font-semibold">.{format.label.toLowerCase()}</span>
                {active && <CheckIcon className="size-4 text-primary" />}
              </div>
              <span className="text-xs text-muted-foreground">{format.hint}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
