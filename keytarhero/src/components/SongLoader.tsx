import { useEffect, useRef, useCallback } from 'react';
import type { SongConfig, NoteChart, LyricLine } from '../types';
import { searchLyrics } from '../utils/lrclibApi';
import { generateChart } from '../engine/noteDetector';
import { useYouTube } from '../hooks/useYouTube';
import YouTubePlayer from './YouTubePlayer';

interface SongLoaderProps {
  songConfig: SongConfig;
  onReady: (chart: NoteChart, lyrics: LyricLine[]) => void;
}

export default function SongLoader({ songConfig, onReady }: SongLoaderProps) {
  const startedRef = useRef(false);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const ytControls = useYouTube({
    videoId: songConfig.videoId,
    containerId: 'yt-loader-player',
  });

  const loadSong = useCallback(async () => {
    const [lyrics, duration] = await Promise.all([
      searchLyrics(songConfig.title, songConfig.artist),
      new Promise<number>((resolve) => {
        setTimeout(() => {
          const d = ytControls.getDuration();
          resolve(d > 0 ? d : 180000);
        }, 500);
      }),
    ]);

    const chart = generateChart(
      songConfig.bpm,
      duration,
      songConfig.difficulty,
      lyrics,
      songConfig.title,
      songConfig.artist
    );

    console.log('[SongLoader] Lyrics fetched:', lyrics.length, 'lines. Chart notes:', chart.notes.length);
    onReadyRef.current(chart, lyrics);
  }, [songConfig, ytControls]);

  // Start loading once YT player is ready (or after timeout fallback)
  useEffect(() => {
    const tryStart = () => {
      if (startedRef.current) return;
      startedRef.current = true;
      loadSong();
    };

    // Fallback timeout in case YT doesn't load
    const timeout = setTimeout(tryStart, 5000);

    // Poll for YT ready state
    const interval = setInterval(() => {
      const t = ytControls.getCurrentTimeMs();
      if (t >= 0 && ytControls.getDuration() > 0) {
        clearInterval(interval);
        tryStart();
      }
    }, 300);

    return () => {
      clearTimeout(timeout);
      clearInterval(interval);
    };
  }, [loadSong, ytControls]);

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-game-bg gap-6">
      <YouTubePlayer containerId="yt-loader-player" />

      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-4 border-yellow-400 border-t-transparent rounded-full animate-spin" />
        <h2 className="text-2xl font-heading text-yellow-400">Loading Song...</h2>
        <p className="text-white/50">
          {songConfig.title} — {songConfig.artist}
        </p>
        <p className="text-white/30 text-sm">Fetching lyrics &amp; generating note chart</p>
      </div>
    </div>
  );
}
