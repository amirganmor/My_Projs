import { useEffect, useRef } from 'react';
import type { GameState } from '../types';
import { getGrade, getStars } from '../engine/scoring';
import { saveScore, getScores } from '../utils/leaderboard';

interface ResultsScreenProps {
  state: GameState;
  onPlayAgain: () => void;
  onNewSong: () => void;
}

export default function ResultsScreen({ state, onPlayAgain, onNewSong }: ResultsScreenProps) {
  const accuracy = state.totalNotes > 0 ? state.totalHits / state.totalNotes : 0;
  const grade = getGrade(accuracy);
  const stars = getStars(accuracy);
  const savedRef = useRef(false);

  useEffect(() => {
    if (savedRef.current || !state.songConfig) return;
    savedRef.current = true;
    saveScore(state.songConfig.videoId, {
      score: state.score,
      accuracy,
      maxStreak: state.maxStreak,
      date: new Date().toISOString(),
    });
  }, [state, accuracy]);

  const highScores = state.songConfig ? getScores(state.songConfig.videoId) : [];

  const gradeColors: Record<string, string> = {
    S: '#facc15',
    A: '#22c55e',
    B: '#3b82f6',
    C: '#f97316',
    F: '#ef4444',
  };

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-game-bg gap-6 px-4">
      <h1 className="text-4xl font-heading text-yellow-400">SONG COMPLETE!</h1>

      {state.chart && (
        <p className="text-white/60 text-lg">
          {state.chart.songTitle} — {state.chart.artist}
        </p>
      )}

      {/* Grade */}
      <div
        className="text-8xl font-heading"
        style={{
          color: gradeColors[grade] || '#fff',
          textShadow: `0 0 40px ${gradeColors[grade]}60`,
        }}
      >
        {grade}
      </div>

      {/* Stars */}
      <div className="flex gap-1 text-3xl">
        {[1, 2, 3, 4, 5].map((s) => (
          <span
            key={s}
            className={s <= stars ? 'text-yellow-400' : 'text-white/15'}
          >
            ★
          </span>
        ))}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-x-12 gap-y-4 text-center">
        <div>
          <div className="text-xs text-white/40 uppercase tracking-wider">Final Score</div>
          <div className="text-2xl font-heading text-white tabular-nums">
            {state.score.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="text-xs text-white/40 uppercase tracking-wider">Max Streak</div>
          <div className="text-2xl font-heading text-orange-400 tabular-nums">
            {state.maxStreak}
          </div>
        </div>
        <div>
          <div className="text-xs text-white/40 uppercase tracking-wider">Accuracy</div>
          <div className="text-2xl font-heading text-white tabular-nums">
            {(accuracy * 100).toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="text-xs text-white/40 uppercase tracking-wider">Perfect Hits</div>
          <div className="text-2xl font-heading text-yellow-400 tabular-nums">
            {state.perfectHits} / {state.totalNotes}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-4 mt-4">
        <button
          onClick={onPlayAgain}
          className="px-8 py-3 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded-lg transition-colors cursor-pointer"
        >
          Play Again
        </button>
        <button
          onClick={onNewSong}
          className="px-8 py-3 bg-white/10 hover:bg-white/20 text-white font-bold rounded-lg transition-colors cursor-pointer"
        >
          New Song
        </button>
      </div>

      {/* Leaderboard */}
      {highScores.length > 1 && (
        <div className="mt-6 w-full max-w-sm">
          <h3 className="text-sm text-white/40 uppercase tracking-wider mb-2 text-center">
            Top Scores for This Song
          </h3>
          <div className="flex flex-col gap-1">
            {highScores.slice(0, 5).map((entry, i) => (
              <div
                key={i}
                className="flex justify-between text-sm px-3 py-1 rounded bg-white/5"
              >
                <span className="text-white/60">#{i + 1}</span>
                <span className="text-white font-bold tabular-nums">
                  {entry.score.toLocaleString()}
                </span>
                <span className="text-white/40">
                  {(entry.accuracy * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
