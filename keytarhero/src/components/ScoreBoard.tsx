import type { GameState } from '../types';
import { getStars } from '../engine/scoring';

interface ScoreBoardProps {
  state: GameState;
}

export default function ScoreBoard({ state }: ScoreBoardProps) {
  const accuracy = state.totalNotes > 0 ? state.totalHits / state.totalNotes : 0;
  const stars = getStars(accuracy);

  return (
    <div className="flex flex-col items-end gap-2 select-none pointer-events-none">
      {/* Score */}
      <div className="text-right">
        <div className="text-xs text-white/40 uppercase tracking-wider">Score</div>
        <div className="text-3xl font-heading text-white tabular-nums">
          {state.score.toLocaleString()}
        </div>
      </div>

      {/* Multiplier */}
      <div
        className="px-3 py-1 rounded-full text-sm font-bold"
        style={{
          background:
            state.multiplier >= 4
              ? 'linear-gradient(135deg, #f97316, #ef4444)'
              : state.multiplier >= 3
                ? 'linear-gradient(135deg, #facc15, #f97316)'
                : state.multiplier >= 2
                  ? 'linear-gradient(135deg, #22c55e, #3b82f6)'
                  : 'rgba(255,255,255,0.15)',
        }}
      >
        {state.multiplier}x
      </div>

      {/* Streak */}
      {state.streak > 0 && (
        <div className="text-right">
          <span className="text-orange-400 font-bold">{state.streak}</span>
          <span className="text-white/50 text-sm ml-1">streak</span>
        </div>
      )}

      {/* Stars */}
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((s) => (
          <span
            key={s}
            className={`text-lg ${s <= stars ? 'text-yellow-400' : 'text-white/15'}`}
          >
            ★
          </span>
        ))}
      </div>
    </div>
  );
}
