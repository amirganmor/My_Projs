import { useRef, useEffect, useCallback } from 'react';
import type { GameState, GameAction, HitEffect, Particle } from '../types';
import type { YouTubeControls } from './useYouTube';
import type { KeyboardState } from './useKeyboard';
import { findHittableNotes, findMissedNotes } from '../engine/hitDetection';
import { getLaneCenterX, HIT_ZONE_Y, LANE_COLORS, EFFECT_DURATION_MS } from '../engine/constants';

interface UseGameLoopOptions {
  state: GameState;
  dispatch: React.Dispatch<GameAction>;
  ytControls: YouTubeControls;
  getKeyboard: () => KeyboardState;
  consumeStrum: () => void;
  drawFrame: (songTimeMs: number, heldLanes: Set<number>) => void;
}

function makeHitEffect(
  lane: number,
  quality: 'PERFECT' | 'GOOD' | 'MISS',
  now: number
): HitEffect {
  return {
    id: `eff-${now}-${lane}-${Math.random()}`,
    lane,
    quality,
    timeCreated: now,
    x: getLaneCenterX(lane),
    y: HIT_ZONE_Y,
  };
}

function makeParticles(lane: number, count: number): Particle[] {
  const cx = getLaneCenterX(lane);
  const color = LANE_COLORS[lane];
  return Array.from({ length: count }, () => ({
    x: cx,
    y: HIT_ZONE_Y,
    vx: (Math.random() - 0.5) * 6,
    vy: -Math.random() * 5 - 2,
    life: 1,
    color,
    size: Math.random() * 4 + 2,
  }));
}

export function useGameLoop({
  state,
  dispatch,
  ytControls,
  getKeyboard,
  consumeStrum,
  drawFrame,
}: UseGameLoopOptions) {
  const rafRef = useRef<number>(0);
  const lastCleanup = useRef(0);
  const guitaristEventRef = useRef<{ type: 'strum' | 'perfect' | 'miss'; time: number } | null>(null);

  const loop = useCallback(() => {
    if (state.phase !== 'PLAYING') return;

    const songTimeMs = ytControls.getCurrentTimeMs();
    dispatch({ type: 'UPDATE_TIME', timeMs: songTimeMs });

    const kb = getKeyboard();

    // Process strums
    if (kb.strummed && state.chart) {
      consumeStrum();
      const hits = findHittableNotes(state.chart.notes, songTimeMs, kb.heldLanes);

      if (hits.length > 0) {
        for (const { note, quality } of hits) {
          const effect = makeHitEffect(note.lane, quality, performance.now());
          const particles = quality === 'PERFECT' ? makeParticles(note.lane, 12) : makeParticles(note.lane, 5);
          dispatch({ type: 'NOTE_HIT', noteId: note.id, quality, effect, particles });
          guitaristEventRef.current = {
            type: quality === 'PERFECT' ? 'perfect' : 'strum',
            time: performance.now(),
          };
        }
      } else {
        // Strummed but no note to hit — miss feedback
        guitaristEventRef.current = { type: 'miss', time: performance.now() };
      }
    } else if (kb.strummed) {
      consumeStrum();
    }

    // Auto-miss notes that are past the window
    if (state.chart) {
      const missed = findMissedNotes(state.chart.notes, songTimeMs);
      for (const note of missed) {
        const effect = makeHitEffect(note.lane, 'MISS', performance.now());
        dispatch({ type: 'NOTE_MISS', noteId: note.id, effect });
      }
    }

    // Cleanup old effects periodically
    const now = performance.now();
    if (now - lastCleanup.current > EFFECT_DURATION_MS) {
      lastCleanup.current = now;
      dispatch({ type: 'CLEANUP_EFFECTS', now });
    }

    drawFrame(songTimeMs, kb.heldLanes);
    rafRef.current = requestAnimationFrame(loop);
  }, [state.phase, state.chart, ytControls, getKeyboard, consumeStrum, dispatch, drawFrame]);

  useEffect(() => {
    if (state.phase === 'PLAYING') {
      rafRef.current = requestAnimationFrame(loop);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [state.phase, loop]);

  return { guitaristEventRef };
}
