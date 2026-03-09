export const LANE_KEYS = ['a', 's', 'd', 'f', 'g'] as const;
export const LANE_COLORS = ['#22c55e', '#ef4444', '#facc15', '#3b82f6', '#f97316'];
export const LANE_GLOW_COLORS = ['#4ade80', '#f87171', '#fde047', '#60a5fa', '#fb923c'];
export const STRUM_KEY = ' ';
export const PAUSE_KEY = 'Escape';

export const HIT_WINDOW_MS = 120;
export const GOOD_WINDOW_MS = 200;
export const NOTE_FALL_DURATION_MS = 2000;

export const CANVAS_WIDTH = 400;
export const HIGHWAY_HEIGHT = 600;
export const HIT_ZONE_Y = 520;
export const LANE_WIDTH = CANVAS_WIDTH / 5;
export const NOTE_HEIGHT = 20;
export const NOTE_WIDTH = LANE_WIDTH - 16;
export const HIT_CIRCLE_RADIUS = 22;

export const EFFECT_DURATION_MS = 800;

export const SCORE_PERFECT = 100;
export const SCORE_GOOD = 50;

export function getMultiplier(streak: number): number {
  if (streak >= 30) return 4;
  if (streak >= 20) return 3;
  if (streak >= 10) return 2;
  return 1;
}

export function getLaneCenterX(lane: number): number {
  return lane * LANE_WIDTH + LANE_WIDTH / 2;
}
