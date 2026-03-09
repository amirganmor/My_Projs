import { useEffect, useRef, useCallback } from 'react';
import { LANE_KEYS, STRUM_KEY, PAUSE_KEY } from '../engine/constants';

export interface KeyboardState {
  heldLanes: Set<number>;
  strummed: boolean;
}

interface UseKeyboardOptions {
  enabled: boolean;
  onPause?: () => void;
}

export function useKeyboard({ enabled, onPause }: UseKeyboardOptions) {
  const heldLanesRef = useRef<Set<number>>(new Set());
  const strummedRef = useRef(false);
  const onPauseRef = useRef(onPause);
  onPauseRef.current = onPause;

  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.repeat) return;

      const key = e.key.toLowerCase();

      if (key === PAUSE_KEY) {
        e.preventDefault();
        onPauseRef.current?.();
        return;
      }

      const laneIdx = LANE_KEYS.indexOf(key as typeof LANE_KEYS[number]);
      if (laneIdx !== -1) {
        e.preventDefault();
        heldLanesRef.current.add(laneIdx);
      }

      if (key === STRUM_KEY) {
        e.preventDefault();
        strummedRef.current = true;
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      const laneIdx = LANE_KEYS.indexOf(key as typeof LANE_KEYS[number]);
      if (laneIdx !== -1) {
        heldLanesRef.current.delete(laneIdx);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [enabled]);

  const getState = useCallback((): KeyboardState => {
    return {
      heldLanes: new Set(heldLanesRef.current),
      strummed: strummedRef.current,
    };
  }, []);

  const consumeStrum = useCallback(() => {
    strummedRef.current = false;
  }, []);

  return { getState, consumeStrum, heldLanesRef };
}
