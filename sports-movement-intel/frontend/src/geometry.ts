export type Pt = [number, number];

export const COLORS = { home: "#38bdf8", away: "#fb7185", ball: "#fde047", accent: "#a78bfa" };

export function hull(points: Pt[]): Pt[] {
  if (points.length < 3) return points.slice();
  const p = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: Pt[] = [], upper: Pt[] = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

export function polygonArea(poly: Pt[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) { const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length]; a += x1 * y2 - x2 * y1; }
  return Math.abs(a) / 2;
}

/** Binary search: index of the last frame with t <= target (or 0). */
export function frameAt<T extends { t: number }>(frames: T[], target: number): number {
  let lo = 0, hi = frames.length - 1, ans = 0;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (frames[mid].t <= target) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
  return ans;
}

export function withAlpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
