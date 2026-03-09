export interface LeaderboardEntry {
  score: number;
  accuracy: number;
  maxStreak: number;
  date: string;
}

const STORAGE_KEY = 'keytarhero_leaderboard';

function getAll(): Record<string, LeaderboardEntry[]> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function getScores(videoId: string): LeaderboardEntry[] {
  const all = getAll();
  return (all[videoId] || []).sort((a, b) => b.score - a.score);
}

export function saveScore(videoId: string, entry: LeaderboardEntry): void {
  const all = getAll();
  if (!all[videoId]) all[videoId] = [];
  all[videoId].push(entry);
  all[videoId] = all[videoId]
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // localStorage full or unavailable
  }
}
