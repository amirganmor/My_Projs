import type { NoteChart, Difficulty, LyricLine } from '../types';

function seededRandom(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

type Pattern = number[][];

function generatePatterns(rand: () => number, lanes: number[]): Pattern[] {
  const pick = () => lanes[Math.floor(rand() * lanes.length)];
  const neighbor = (lane: number, dir: number) => {
    const idx = lanes.indexOf(lane);
    const next = idx + dir;
    return lanes[Math.max(0, Math.min(lanes.length - 1, next))];
  };

  return [
    // Scale run up
    (() => {
      const start = lanes[0];
      return lanes.slice(0, 4).map((_, i) => [neighbor(start, i)]);
    })(),
    // Scale run down
    (() => {
      const start = lanes[lanes.length - 1];
      return lanes.slice(0, 4).map((_, i) => [neighbor(start, -i)]);
    })(),
    // Repeated note (pulse)
    (() => {
      const l = pick();
      return [[l], [l], [l], [l]];
    })(),
    // Alternating two lanes
    (() => {
      const a = pick();
      let b = pick();
      while (b === a && lanes.length > 1) b = pick();
      return [[a], [b], [a], [b]];
    })(),
    // Step up then back
    (() => {
      const base = pick();
      const up = neighbor(base, 1);
      return [[base], [up], [up], [base]];
    })(),
    // Walk pattern (1-2-3-2)
    (() => {
      const idx = Math.floor(rand() * Math.max(1, lanes.length - 2));
      const a = lanes[idx];
      const b = lanes[Math.min(idx + 1, lanes.length - 1)];
      const c = lanes[Math.min(idx + 2, lanes.length - 1)];
      return [[a], [b], [c], [b]];
    })(),
    // Gap pattern (note, rest, note, note)
    (() => {
      const a = pick();
      const b = neighbor(a, 1);
      return [[a], [], [b], [a]];
    })(),
    // Chord pattern (for medium+)
    (() => {
      const a = pick();
      const b = neighbor(a, 1);
      return [[a, b], [], [a], [b]];
    })(),
    // Hammer-on run
    (() => {
      const start = pick();
      return [[start], [neighbor(start, 1)], [neighbor(start, 2)], []];
    })(),
    // Power chord hit
    (() => {
      const a = pick();
      const b = neighbor(a, 1);
      return [[a, b], [a, b], [], []];
    })(),
  ];
}

interface DifficultyConfig {
  lanes: number[];
  division: number;
  notesPerLine: number;
  soloMultiplier: number;
  chordChance: number;
}

const DIFFICULTY_CONFIGS: Record<Difficulty, DifficultyConfig> = {
  beginner: { lanes: [1, 2, 3], division: 0.5, notesPerLine: 2, soloMultiplier: 0.5, chordChance: 0 },
  casual:   { lanes: [1, 2, 3], division: 1,   notesPerLine: 3, soloMultiplier: 0.7, chordChance: 0 },
  easy:     { lanes: [1, 2, 3], division: 1,   notesPerLine: 4, soloMultiplier: 1,   chordChance: 0 },
  medium:   { lanes: [0, 1, 2, 3, 4], division: 2, notesPerLine: 6, soloMultiplier: 1.5, chordChance: 0.15 },
  hard:     { lanes: [0, 1, 2, 3, 4], division: 4, notesPerLine: 8, soloMultiplier: 2,   chordChance: 0.3 },
};

interface Section {
  type: 'vocal' | 'instrumental';
  startMs: number;
  endMs: number;
  lyricLines: LyricLine[];
}

function buildSections(lyrics: LyricLine[], durationMs: number): Section[] {
  const sections: Section[] = [];
  const GAP_THRESHOLD = 4000;

  if (lyrics.length === 0) {
    sections.push({ type: 'instrumental', startMs: 0, endMs: durationMs, lyricLines: [] });
    return sections;
  }

  // Intro instrumental
  if (lyrics[0].timeMs > GAP_THRESHOLD) {
    sections.push({ type: 'instrumental', startMs: 2000, endMs: lyrics[0].timeMs - 500, lyricLines: [] });
  }

  let currentVocal: LyricLine[] = [];
  let vocalStart = lyrics[0].timeMs;

  for (let i = 0; i < lyrics.length; i++) {
    const line = lyrics[i];
    const nextLine = lyrics[i + 1];

    currentVocal.push(line);

    const gap = nextLine ? nextLine.timeMs - line.timeMs : durationMs - line.timeMs;

    if (gap > GAP_THRESHOLD || !nextLine) {
      sections.push({
        type: 'vocal',
        startMs: vocalStart,
        endMs: line.timeMs + Math.min(gap, 3000),
        lyricLines: [...currentVocal],
      });

      if (nextLine && gap > GAP_THRESHOLD) {
        sections.push({
          type: 'instrumental',
          startMs: line.timeMs + 2000,
          endMs: nextLine.timeMs - 500,
          lyricLines: [],
        });
      }

      currentVocal = [];
      if (nextLine) vocalStart = nextLine.timeMs;
    }
  }

  // Outro instrumental
  const lastLyric = lyrics[lyrics.length - 1];
  if (durationMs - lastLyric.timeMs > GAP_THRESHOLD) {
    sections.push({
      type: 'instrumental',
      startMs: lastLyric.timeMs + 3000,
      endMs: durationMs - 1000,
      lyricLines: [],
    });
  }

  return sections;
}

export function generateChart(
  bpm: number,
  durationMs: number,
  difficulty: Difficulty,
  lyrics: LyricLine[],
  songTitle = 'Generated',
  artist = 'Auto'
): NoteChart {
  const rand = seededRandom(Math.round(bpm * 1000 + durationMs));
  const beatMs = 60000 / bpm;
  const cfg = DIFFICULTY_CONFIGS[difficulty];
  const subBeatMs = beatMs / cfg.division;
  const notes: Array<{ id: string; lane: number; timeMs: number }> = [];
  let id = 0;

  const syncedLyrics = lyrics.filter(l => l.timeMs > 0);
  const patterns = generatePatterns(rand, cfg.lanes);
  const pickPattern = () => patterns[Math.floor(rand() * patterns.length)];

  const addNote = (lane: number, timeMs: number) => {
    if (timeMs > 1000 && timeMs < durationMs - 500) {
      notes.push({ id: `gen-${id++}`, lane, timeMs: Math.round(timeMs) });
    }
  };

  const fillPattern = (startMs: number, count: number) => {
    const pattern = pickPattern();
    let t = startMs;
    let placed = 0;
    for (let rep = 0; placed < count; rep++) {
      for (const beat of pattern) {
        if (placed >= count) break;
        for (const lane of beat) {
          addNote(lane, t);
          placed++;
        }
        t += subBeatMs;
      }
    }
    return t;
  };

  const fillSolo = (startMs: number, endMs: number) => {
    const soloPatterns = [
      patterns[0], // scale up
      patterns[1], // scale down
      patterns[8], // hammer-on run
    ];
    let t = startMs;
    while (t < endMs) {
      const pat = soloPatterns[Math.floor(rand() * soloPatterns.length)];
      for (const beat of pat) {
        if (t >= endMs) break;
        for (const lane of beat) {
          addNote(lane, t);
        }
        t += subBeatMs / cfg.soloMultiplier;
      }
      t += subBeatMs * 2;
    }
  };

  if (syncedLyrics.length >= 5) {
    const sections = buildSections(syncedLyrics, durationMs);

    for (const section of sections) {
      if (section.type === 'vocal') {
        for (const line of section.lyricLines) {
          const wordCount = line.text.split(/\s+/).length;
          const noteCount = Math.max(1, Math.min(cfg.notesPerLine, Math.ceil(wordCount * (cfg.notesPerLine / 6))));
          fillPattern(line.timeMs, noteCount);
        }
      } else {
        fillSolo(section.startMs, section.endMs);
      }
    }
  } else {
    // Fallback: pure BPM-based generation
    let t = 2000;
    const endMs = durationMs - 1000;
    while (t < endMs) {
      const pattern = pickPattern();
      const repeats = 2 + (rand() < 0.3 ? 1 : 0);
      for (let rep = 0; rep < repeats && t < endMs; rep++) {
        for (const beat of pattern) {
          if (t >= endMs) break;
          for (const lane of beat) {
            addNote(lane, t);
          }
          t += subBeatMs;
        }
      }
      t += subBeatMs * 2;
      if (rand() < 0.15) t += subBeatMs * 2;
    }
  }

  return {
    songTitle,
    artist,
    bpm,
    notes: notes.sort((a, b) => a.timeMs - b.timeMs),
  };
}

// Keep backward compat
export const generateChartFromBPM = (
  bpm: number,
  durationMs: number,
  difficulty: Difficulty,
  songTitle?: string,
  artist?: string
) => generateChart(bpm, durationMs, difficulty, [], songTitle, artist);
