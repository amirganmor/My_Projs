import { useReducer, useCallback, useState } from 'react';
import type { GameState, GameAction, SongConfig, NoteChart, LyricLine } from './types';
import { getMultiplier, SCORE_PERFECT, SCORE_GOOD, EFFECT_DURATION_MS } from './engine/constants';
import StartScreen from './components/StartScreen';
import SongLoader from './components/SongLoader';
import GameView from './components/GameView';
import ResultsScreen from './components/ResultsScreen';
import ControllerSetup from './components/ControllerSetup';

const initialState: GameState = {
  phase: 'MENU',
  score: 0,
  streak: 0,
  multiplier: 1,
  maxStreak: 0,
  totalHits: 0,
  perfectHits: 0,
  totalNotes: 0,
  songTimeMs: 0,
  chart: null,
  lyrics: [],
  songConfig: null,
  hitEffects: [],
  particles: [],
};

function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'START_LOADING':
      return { ...state, phase: 'LOADING', songConfig: action.songConfig };

    case 'START_PLAYING':
      console.log('[App] START_PLAYING — lyrics:', action.lyrics.length, 'notes:', action.chart.notes.length);
      return {
        ...state,
        phase: 'PLAYING',
        chart: action.chart,
        lyrics: action.lyrics,
        totalNotes: action.chart.notes.length,
        score: 0,
        streak: 0,
        multiplier: 1,
        maxStreak: 0,
        totalHits: 0,
        perfectHits: 0,
        songTimeMs: 0,
        hitEffects: [],
        particles: [],
      };

    case 'PAUSE':
      return state.phase === 'PLAYING' ? { ...state, phase: 'PAUSED' } : state;

    case 'RESUME':
      return state.phase === 'PAUSED' ? { ...state, phase: 'PLAYING' } : state;

    case 'UPDATE_TIME':
      return { ...state, songTimeMs: action.timeMs };

    case 'NOTE_HIT': {
      const points = (action.quality === 'PERFECT' ? SCORE_PERFECT : SCORE_GOOD) * state.multiplier;
      const newStreak = state.streak + 1;
      const chart = state.chart
        ? {
            ...state.chart,
            notes: state.chart.notes.map((n) =>
              n.id === action.noteId ? { ...n, hit: true } : n
            ),
          }
        : null;
      return {
        ...state,
        chart,
        score: state.score + points,
        streak: newStreak,
        multiplier: getMultiplier(newStreak),
        maxStreak: Math.max(state.maxStreak, newStreak),
        totalHits: state.totalHits + 1,
        perfectHits: state.perfectHits + (action.quality === 'PERFECT' ? 1 : 0),
        hitEffects: [...state.hitEffects, action.effect],
        particles: [...state.particles, ...action.particles],
      };
    }

    case 'NOTE_MISS': {
      const chart = state.chart
        ? {
            ...state.chart,
            notes: state.chart.notes.map((n) =>
              n.id === action.noteId ? { ...n, missed: true } : n
            ),
          }
        : null;
      return {
        ...state,
        chart,
        streak: 0,
        multiplier: 1,
        hitEffects: [...state.hitEffects, action.effect],
      };
    }

    case 'CLEANUP_EFFECTS':
      return {
        ...state,
        hitEffects: state.hitEffects.filter(
          (e) => action.now - e.timeCreated < EFFECT_DURATION_MS
        ),
        particles: state.particles.filter((p) => p.life > 0),
      };

    case 'SONG_END':
      return { ...state, phase: 'RESULTS' };

    case 'RESET':
      return initialState;

    default:
      return state;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(gameReducer, initialState);
  const [showControllerSetup, setShowControllerSetup] = useState(false);

  const handleLoadSong = useCallback((config: SongConfig) => {
    dispatch({ type: 'START_LOADING', songConfig: config });
  }, []);

  const handleGameReady = useCallback((chart: NoteChart, lyrics: LyricLine[]) => {
    dispatch({ type: 'START_PLAYING', chart, lyrics });
  }, []);

  const handleReset = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

  const handlePlayAgain = useCallback(() => {
    if (state.songConfig) {
      dispatch({ type: 'START_LOADING', songConfig: state.songConfig });
    }
  }, [state.songConfig]);

  if (showControllerSetup) {
    return (
      <div className="w-full h-full bg-game-bg">
        <ControllerSetup onDone={() => setShowControllerSetup(false)} />
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-game-bg">
      {state.phase === 'MENU' && (
        <StartScreen
          onStartLoad={handleLoadSong}
          onConfigureController={() => setShowControllerSetup(true)}
        />
      )}

      {state.phase === 'LOADING' && state.songConfig && (
        <SongLoader songConfig={state.songConfig} onReady={handleGameReady} />
      )}

      {(state.phase === 'PLAYING' || state.phase === 'PAUSED') && (
        <GameView state={state} dispatch={dispatch} />
      )}

      {state.phase === 'RESULTS' && (
        <ResultsScreen
          state={state}
          onPlayAgain={handlePlayAgain}
          onNewSong={handleReset}
        />
      )}
    </div>
  );
}
