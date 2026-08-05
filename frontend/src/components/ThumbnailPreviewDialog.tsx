import { ExternalLinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { VideoThumbnail } from "@/components/VideoThumbnail";
import { youtubeWatchUrl } from "@/lib/thumbnails";

export function ThumbnailPreviewDialog({
  open,
  onOpenChange,
  videoId,
  title,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  videoId: string;
  title: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg gap-4">
        <DialogHeader>
          <DialogTitle className="line-clamp-2 pr-6">{title}</DialogTitle>
          <DialogDescription>Preview thumbnail for this video.</DialogDescription>
        </DialogHeader>

        <VideoThumbnail videoId={videoId} title={title} size="lg" className="aspect-video h-auto w-full" />

        <Button variant="outline" className="w-full" asChild>
          <a href={youtubeWatchUrl(videoId)} target="_blank" rel="noreferrer">
            <ExternalLinkIcon />
            Open on YouTube
          </a>
        </Button>
      </DialogContent>
    </Dialog>
  );
}
