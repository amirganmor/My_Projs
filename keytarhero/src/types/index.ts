export interface Note {
  id: string;
  lane: number;
  timeMs: number;
  duration?: number;
  hit?: boolean;
  missed?: boolean;
}

export interface NoteChart {
  songTitle: string;
  artist: string;
  bpm: number;
  notes: Note[];
}

export interface LyricLine {
  timeMs: number;
  text: string;
}

export type GamePhase = 'MENU' | 'LOADING' | 'PLAYING' | 'PAUSED' | 'RESULTS';
export type Difficulty = 'beginner' | 'casual' | 'easy' | 'medium' | 'hard';
export type HitQuality = 'PERFECT' | 'GOOD';

export interface SongConfig {
  videoId: string;
  title: string;
  artist: string;
  bpm: number;
  difficulty: Difficulty;
  playbackRate: number;
}

export interface HitEffect {
  id: string;
  lane: number;
  quality: HitQuality | 'MISS';
  timeCreated: number;
  x: number;
  y: number;
}

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  color: string;
  size: number;
}

export interface GameState {
  phase: GamePhase;
  score: number;
  streak: number;
  multiplier: number;
  maxStreak: number;
  totalHits: number;
  perfectHits: number;
  totalNotes: number;
  songTimeMs: number;
  chart: NoteChart | null;
  lyrics: LyricLine[];
  songConfig: SongConfig | null;
  hitEffects: HitEffect[];
  particles: Particle[];
}

export type GameAction =
  | { type: 'START_LOADING'; songConfig: SongConfig }
  | { type: 'START_PLAYING'; chart: NoteChart; lyrics: LyricLine[] }
  | { type: 'PAUSE' }
  | { type: 'RESUME' }
  | { type: 'UPDATE_TIME'; timeMs: number }
  | { type: 'NOTE_HIT'; noteId: string; quality: HitQuality; effect: HitEffect; particles: Particle[] }
  | { type: 'NOTE_MISS'; noteId: string; effect: HitEffect }
  | { type: 'CLEANUP_EFFECTS'; now: number }
  | { type: 'SONG_END' }
  | { type: 'RESET' };
