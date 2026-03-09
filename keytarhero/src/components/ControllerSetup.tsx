import { useState, useEffect, useRef, useCallback } from 'react';
import { LANE_COLORS } from '../engine/constants';
import { saveMapping, clearMapping, type GamepadMapping } from '../hooks/useGamepad';

interface ControllerSetupProps {
  onDone: () => void;
}

const STEPS = [
  { label: 'GREEN fret', color: LANE_COLORS[0], key: 'fret0' },
  { label: 'RED fret', color: LANE_COLORS[1], key: 'fret1' },
  { label: 'YELLOW fret', color: LANE_COLORS[2], key: 'fret2' },
  { label: 'BLUE fret', color: LANE_COLORS[3], key: 'fret3' },
  { label: 'ORANGE fret', color: LANE_COLORS[4], key: 'fret4' },
  { label: 'STRUM UP', color: '#fff', key: 'strumUp' },
  { label: 'STRUM DOWN', color: '#fff', key: 'strumDown' },
  { label: 'PAUSE / START', color: '#facc15', key: 'pause' },
] as const;

function getFirstGamepad(): Gamepad | null {
  const pads = navigator.getGamepads();
  for (const pad of pads) {
    if (pad && pad.connected) return pad;
  }
  return null;
}

export default function ControllerSetup({ onDone }: ControllerSetupProps) {
  const [step, setStep] = useState(0);
  const [captured, setCaptured] = useState<number[]>([]);
  const [connected, setConnected] = useState(false);
  const [gamepadName, setGamepadName] = useState('');
  const prevButtonsRef = useRef<boolean[]>([]);
  const done = step >= STEPS.length;

  useEffect(() => {
    const check = () => {
      const pad = getFirstGamepad();
      setConnected(!!pad);
      setGamepadName(pad?.id ?? '');
    };
    check();
    const onConn = () => check();
    window.addEventListener('gamepadconnected', onConn);
    window.addEventListener('gamepaddisconnected', onConn);
    return () => {
      window.removeEventListener('gamepadconnected', onConn);
      window.removeEventListener('gamepaddisconnected', onConn);
    };
  }, []);

  useEffect(() => {
    if (done || !connected) return;
    let rafId = 0;

    function poll() {
      const pad = getFirstGamepad();
      if (!pad) { rafId = requestAnimationFrame(poll); return; }

      const prev = prevButtonsRef.current;
      for (let i = 0; i < pad.buttons.length; i++) {
        const pressed = pad.buttons[i].pressed;
        const wasPrev = prev[i] ?? false;
        if (pressed && !wasPrev) {
          setCaptured(c => [...c, i]);
          setStep(s => s + 1);
          prevButtonsRef.current = pad.buttons.map(b => b.pressed);
          return;
        }
      }
      prevButtonsRef.current = pad.buttons.map(b => b.pressed);
      rafId = requestAnimationFrame(poll);
    }

    rafId = requestAnimationFrame(poll);
    return () => cancelAnimationFrame(rafId);
  }, [done, connected, step]);

  const handleSave = useCallback(() => {
    const mapping: GamepadMapping = {
      frets: [captured[0], captured[1], captured[2], captured[3], captured[4]],
      strumUp: captured[5],
      strumDown: captured[6],
      pause: captured[7],
    };
    saveMapping(mapping);
    onDone();
  }, [captured, onDone]);

  const handleReset = useCallback(() => {
    setStep(0);
    setCaptured([]);
    prevButtonsRef.current = [];
  }, []);

  const handleClear = useCallback(() => {
    clearMapping();
    onDone();
  }, [onDone]);

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-game-bg px-4">
      <h1 className="text-4xl font-heading text-yellow-400 mb-2">Controller Setup</h1>
      <p className="text-white/50 mb-6 text-sm">
        {connected
          ? `Detected: ${gamepadName.slice(0, 50)}`
          : 'Connect your guitar controller and press any button...'}
      </p>

      {!connected && (
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-yellow-400/30 border-t-yellow-400 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-white/40 text-sm mb-6">Waiting for controller...</p>
          <button
            onClick={onDone}
            className="px-6 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors cursor-pointer"
          >
            Back to Menu
          </button>
        </div>
      )}

      {connected && !done && (
        <div className="flex flex-col items-center gap-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-8 w-80 text-center">
            <p className="text-white/40 text-xs mb-2 uppercase tracking-wider">
              Step {step + 1} of {STEPS.length}
            </p>
            <p className="text-3xl font-bold mb-1" style={{ color: STEPS[step].color }}>
              Press {STEPS[step].label}
            </p>
            <p className="text-white/30 text-sm">on your guitar controller</p>
          </div>

          {captured.length > 0 && (
            <div className="flex gap-2 flex-wrap justify-center">
              {captured.map((btnIdx, i) => (
                <span
                  key={i}
                  className="px-3 py-1 rounded-full text-xs font-bold"
                  style={{ backgroundColor: STEPS[i].color + '30', color: STEPS[i].color }}
                >
                  {STEPS[i].label}: btn {btnIdx}
                </span>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white/60 text-sm rounded-lg transition-colors cursor-pointer"
            >
              Start Over
            </button>
            <button
              onClick={onDone}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white/60 text-sm rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {connected && done && (
        <div className="flex flex-col items-center gap-4">
          <div className="bg-white/5 border border-green-500/30 rounded-xl p-6 w-80">
            <p className="text-green-400 text-lg font-bold text-center mb-3">Mapping Complete</p>
            <div className="flex flex-col gap-1">
              {captured.map((btnIdx, i) => (
                <div key={i} className="flex justify-between text-sm">
                  <span style={{ color: STEPS[i].color }}>{STEPS[i].label}</span>
                  <span className="text-white/50">Button {btnIdx}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleSave}
              className="px-6 py-3 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded-lg transition-colors cursor-pointer"
            >
              Save & Play
            </button>
            <button
              onClick={handleReset}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white font-bold rounded-lg transition-colors cursor-pointer"
            >
              Redo
            </button>
            <button
              onClick={handleClear}
              className="px-6 py-3 bg-red-500/20 hover:bg-red-500/30 text-red-400 font-bold rounded-lg transition-colors cursor-pointer"
            >
              Clear & Use Defaults
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
