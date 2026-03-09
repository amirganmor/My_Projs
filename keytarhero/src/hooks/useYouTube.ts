import { useEffect, useRef, useState, useCallback } from 'react';

let apiLoaded = false;
let apiReady = false;
const readyCallbacks: (() => void)[] = [];

function loadYouTubeApi(): Promise<void> {
  if (apiReady) return Promise.resolve();
  return new Promise((resolve) => {
    if (apiLoaded) {
      readyCallbacks.push(resolve);
      return;
    }
    apiLoaded = true;
    readyCallbacks.push(resolve);

    const prev = (window as unknown as Record<string, unknown>).onYouTubeIframeAPIReady as (() => void) | undefined;
    (window as unknown as Record<string, unknown>).onYouTubeIframeAPIReady = () => {
      prev?.();
      apiReady = true;
      readyCallbacks.forEach((cb) => cb());
      readyCallbacks.length = 0;
    };

    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(script);
  });
}

export interface YouTubeControls {
  play: () => void;
  pause: () => void;
  seekTo: (ms: number) => void;
  getCurrentTimeMs: () => number;
  setPlaybackRate: (rate: number) => void;
  getDuration: () => number;
}

interface UseYouTubeOptions {
  videoId: string | null;
  containerId: string;
  onReady?: () => void;
  onEnd?: () => void;
  onStateChange?: (state: number) => void;
}

export function useYouTube({
  videoId,
  containerId,
  onReady,
  onEnd,
  onStateChange,
}: UseYouTubeOptions): YouTubeControls {
  const playerRef = useRef<YT.Player | null>(null);
  const [, setReady] = useState(false);

  const onReadyRef = useRef(onReady);
  const onEndRef = useRef(onEnd);
  const onStateChangeRef = useRef(onStateChange);
  onReadyRef.current = onReady;
  onEndRef.current = onEnd;
  onStateChangeRef.current = onStateChange;

  useEffect(() => {
    if (!videoId) return;

    let destroyed = false;

    loadYouTubeApi().then(() => {
      if (destroyed) return;

      if (playerRef.current) {
        playerRef.current.destroy();
      }

      playerRef.current = new YT.Player(containerId, {
        videoId,
        width: 1,
        height: 1,
        playerVars: {
          autoplay: 0,
          controls: 0,
          disablekb: 1,
          fs: 0,
          modestbranding: 1,
          rel: 0,
          iv_load_policy: 3,
          playsinline: 1,
        },
        events: {
          onReady: () => {
            setReady(true);
            onReadyRef.current?.();
          },
          onStateChange: (e: YT.OnStateChangeEvent) => {
            onStateChangeRef.current?.(e.data);
            if (e.data === YT.PlayerState.ENDED) {
              onEndRef.current?.();
            }
          },
        },
      });
    });

    return () => {
      destroyed = true;
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
    };
  }, [videoId, containerId]);

  const play = useCallback(() => playerRef.current?.playVideo(), []);
  const pause = useCallback(() => playerRef.current?.pauseVideo(), []);
  const seekTo = useCallback((ms: number) => playerRef.current?.seekTo(ms / 1000, true), []);
  const getCurrentTimeMs = useCallback(() => (playerRef.current?.getCurrentTime() ?? 0) * 1000, []);
  const setPlaybackRate = useCallback((rate: number) => playerRef.current?.setPlaybackRate(rate), []);
  const getDuration = useCallback(() => (playerRef.current?.getDuration() ?? 0) * 1000, []);

  return { play, pause, seekTo, getCurrentTimeMs, setPlaybackRate, getDuration };
}
