import { useMemo } from 'react';
import type { LyricLine } from '../types';

export interface LyricsState {
  currentLine: string;
  nextLine: string;
  currentIndex: number;
}

export function useLyrics(lyrics: LyricLine[], currentTimeMs: number): LyricsState {
  return useMemo(() => {
    if (lyrics.length === 0) {
      return { currentLine: '', nextLine: '', currentIndex: -1 };
    }

    // All unsynced (timeMs === 0 for all): just return first line
    if (lyrics.every((l) => l.timeMs === 0)) {
      return { currentLine: lyrics[0]?.text ?? '', nextLine: lyrics[1]?.text ?? '', currentIndex: 0 };
    }

    // Binary search for current line
    let lo = 0;
    let hi = lyrics.length - 1;
    let idx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      if (lyrics[mid].timeMs <= currentTimeMs) {
        idx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }

    if (idx < 0) {
      return { currentLine: '', nextLine: lyrics[0]?.text ?? '', currentIndex: -1 };
    }

    return {
      currentLine: lyrics[idx].text,
      nextLine: lyrics[idx + 1]?.text ?? '',
      currentIndex: idx,
    };
  }, [lyrics, currentTimeMs]);
}
