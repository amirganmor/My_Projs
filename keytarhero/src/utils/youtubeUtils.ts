export function extractVideoId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtube\.com\/embed\/|youtu\.be\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})/,
    /^([a-zA-Z0-9_-]{11})$/,
  ];
  for (const p of patterns) {
    const m = url.match(p);
    if (m) return m[1];
  }
  return null;
}

export interface VideoMeta {
  title: string;
  author: string;
}

export async function getVideoMeta(videoId: string): Promise<VideoMeta> {
  const url = `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch video metadata');
  const data = await res.json();
  return { title: data.title, author: data.author_name };
}
