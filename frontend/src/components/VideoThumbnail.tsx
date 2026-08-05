import { useState } from "react";
import { cn } from "@/lib/utils";
import { youtubeThumbnail } from "@/lib/thumbnails";

export function VideoThumbnail({
  videoId,
  title,
  size = "md",
  className,
}: {
  videoId: string;
  title: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const sizes = {
    sm: "size-10",
    md: "size-14",
    lg: "aspect-video h-auto w-full max-h-56",
  };

  if (failed || !videoId) {
    return (
      <div
        className={cn(
          "shrink-0 rounded-md bg-muted",
          sizes[size],
          className,
        )}
        title={title}
      />
    );
  }

  return (
    <img
      src={youtubeThumbnail(videoId, size === "lg" ? "sd" : "hq")}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={cn(
        "shrink-0 rounded-md object-cover bg-muted",
        sizes[size],
        className,
      )}
      title={title}
    />
  );
}
