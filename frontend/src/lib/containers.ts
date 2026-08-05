export type VideoContainer = "mkv" | "mp4" | "webm";

export const VIDEO_FORMATS: { id: VideoContainer; label: string; hint: string }[] = [
  { id: "mp4", label: "MP4", hint: "Plays everywhere — QuickTime, TV, phone" },
  { id: "mkv", label: "MKV", hint: "Best for subtitles and multiple audio tracks" },
  { id: "webm", label: "WebM", hint: "Smaller files, VP9 video" },
];
