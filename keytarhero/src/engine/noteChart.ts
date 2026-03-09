import type { NoteChart } from '../types';

export const DEMO_CHART_SIMPLE: NoteChart = {
  songTitle: 'Demo - Easy',
  artist: 'Keytar Hero',
  bpm: 120,
  notes: Array.from({ length: 30 }, (_, i) => ({
    id: `demo-s-${i}`,
    lane: (i * 3 + i) % 5,
    timeMs: 2000 + i * 500,
  })),
};

export const DEMO_CHART_MEDIUM: NoteChart = {
  songTitle: 'Demo - Medium',
  artist: 'Keytar Hero',
  bpm: 140,
  notes: (() => {
    const notes = [];
    let id = 0;
    for (let beat = 0; beat < 60; beat++) {
      const t = 2000 + beat * 428;
      notes.push({ id: `demo-m-${id++}`, lane: beat % 5, timeMs: t });
      if (beat % 4 === 0) {
        notes.push({ id: `demo-m-${id++}`, lane: (beat + 2) % 5, timeMs: t });
      }
      if (beat % 3 === 0) {
        notes.push({ id: `demo-m-${id++}`, lane: (beat + 1) % 5, timeMs: t + 214 });
      }
    }
    return notes.sort((a, b) => a.timeMs - b.timeMs);
  })(),
};
