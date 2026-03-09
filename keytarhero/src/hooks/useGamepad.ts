import { useEffect, useRef, useCallback } from 'react';
import type { KeyboardState } from './useKeyboard';

export interface GamepadMapping {
  frets: [number, number, number, number, number];
  strumUp: number;
  strumDown: number;
  pause: number;
}

const STORAGE_KEY = 'keytarhero-gamepad-mapping';

const DEFAULT_MAPPING: GamepadMapping = {
  frets: [0, 1, 2, 3, 4],
  strumUp: 12,
  strumDown: 13,
  pause: 9,
};

export function loadMapping(): GamepadMapping | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as GamepadMapping;
  } catch {
    return null;
  }
}

export function saveMapping(mapping: GamepadMapping) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(mapping));
}

export function clearMapping() {
  localStorage.removeItem(STORAGE_KEY);
}

function getFirstGamepad(): Gamepad | null {
  const pads = navigator.getGamepads();
  for (const pad of pads) {
    if (pad && pad.connected) return pad;
  }
  return null;
}

interface UseGamepadOptions {
  enabled: boolean;
  onPause?: () => void;
}

export function useGamepad({ enabled, onPause }: UseGamepadOptions) {
  const heldLanesRef = useRef<Set<number>>(new Set());
  const strummedRef = useRef(false);
  const prevStrumRef = useRef(false);
  const prevPauseRef = useRef(false);
  const onPauseRef = useRef(onPause);
  const connectedRef = useRef(false);
  const gamepadNameRef = useRef('');
  onPauseRef.current = onPause;

  useEffect(() => {
    const onConnect = (e: GamepadEvent) => {
      connectedRef.current = true;
      gamepadNameRef.current = e.gamepad.id;
      console.log('[Gamepad] Connected:', e.gamepad.id, '—', e.gamepad.buttons.length, 'buttons,', e.gamepad.axes.length, 'axes');
    };
    const onDisconnect = () => {
      connectedRef.current = false;
      gamepadNameRef.current = '';
      console.log('[Gamepad] Disconnected');
    };
    window.addEventListener('gamepadconnected', onConnect);
    window.addEventListener('gamepaddisconnected', onDisconnect);

    const pad = getFirstGamepad();
    if (pad) {
      connectedRef.current = true;
      gamepadNameRef.current = pad.id;
    }

    return () => {
      window.removeEventListener('gamepadconnected', onConnect);
      window.removeEventListener('gamepaddisconnected', onDisconnect);
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const mapping = loadMapping() ?? DEFAULT_MAPPING;
    let rafId = 0;

    function poll() {
      const pad = getFirstGamepad();
      if (!pad) {
        rafId = requestAnimationFrame(poll);
        return;
      }

      const lanes = new Set<number>();
      for (let i = 0; i < 5; i++) {
        const btnIdx = mapping.frets[i];
        if (btnIdx < pad.buttons.length && pad.buttons[btnIdx].pressed) {
          lanes.add(i);
        }
      }
      heldLanesRef.current = lanes;

      const strumNow =
        (mapping.strumUp < pad.buttons.length && pad.buttons[mapping.strumUp].pressed) ||
        (mapping.strumDown < pad.buttons.length && pad.buttons[mapping.strumDown].pressed);

      if (strumNow && !prevStrumRef.current) {
        strummedRef.current = true;
      }
      prevStrumRef.current = strumNow;

      const pauseNow = mapping.pause < pad.buttons.length && pad.buttons[mapping.pause].pressed;
      if (pauseNow && !prevPauseRef.current) {
        onPauseRef.current?.();
      }
      prevPauseRef.current = pauseNow;

      rafId = requestAnimationFrame(poll);
    }

    rafId = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(rafId);
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

  return { getState, consumeStrum, connectedRef, gamepadNameRef };
}

export function useGamepadConnected() {
  const connectedRef = useRef(false);
  const nameRef = useRef('');

  useEffect(() => {
    const check = () => {
      const pad = getFirstGamepad();
      connectedRef.current = !!pad;
      nameRef.current = pad?.id ?? '';
    };
    check();
    const onConnect = (e: GamepadEvent) => {
      connectedRef.current = true;
      nameRef.current = e.gamepad.id;
    };
    const onDisconnect = () => {
      connectedRef.current = false;
      nameRef.current = '';
    };
    window.addEventListener('gamepadconnected', onConnect);
    window.addEventListener('gamepaddisconnected', onDisconnect);
    return () => {
      window.removeEventListener('gamepadconnected', onConnect);
      window.removeEventListener('gamepaddisconnected', onDisconnect);
    };
  }, []);

  return { connectedRef, nameRef };
}
