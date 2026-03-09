import { useState, useEffect } from 'react';
import type { SongConfig, Difficulty } from '../types';
import { extractVideoId, getVideoMeta } from '../utils/youtubeUtils';
import { LANE_COLORS } from '../engine/constants';
import { loadMapping } from '../hooks/useGamepad';

interface StartScreenProps {
  onStartLoad: (config: SongConfig) => void;
  onConfigureController: () => void;
}

const LANE_LABELS = ['A', 'S', 'D', 'F', 'G'];

export default function StartScreen({ onStartLoad, onConfigureController }: StartScreenProps) {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [artist, setArtist] = useState('');
  const [bpm, setBpm] = useState('120');
  const [difficulty, setDifficulty] = useState<Difficulty>('medium');
  const [speed, setSpeed] = useState('1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [gamepadConnected, setGamepadConnected] = useState(false);
  const [gamepadName, setGamepadName] = useState('');
  const hasMapping = loadMapping() !== null;

  useEffect(() => {
    const check = () => {
      const pads = navigator.getGamepads();
      for (const pad of pads) {
        if (pad && pad.connected) {
          setGamepadConnected(true);
          setGamepadName(pad.id);
          return;
        }
      }
      setGamepadConnected(false);
      setGamepadName('');
    };
    check();
    const interval = setInterval(check, 1000);
    const onConn = () => check();
    window.addEventListener('gamepadconnected', onConn);
    window.addEventListener('gamepaddisconnected', onConn);
    return () => {
      clearInterval(interval);
      window.removeEventListener('gamepadconnected', onConn);
      window.removeEventListener('gamepaddisconnected', onConn);
    };
  }, []);

  const handleUrlBlur = async () => {
    const id = extractVideoId(url);
    if (!id) return;
    try {
      const meta = await getVideoMeta(id);
      if (!title) setTitle(meta.title);
      if (!artist) setArtist(meta.author);
    } catch {
      // oEmbed may fail for some videos
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const videoId = extractVideoId(url);
    if (!videoId) {
      setError('Please enter a valid YouTube URL');
      return;
    }
    if (!title.trim()) {
      setError('Please enter a song title');
      return;
    }
    setLoading(true);
    setError('');
    onStartLoad({
      videoId,
      title: title.trim(),
      artist: artist.trim() || 'Unknown',
      bpm: parseInt(bpm) || 120,
      difficulty,
      playbackRate: parseFloat(speed) || 1,
    });
  };

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-game-bg px-4">
      {/* Title */}
      <h1
        className="text-6xl font-heading mb-2 tracking-wider animate-[pulse-glow_3s_ease-in-out_infinite]"
        style={{ color: '#facc15' }}
      >
        KEYTAR HERO
      </h1>
      <p className="text-white/50 mb-8 text-lg">Shred to any song on YouTube</p>

      {/* Key layout display */}
      <div className="flex gap-2 mb-8">
        {LANE_LABELS.map((key, i) => (
          <div
            key={key}
            className="w-12 h-12 rounded-lg flex items-center justify-center text-lg font-bold border-2 transition-all"
            style={{
              borderColor: LANE_COLORS[i],
              color: LANE_COLORS[i],
              boxShadow: `0 0 10px ${LANE_COLORS[i]}40`,
            }}
          >
            {key}
          </div>
        ))}
        <div className="w-28 h-12 rounded-lg flex items-center justify-center text-sm font-bold border-2 border-white/40 text-white/60 ml-2">
          SPACE = Strum
        </div>
      </div>

      {/* Controller status */}
      <div className="flex items-center gap-3 mb-6">
        <div className="flex items-center gap-2">
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: gamepadConnected ? '#22c55e' : '#666' }}
          />
          <span className="text-sm" style={{ color: gamepadConnected ? '#22c55e' : '#666' }}>
            {gamepadConnected
              ? `Guitar: ${gamepadName.slice(0, 35)}${gamepadName.length > 35 ? '...' : ''}`
              : 'No controller detected'}
          </span>
        </div>
        <button
          type="button"
          onClick={onConfigureController}
          className="px-3 py-1 text-xs rounded-lg bg-white/10 hover:bg-white/20 text-white/60 hover:text-white transition-colors cursor-pointer border border-white/10"
        >
          {hasMapping ? 'Recalibrate' : 'Configure Controller'}
        </button>
      </div>

      {/* Song loader form */}
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md flex flex-col gap-3 bg-white/5 p-6 rounded-xl border border-white/10"
      >
        <input
          type="text"
          placeholder="Paste YouTube URL..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onBlur={handleUrlBlur}
          className="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/30 focus:outline-none focus:border-yellow-400/60 transition-colors"
        />

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Song title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="flex-1 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/30 focus:outline-none focus:border-yellow-400/60 transition-colors"
          />
          <input
            type="text"
            placeholder="Artist"
            value={artist}
            onChange={(e) => setArtist(e.target.value)}
            className="flex-1 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/30 focus:outline-none focus:border-yellow-400/60 transition-colors"
          />
        </div>

        <div className="flex gap-2">
          <div className="flex-1">
            <label className="text-xs text-white/40 mb-1 block">BPM</label>
            <input
              type="number"
              value={bpm}
              onChange={(e) => setBpm(e.target.value)}
              min="60"
              max="300"
              className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white focus:outline-none focus:border-yellow-400/60 transition-colors"
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-white/40 mb-1 block">Difficulty</label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Difficulty)}
              className="w-full px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white focus:outline-none focus:border-yellow-400/60 transition-colors"
            >
              <option value="beginner" className="bg-gray-900">Beginner</option>
              <option value="casual" className="bg-gray-900">Casual</option>
              <option value="easy" className="bg-gray-900">Easy</option>
              <option value="medium" className="bg-gray-900">Medium</option>
              <option value="hard" className="bg-gray-900">Hard</option>
            </select>
          </div>
        </div>

        <div>
          <label className="text-xs text-white/40 mb-1 block">Practice Speed</label>
          <div className="flex gap-2">
            {['0.5', '0.75', '1'].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSpeed(s)}
                className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors cursor-pointer ${
                  speed === s
                    ? 'bg-yellow-500 text-black'
                    : 'bg-white/10 text-white/60 hover:bg-white/20'
                }`}
              >
                {s === '1' ? 'Normal' : `${parseFloat(s) * 100}%`}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 rounded-lg bg-yellow-500 hover:bg-yellow-400 text-black font-bold text-lg transition-colors disabled:opacity-50 cursor-pointer"
        >
          {loading ? 'Loading...' : "Let's Rock!"}
        </button>
      </form>
    </div>
  );
}
