import { useRef, useEffect, useMemo } from 'react';
import type { LyricLine } from '../types';

interface LyricsDisplayProps {
  lyrics: LyricLine[];
  currentTimeMs: number;
  durationMs: number;
}

function findCurrentIndex(lyrics: LyricLine[], timeMs: number): number {
  if (lyrics.length === 0) return -1;
  let lo = 0;
  let hi = lyrics.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (lyrics[mid].timeMs <= timeMs) {
      idx = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return idx;
}

export default function LyricsDisplay({ lyrics, currentTimeMs, durationMs }: LyricsDisplayProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const displayLyrics = useMemo(() => {
    const synced = lyrics.filter(l => l.timeMs > 0);
    if (synced.length >= 3) return synced;
    if (lyrics.length > 0) return lyrics;
    return [];
  }, [lyrics]);

  const hasSynced = displayLyrics.length > 0 && displayLyrics.some(l => l.timeMs > 0);
  const currentIndex = hasSynced
    ? findCurrentIndex(displayLyrics, currentTimeMs)
    : (displayLyrics.length > 0 ? 0 : -1);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || currentIndex < 0) return;
    const children = container.querySelectorAll('[data-lyric]');
    const lineEl = children[currentIndex] as HTMLElement | undefined;
    if (!lineEl) return;
    const targetScroll = lineEl.offsetTop - container.clientHeight / 2 + lineEl.clientHeight / 2;
    container.scrollTo({ top: Math.max(0, targetScroll), behavior: 'smooth' });
  }, [currentIndex]);

  const progress = durationMs > 0 ? Math.min(1, currentTimeMs / durationMs) : 0;

  return (
    <div
      style={{
        width: 200,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(0,0,0,0.7)',
        borderRadius: 12,
        border: '1px solid rgba(255,255,255,0.15)',
        overflow: 'hidden',
        flexShrink: 0,
        position: 'relative',
        zIndex: 20,
      }}
    >
      {/* Progress bar */}
      <div style={{ height: 4, width: '100%', background: 'rgba(255,255,255,0.1)', flexShrink: 0 }}>
        <div style={{ height: '100%', width: `${progress * 100}%`, background: '#facc15', transition: 'width 0.3s' }} />
      </div>

      {/* Header */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.1)', flexShrink: 0 }}>
        <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700 }}>
          Lyrics {displayLyrics.length > 0 ? `(${displayLyrics.length})` : ''}
        </span>
      </div>

      {displayLyrics.length === 0 ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 16, gap: 8 }}>
          <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12, textAlign: 'center' }}>
            No lyrics found for this song.
          </p>
          <p style={{ color: 'rgba(255,255,255,0.15)', fontSize: 10, textAlign: 'center' }}>
            Tip: Make sure the Song Title and Artist fields are filled in correctly on the start screen.
          </p>
          <p style={{ color: 'rgba(255,255,255,0.1)', fontSize: 9, textAlign: 'center' }}>
            Total lyrics received: {lyrics.length}
          </p>
        </div>
      ) : (
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px 14px',
            scrollbarWidth: 'none',
            msOverflowStyle: 'none',
          }}
        >
          {/* Top spacer */}
          <div style={{ height: '35%' }} />

          {displayLyrics.map((line, i) => {
            const isCurrent = i === currentIndex;
            const isPast = hasSynced && currentIndex >= 0 && i < currentIndex;
            const distance = currentIndex >= 0 ? Math.abs(i - currentIndex) : i;

            let opacity = 0.25;
            if (isCurrent) opacity = 1;
            else if (isPast) opacity = Math.max(0.12, 0.3 - distance * 0.03);
            else if (distance <= 2) opacity = 0.5;
            else opacity = Math.max(0.15, 0.4 - distance * 0.05);

            let wipePercent = 0;
            if (isCurrent && hasSynced) {
              const lineStart = line.timeMs;
              const lineEnd = displayLyrics[i + 1]?.timeMs ?? lineStart + 4000;
              const dur = Math.max(1, lineEnd - lineStart);
              wipePercent = Math.min(1, Math.max(0, (currentTimeMs - lineStart) / dur));
            }

            return (
              <div
                key={`lyric-${i}-${line.timeMs}`}
                data-lyric=""
                style={{
                  opacity,
                  fontSize: isCurrent ? 14 : 11,
                  fontWeight: isCurrent ? 700 : 400,
                  color: isCurrent ? '#facc15' : isPast ? '#666' : '#aaa',
                  marginBottom: 10,
                  lineHeight: 1.4,
                  transition: 'all 0.3s ease',
                  textShadow: isCurrent ? '0 0 10px rgba(250,204,21,0.5)' : 'none',
                }}
              >
                {isCurrent && hasSynced ? (
                  <span style={{ position: 'relative', display: 'inline-block' }}>
                    <span style={{ color: 'rgba(255,255,255,0.2)' }}>{line.text}</span>
                    <span
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        overflow: 'hidden',
                        whiteSpace: 'nowrap',
                        width: `${wipePercent * 100}%`,
                      }}
                    >
                      <span style={{ color: '#facc15' }}>{line.text}</span>
                    </span>
                  </span>
                ) : (
                  line.text
                )}
              </div>
            );
          })}

          {/* Bottom spacer */}
          <div style={{ height: '35%' }} />
        </div>
      )}
    </div>
  );
}
