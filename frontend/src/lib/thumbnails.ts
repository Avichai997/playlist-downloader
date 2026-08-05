/** YouTube thumbnail URLs — no download needed, keyed by video id. */
export function youtubeThumbnail(videoId: string, quality: "default" | "hq" | "mq" | "sd" = "hq") {
  const file = { default: "default", hq: "hqdefault", mq: "mqdefault", sd: "sddefault" }[quality];
  return `https://i.ytimg.com/vi/${videoId}/${file}.jpg`;
}

export function youtubeWatchUrl(videoId: string) {
  return `https://www.youtube.com/watch?v=${videoId}`;
}
