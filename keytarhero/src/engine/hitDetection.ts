import type { Note, HitQuality } from '../types';
import { HIT_WINDOW_MS, GOOD_WINDOW_MS } from './constants';

export function checkHit(
  note: Note,
  currentTimeMs: number,
  pressedLane: number
): HitQuality | 'MISS' | null {
  if (note.hit || note.missed) return null;
  if (note.lane !== pressedLane) return null;

  const diff = Math.abs(currentTimeMs - note.timeMs);

  if (diff <= HIT_WINDOW_MS) return 'PERFECT';
  if (diff <= GOOD_WINDOW_MS) return 'GOOD';

  return null;
}

export function findHittableNotes(
  notes: Note[],
  currentTimeMs: number,
  pressedLanes: Set<number>
): Array<{ note: Note; quality: HitQuality }> {
  const hits: Array<{ note: Note; quality: HitQuality }> = [];

  for (const note of notes) {
    if (note.hit || note.missed) continue;
    if (!pressedLanes.has(note.lane)) continue;

    const diff = Math.abs(currentTimeMs - note.timeMs);
    if (diff > GOOD_WINDOW_MS) {
      if (note.timeMs > currentTimeMs + GOOD_WINDOW_MS) break;
      continue;
    }

    const quality = diff <= HIT_WINDOW_MS ? 'PERFECT' : 'GOOD';
    hits.push({ note, quality });
  }

  return hits;
}

export function findMissedNotes(notes: Note[], currentTimeMs: number): Note[] {
  const missed: Note[] = [];
  for (const note of notes) {
    if (note.hit || note.missed) continue;
    if (note.timeMs < currentTimeMs - GOOD_WINDOW_MS) {
      missed.push(note);
    }
    if (note.timeMs > currentTimeMs + GOOD_WINDOW_MS) break;
  }
  return missed;
}
