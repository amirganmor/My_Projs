import { useRef, useCallback, useState, useEffect } from 'react';
import type { GameState, GameAction } from '../types';
import { useYouTube } from '../hooks/useYouTube';
import { useKeyboard, type KeyboardState } from '../hooks/useKeyboard';
import { useGamepad } from '../hooks/useGamepad';
import { useGameLoop } from '../hooks/useGameLoop';
import GameCanvas, { type GameCanvasHandle } from './GameCanvas';
import Guitarist, { type GuitaristEvent } from './Guitarist';
import LyricsDisplay from './LyricsDisplay';
import ScoreBoard from './ScoreBoard';
import YouTubePlayer from './YouTubePlayer';

function mergeInputs(kb: KeyboardState, gp: KeyboardState): KeyboardState {
  const heldLanes = new Set(kb.heldLanes);
  for (const lane of gp.heldLanes) heldLanes.add(lane);
  return { heldLanes, strummed: kb.strummed || gp.strummed };
}

interface GameViewProps {
  state: GameState;
  dispatch: React.Dispatch<GameAction>;
}

export default function GameView({ state, dispatch }: GameViewProps) {
  const canvasRef = useRef<GameCanvasHandle>(null);
  const [guitaristEvent, setGuitaristEvent] = useState<GuitaristEvent>('idle');
  const [guitaristTime, setGuitaristTime] = useState(performance.now());
  const [ytReady, setYtReady] = useState(false);
  const [durationMs, setDurationMs] = useState(0);

  const ytControls = useYouTube({
    videoId: state.songConfig?.videoId ?? null,
    containerId: 'yt-game-player',
    onReady: () => setYtReady(true),
    onEnd: () => dispatch({ type: 'SONG_END' }),
  });

  useEffect(() => {
    if (ytReady && state.phase === 'PLAYING') {
      if (state.songConfig?.playbackRate && state.songConfig.playbackRate !== 1) {
        ytControls.setPlaybackRate(state.songConfig.playbackRate);
      }
      ytControls.play();
      const d = ytControls.getDuration();
      if (d > 0) setDurationMs(d);
    }
  }, [ytReady, state.phase, ytControls, state.songConfig?.playbackRate]);

  useEffect(() => {
    if (state.phase === 'PAUSED') {
      ytControls.pause();
    } else if (state.phase === 'PLAYING' && ytReady) {
      ytControls.play();
    }
  }, [state.phase, ytReady, ytControls]);

  const handlePause = useCallback(() => {
    if (state.phase === 'PLAYING') {
      dispatch({ type: 'PAUSE' });
    } else if (state.phase === 'PAUSED') {
      dispatch({ type: 'RESUME' });
    }
  }, [state.phase, dispatch]);

  const { getState: getKeyboard, consumeStrum: consumeKbStrum } = useKeyboard({
    enabled: state.phase === 'PLAYING',
    onPause: handlePause,
  });

  const { getState: getGamepadState, consumeStrum: consumeGpStrum } = useGamepad({
    enabled: state.phase === 'PLAYING',
    onPause: handlePause,
  });

  const getMergedInput = useCallback((): KeyboardState => {
    return mergeInputs(getKeyboard(), getGamepadState());
  }, [getKeyboard, getGamepadState]);

  const consumeMergedStrum = useCallback(() => {
    consumeKbStrum();
    consumeGpStrum();
  }, [consumeKbStrum, consumeGpStrum]);

  const drawFrame = useCallback(
    (songTimeMs: number, heldLanes: Set<number>) => {
      canvasRef.current?.draw(songTimeMs, heldLanes);
    },
    []
  );

  const { guitaristEventRef } = useGameLoop({
    state,
    dispatch,
    ytControls,
    getKeyboard: getMergedInput,
    consumeStrum: consumeMergedStrum,
    drawFrame,
  });

  useEffect(() => {
    const interval = setInterval(() => {
      const evt = guitaristEventRef.current;
      if (evt) {
        setGuitaristEvent(evt.type as GuitaristEvent);
        setGuitaristTime(evt.time);
        guitaristEventRef.current = null;
      }
    }, 50);
    return () => clearInterval(interval);
  }, [guitaristEventRef]);

  return (
    <div className="w-full h-full flex items-center justify-center bg-game-bg relative overflow-hidden">
      <YouTubePlayer containerId="yt-game-player" backgroundMode />

      <button
        onClick={() => dispatch({ type: 'PAUSE' })}
        className="absolute top-4 left-4 z-50 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/60 hover:text-white text-sm font-bold transition-colors cursor-pointer backdrop-blur-sm border border-white/10"
      >
        ✕ Menu
      </button>

      {/* Main game layout: Lyrics | Guitarist | Highway | Score */}
      <div
        style={{
          display: 'flex',
          alignItems: 'stretch',
          gap: 12,
          zIndex: 10,
          position: 'relative',
          height: 600,
        }}
      >
        <LyricsDisplay
          lyrics={state.lyrics}
          currentTimeMs={state.songTimeMs}
          durationMs={durationMs}
        />

        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <Guitarist
            event={guitaristEvent}
            eventTime={guitaristTime}
            bpm={state.songConfig?.bpm ?? 120}
            streak={state.streak}
          />
        </div>

        <div style={{ position: 'relative', alignSelf: 'flex-end' }}>
          <GameCanvas ref={canvasRef} state={state} />
        </div>

        <div style={{ alignSelf: 'flex-start', paddingTop: 16 }}>
          <ScoreBoard state={state} />
        </div>
      </div>

      {state.phase === 'PAUSED' && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-black/70 backdrop-blur-sm">
          <h2 className="text-4xl font-heading text-yellow-400 mb-6">PAUSED</h2>
          <div className="flex flex-col gap-3">
            <button
              onClick={() => dispatch({ type: 'RESUME' })}
              className="px-8 py-3 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded-lg transition-colors cursor-pointer"
            >
              Resume
            </button>
            <button
              onClick={() => dispatch({ type: 'RESET' })}
              className="px-8 py-3 bg-white/10 hover:bg-white/20 text-white font-bold rounded-lg transition-colors cursor-pointer"
            >
              Quit to Menu
            </button>
          </div>
          <p className="text-white/40 text-sm mt-4">Press ESC to resume</p>
        </div>
      )}
    </div>
  );
}
