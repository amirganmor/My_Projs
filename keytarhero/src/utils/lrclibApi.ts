import type { LyricLine } from '../types';

interface LrcLibResult {
  id: number;
  trackName: string;
  artistName: string;
  syncedLyrics: string | null;
  plainLyrics: string | null;
}

export function parseLRC(lrc: string): LyricLine[] {
  const lines: LyricLine[] = [];
  const regex = /\[(\d{2}):(\d{2})\.(\d{2,3})\]\s*(.*)/g;
  let match;
  while ((match = regex.exec(lrc)) !== null) {
    const minutes = parseInt(match[1], 10);
    const seconds = parseInt(match[2], 10);
    let centis = match[3];
    if (centis.length === 2) centis += '0';
    const ms = minutes * 60000 + seconds * 1000 + parseInt(centis, 10);
    const text = match[4].trim();
    if (text) {
      lines.push({ timeMs: ms, text });
    }
  }
  return lines.sort((a, b) => a.timeMs - b.timeMs);
}

function cleanTitle(raw: string): string {
  return raw
    .replace(/\(official\s*(music\s*)?video\)/gi, '')
    .replace(/\(official\s*audio\)/gi, '')
    .replace(/\(lyric\s*video\)/gi, '')
    .replace(/\(lyrics?\)/gi, '')
    .replace(/\(live\)/gi, '')
    .replace(/\(audio\)/gi, '')
    .replace(/\[official\s*(music\s*)?video\]/gi, '')
    .replace(/\[.*?\]/g, '')
    .replace(/\bft\.?\s+/gi, '')
    .replace(/\bfeat\.?\s+/gi, '')
    .replace(/\bhd\b/gi, '')
    .replace(/\bremastered\b/gi, '')
    .replace(/\b\d{4}\b/g, '')
    .replace(/[|]/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function splitArtistTitle(raw: string): { title: string; artist: string } | null {
  const sep = raw.indexOf(' - ');
  if (sep > 0) {
    return {
      artist: raw.slice(0, sep).trim(),
      title: raw.slice(sep + 3).trim(),
    };
  }
  return null;
}

async function tryFetch(url: string): Promise<LrcLibResult[] | null> {
  try {
    console.log('[Lyrics] Trying:', url);
    const res = await fetch(url);
    if (!res.ok) {
      console.warn('[Lyrics] HTTP', res.status, 'for', url);
      return null;
    }
    const data = await res.json();
    return Array.isArray(data) ? data : [data];
  } catch (err) {
    console.warn('[Lyrics] Fetch error:', err);
    return null;
  }
}

function extractLyrics(results: LrcLibResult[]): LyricLine[] {
  const synced = results.find((r) => r.syncedLyrics);
  if (synced?.syncedLyrics) {
    const lines = parseLRC(synced.syncedLyrics);
    console.log('[Lyrics] Got', lines.length, 'synced lines');
    return lines;
  }
  const plain = results.find((r) => r.plainLyrics);
  if (plain?.plainLyrics) {
    const lines = plain.plainLyrics
      .split('\n')
      .filter((l) => l.trim())
      .map((text) => ({ timeMs: 0, text: text.trim() }));
    console.log('[Lyrics] Got', lines.length, 'plain lines');
    return lines;
  }
  return [];
}

export async function searchLyrics(title: string, artist: string): Promise<LyricLine[]> {
  console.log('[Lyrics] searchLyrics called with title:', JSON.stringify(title), 'artist:', JSON.stringify(artist));

  const cleanedTitle = cleanTitle(title);
  const cleanedArtist = cleanTitle(artist);
  const parsed = splitArtistTitle(cleanedTitle);

  const queries: string[] = [];

  if (parsed) {
    queries.push(`${parsed.title} ${parsed.artist}`);
    queries.push(parsed.title);
  }
  queries.push(`${cleanedTitle} ${cleanedArtist}`);
  queries.push(cleanedTitle);

  const directTitle = parsed?.title || cleanedTitle;
  const directArtist = parsed?.artist || cleanedArtist;

  // Try search endpoint with each query
  for (const q of queries) {
    const results = await tryFetch(`https://lrclib.net/api/search?q=${encodeURIComponent(q)}`);
    if (results && results.length > 0) {
      const lyrics = extractLyrics(results);
      if (lyrics.length > 0) {
        console.log('[Lyrics] Found lyrics via search query:', q);
        return lyrics;
      }
    }
  }

  // Try direct get endpoint
  const directUrl = `https://lrclib.net/api/get?artist_name=${encodeURIComponent(directArtist)}&track_name=${encodeURIComponent(directTitle)}`;
  const directResult = await tryFetch(directUrl);
  if (directResult && directResult.length > 0) {
    const lyrics = extractLyrics(directResult);
    if (lyrics.length > 0) {
      console.log('[Lyrics] Found lyrics via direct lookup');
      return lyrics;
    }
  }

  console.warn('[Lyrics] No lyrics found after all attempts');
  return [];
}
