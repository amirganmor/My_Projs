import { useRef, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import type { GameState } from '../types';
import {
  CANVAS_WIDTH,
  HIGHWAY_HEIGHT,
  HIT_ZONE_Y,
  LANE_WIDTH,
  NOTE_HEIGHT,
  NOTE_WIDTH,
  HIT_CIRCLE_RADIUS,
  NOTE_FALL_DURATION_MS,
  LANE_COLORS,
  EFFECT_DURATION_MS,
  getLaneCenterX,
} from '../engine/constants';

export interface GameCanvasHandle {
  draw: (songTimeMs: number, heldLanes: Set<number>) => void;
}

interface GameCanvasProps {
  state: GameState;
}

const GameCanvas = forwardRef<GameCanvasHandle, GameCanvasProps>(({ state }, ref) => {
  const bgCanvasRef = useRef<HTMLCanvasElement>(null);
  const noteCanvasRef = useRef<HTMLCanvasElement>(null);
  const fxCanvasRef = useRef<HTMLCanvasElement>(null);
  const bgDrawn = useRef(false);

  // Draw the static background once
  const drawBackground = useCallback(() => {
    const canvas = bgCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    // Dark gradient
    const grad = ctx.createLinearGradient(0, 0, 0, HIGHWAY_HEIGHT);
    grad.addColorStop(0, '#0a0a14');
    grad.addColorStop(1, '#0f0f1a');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, CANVAS_WIDTH, HIGHWAY_HEIGHT);

    // Lane dividers with glow
    for (let i = 0; i <= 5; i++) {
      const x = i * LANE_WIDTH;
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, HIGHWAY_HEIGHT);
      ctx.stroke();
    }

    // Lane center glow lines
    for (let i = 0; i < 5; i++) {
      const cx = getLaneCenterX(i);
      ctx.strokeStyle = LANE_COLORS[i] + '15';
      ctx.lineWidth = LANE_WIDTH - 4;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, HIGHWAY_HEIGHT);
      ctx.stroke();
    }

    // Horizontal grid lines for motion feel
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.lineWidth = 1;
    for (let y = 0; y < HIGHWAY_HEIGHT; y += 40) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(CANVAS_WIDTH, y);
      ctx.stroke();
    }

    // Hit zone bar
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(0, HIT_ZONE_Y - 2, CANVAS_WIDTH, 4);

    bgDrawn.current = true;
  }, []);

  useEffect(() => {
    drawBackground();
  }, [drawBackground]);

  const drawNotes = useCallback(
    (ctx: CanvasRenderingContext2D, songTimeMs: number, heldLanes: Set<number>) => {
      ctx.clearRect(0, 0, CANVAS_WIDTH, HIGHWAY_HEIGHT);

      if (!state.chart) return;

      // Draw falling notes
      for (const note of state.chart.notes) {
        if (note.hit || note.missed) continue;

        const relativeTime = note.timeMs - songTimeMs;
        if (relativeTime > NOTE_FALL_DURATION_MS || relativeTime < -200) continue;

        const progress = 1 - relativeTime / NOTE_FALL_DURATION_MS;
        const y = progress * HIT_ZONE_Y;
        const cx = getLaneCenterX(note.lane);
        const color = LANE_COLORS[note.lane];

        // Glow
        ctx.shadowColor = color;
        ctx.shadowBlur = 12;

        // Note body
        ctx.fillStyle = color;
        ctx.beginPath();
        const r = 6;
        const x = cx - NOTE_WIDTH / 2;
        const ny = y - NOTE_HEIGHT / 2;
        ctx.roundRect(x, ny, NOTE_WIDTH, NOTE_HEIGHT, r);
        ctx.fill();

        // Inner highlight
        ctx.shadowBlur = 0;
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.beginPath();
        ctx.roundRect(x + 4, ny + 3, NOTE_WIDTH - 8, NOTE_HEIGHT / 2 - 2, 3);
        ctx.fill();
      }

      ctx.shadowBlur = 0;

      // Draw hit zone circles
      for (let i = 0; i < 5; i++) {
        const cx = getLaneCenterX(i);
        const held = heldLanes.has(i);
        const color = LANE_COLORS[i];

        // Outer ring
        ctx.beginPath();
        ctx.arc(cx, HIT_ZONE_Y, HIT_CIRCLE_RADIUS, 0, Math.PI * 2);
        ctx.strokeStyle = held ? color : 'rgba(255,255,255,0.2)';
        ctx.lineWidth = held ? 3 : 2;
        ctx.stroke();

        if (held) {
          // Fill glow
          ctx.fillStyle = color + '40';
          ctx.fill();
          ctx.shadowColor = color;
          ctx.shadowBlur = 20;
          ctx.beginPath();
          ctx.arc(cx, HIT_ZONE_Y, HIT_CIRCLE_RADIUS - 4, 0, Math.PI * 2);
          ctx.fillStyle = color + '60';
          ctx.fill();
          ctx.shadowBlur = 0;
        }

        // Lane letter
        ctx.fillStyle = held ? '#fff' : 'rgba(255,255,255,0.4)';
        ctx.font = 'bold 14px system-ui';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(['A', 'S', 'D', 'F', 'G'][i], cx, HIT_ZONE_Y);
      }
    },
    [state.chart]
  );

  const drawEffects = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      ctx.clearRect(0, 0, CANVAS_WIDTH, HIGHWAY_HEIGHT);
      const now = performance.now();

      // Hit effects (floating text)
      for (const effect of state.hitEffects) {
        const elapsed = now - effect.timeCreated;
        if (elapsed > EFFECT_DURATION_MS) continue;

        const progress = elapsed / EFFECT_DURATION_MS;
        const alpha = 1 - progress;
        const offsetY = progress * 60;

        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.font = 'bold 18px system-ui';
        ctx.textAlign = 'center';

        if (effect.quality === 'PERFECT') {
          ctx.fillStyle = '#facc15';
          ctx.shadowColor = '#facc15';
          ctx.shadowBlur = 10;
          ctx.fillText('PERFECT!', effect.x, effect.y - 40 - offsetY);
        } else if (effect.quality === 'GOOD') {
          ctx.fillStyle = '#22c55e';
          ctx.fillText('GOOD!', effect.x, effect.y - 40 - offsetY);
        } else {
          ctx.fillStyle = '#ef4444';
          ctx.fillText('MISS', effect.x, effect.y - 40 - offsetY);
        }
        ctx.restore();
      }

      // Particles
      for (const p of state.particles) {
        if (p.life <= 0) continue;
        ctx.save();
        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // Update particle state inline for smooth animation
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.15;
        p.life -= 0.02;
      }
    },
    [state.hitEffects, state.particles]
  );

  const draw = useCallback(
    (songTimeMs: number, heldLanes: Set<number>) => {
      if (!bgDrawn.current) drawBackground();

      const noteCtx = noteCanvasRef.current?.getContext('2d');
      if (noteCtx) drawNotes(noteCtx, songTimeMs, heldLanes);

      const fxCtx = fxCanvasRef.current?.getContext('2d');
      if (fxCtx) drawEffects(fxCtx);
    },
    [drawBackground, drawNotes, drawEffects]
  );

  useImperativeHandle(ref, () => ({ draw }), [draw]);

  const canvasStyle = { position: 'absolute' as const, top: 0, left: 0 };

  return (
    <div className="relative" style={{ width: CANVAS_WIDTH, height: HIGHWAY_HEIGHT }}>
      <canvas ref={bgCanvasRef} width={CANVAS_WIDTH} height={HIGHWAY_HEIGHT} style={canvasStyle} />
      <canvas ref={noteCanvasRef} width={CANVAS_WIDTH} height={HIGHWAY_HEIGHT} style={{ ...canvasStyle, zIndex: 10 }} />
      <canvas ref={fxCanvasRef} width={CANVAS_WIDTH} height={HIGHWAY_HEIGHT} style={{ ...canvasStyle, zIndex: 20 }} />
    </div>
  );
});

GameCanvas.displayName = 'GameCanvas';

export default GameCanvas;
