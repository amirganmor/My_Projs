import { useRef, useEffect } from 'react';

export type GuitaristEvent = 'idle' | 'strum' | 'perfect' | 'miss';

interface GuitaristProps {
  event: GuitaristEvent;
  eventTime: number;
  bpm: number;
  streak: number;
}

const W = 240;
const H = 520;

// Pre-computed hair strand positions (left side, mirrored for right)
const HAIR_STRANDS = Array.from({ length: 9 }, (_, i) => ({
  startOffsetX: 2 + Math.sin(i * 1.4) * 3,
  startOffsetY: -4 + i * 3,
  cp1dx: -10 - i * 2,
  cp1dy: 25 + i * 6,
  cp2dx: 5 - i * 1.5,
  cp2dy: 55 + i * 10,
  endDx: -8 - i * 3 + Math.sin(i * 2) * 4,
  endDy: 80 + i * 14,
  thickness: 5.5 - i * 0.2,
}));

export default function Guitarist({ event, eventTime, bpm, streak }: GuitaristProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const phaseRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const beatMs = 60000 / (bpm || 120);
    let prev = performance.now();

    function frame() {
      const now = performance.now();
      const dt = (now - prev) / 1000;
      prev = now;
      ctx.clearRect(0, 0, W, H);

      const el = now - eventTime;
      const t = now / 1000;
      phaseRef.current += dt * 1.5;
      const ph = phaseRef.current;

      const beatT = (now % beatMs) / beatMs;
      const pulse = Math.sin(beatT * Math.PI * 2);
      const hpulse = Math.sin(beatT * Math.PI);

      let sx = Math.sin(ph * Math.PI * 0.5) * 4 + pulse * 1.5;
      let by = Math.abs(Math.sin(ph * Math.PI)) * 3 + hpulse * 2;
      let headTilt = pulse * 0.025;
      let gRock = Math.sin(t * 0.6) * 0.03 + pulse * 0.01;
      let armA = Math.sin(t * 1.6) * 0.04;
      let lean = 0;
      let jmp = 0;
      let star = false;

      const wk = Math.sin(ph * Math.PI);
      const wk2 = Math.sin(ph * Math.PI + Math.PI);
      let ll = wk * 0.12, rl = wk2 * 0.12;
      let lf = Math.max(0, wk) * 5, rf = Math.max(0, wk2) * 5;

      if (streak > 20) { lean = 0.07; gRock += Math.sin(t * 1.2) * 0.04; }
      else if (streak > 10) { sx += Math.sin(t * 1.3) * 4; ll *= 1.3; rl *= 1.3; }

      if (event === 'strum' && el < 180) armA = -0.7 + (el / 180) * 0.8;
      else if (event === 'perfect' && el < 450) { jmp = Math.sin((el / 450) * Math.PI) * 25; star = el < 300; armA = -0.4; }
      else if (event === 'miss' && el < 400) { headTilt = 0.1 * (1 - el / 400); by *= 0.2; }

      const ox = W / 2 + sx;
      const oy = 380 - by - jmp;

      ctx.save();
      ctx.translate(ox, oy);
      ctx.rotate(lean);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      // ===== LAYER 1: BACK HAIR MASS (behind everything) =====
      ctx.fillStyle = '#0c0800';
      ctx.beginPath();
      ctx.moveTo(-45, -105);
      ctx.quadraticCurveTo(-50, -135, -30, -148);
      ctx.quadraticCurveTo(0, -158, 30, -148);
      ctx.quadraticCurveTo(50, -135, 45, -105);
      ctx.quadraticCurveTo(42, -50, 38, 5);
      ctx.lineTo(-38, 5);
      ctx.quadraticCurveTo(-42, -50, -45, -105);
      ctx.fill();

      // ===== LAYER 2: LEGS =====
      for (const s of [-1, 1] as const) {
        const a = s < 0 ? ll : rl;
        const f = s < 0 ? lf : rf;
        ctx.save();
        ctx.translate(s * 8, 0);
        ctx.rotate(a);
        ctx.fillStyle = '#111';
        ctx.beginPath();
        ctx.moveTo(-6, -2); ctx.lineTo(-8, 55); ctx.lineTo(8, 55); ctx.lineTo(6, -2);
        ctx.closePath(); ctx.fill();
        ctx.beginPath();
        ctx.moveTo(-8, 53); ctx.lineTo(-9 + s * 6, 100 - f); ctx.lineTo(9 + s * 6, 100 - f); ctx.lineTo(8, 53);
        ctx.closePath(); ctx.fill();
        ctx.fillStyle = '#0a0604';
        ctx.beginPath();
        ctx.moveTo(-9 + s * 6, 96 - f); ctx.lineTo(-10 + s * 6, 112 - f);
        ctx.lineTo(s * 22 + s * 4, 114 - f); ctx.lineTo(10 + s * 6, 112 - f);
        ctx.lineTo(10 + s * 6, 96 - f); ctx.closePath(); ctx.fill();
        ctx.restore();
      }

      // Belt
      ctx.fillStyle = '#1a1a1a'; ctx.fillRect(-26, -3, 52, 7);
      ctx.fillStyle = '#999'; ctx.beginPath(); ctx.roundRect(-5, -4, 10, 9, 3); ctx.fill();

      // ===== LAYER 3: TORSO (dark shirt) =====
      ctx.fillStyle = '#1c1c1c';
      ctx.beginPath();
      ctx.moveTo(-28, -85); ctx.quadraticCurveTo(-34, -45, -30, 5);
      ctx.lineTo(30, 5); ctx.quadraticCurveTo(34, -45, 28, -85);
      ctx.closePath(); ctx.fill();

      // V-neck opening showing skin
      ctx.fillStyle = '#b07850';
      ctx.beginPath();
      ctx.moveTo(-8, -85); ctx.lineTo(8, -85);
      ctx.lineTo(6, -60); ctx.lineTo(0, -55); ctx.lineTo(-6, -60);
      ctx.closePath(); ctx.fill();

      // Necklace
      ctx.strokeStyle = '#b8922a'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(-6, -84); ctx.quadraticCurveTo(0, -70, 6, -84); ctx.stroke();
      ctx.fillStyle = '#b8922a';
      ctx.beginPath(); ctx.arc(0, -71, 2.5, 0, Math.PI * 2); ctx.fill();

      // Guitar strap
      ctx.strokeStyle = '#2a1808'; ctx.lineWidth = 6;
      ctx.beginPath(); ctx.moveTo(14, -82); ctx.lineTo(-16, -30); ctx.stroke();

      // ===== LAYER 4: LES PAUL GUITAR =====
      ctx.save();
      ctx.translate(-22, -8 + Math.sin(t * 0.5) * 2);
      ctx.rotate(-0.3 + gRock);

      ctx.fillStyle = '#3e2410'; ctx.fillRect(-3, -80, 7, 82);
      ctx.strokeStyle = '#bbb'; ctx.lineWidth = 0.6;
      for (let f = -74; f < 0; f += 8) { ctx.beginPath(); ctx.moveTo(-3, f); ctx.lineTo(4, f); ctx.stroke(); }

      ctx.fillStyle = '#111';
      ctx.beginPath();
      ctx.moveTo(-6, -80); ctx.lineTo(-9, -100);
      ctx.quadraticCurveTo(-6, -105, -3, -101); ctx.lineTo(0, -96);
      ctx.lineTo(3, -101); ctx.quadraticCurveTo(6, -105, 9, -100);
      ctx.lineTo(6, -80); ctx.closePath(); ctx.fill();
      ctx.fillStyle = '#bbb';
      for (let p = 0; p < 3; p++) {
        ctx.beginPath(); ctx.arc(-10, -84 - p * 5, 2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(10, -84 - p * 5, 2, 0, Math.PI * 2); ctx.fill();
      }

      const bg = ctx.createRadialGradient(0, 22, 4, 0, 22, 30);
      bg.addColorStop(0, '#f5c030'); bg.addColorStop(0.35, '#d89018');
      bg.addColorStop(0.6, '#a06008'); bg.addColorStop(1, '#3a1804');
      ctx.fillStyle = bg;
      ctx.beginPath(); ctx.ellipse(0, 6, 16, 12, 0, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.ellipse(0, 26, 22, 19, 0, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#f0e0c0'; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.ellipse(0, 26, 22, 19, 0, 0, Math.PI * 2); ctx.stroke();

      ctx.fillStyle = '#ccc';
      ctx.beginPath(); ctx.roundRect(-7, 8, 14, 6, 2); ctx.fill();
      ctx.beginPath(); ctx.roundRect(-7, 24, 14, 6, 2); ctx.fill();
      ctx.fillStyle = '#b8922a';
      for (const [kx, ky] of [[-10, 38], [10, 38], [-10, 44], [10, 44]] as const) {
        ctx.beginPath(); ctx.arc(kx, ky, 2.5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.strokeStyle = '#ddd'; ctx.lineWidth = 0.3;
      for (let s = -2; s <= 2; s++) { ctx.beginPath(); ctx.moveTo(s * 0.8, -80); ctx.lineTo(s * 1.2, 38); ctx.stroke(); }

      ctx.restore();

      // ===== LAYER 5: ARMS =====
      // Right arm (strum)
      ctx.save();
      ctx.translate(24, -68);
      ctx.rotate(armA);
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.moveTo(-4, 0); ctx.lineTo(-3, 38); ctx.quadraticCurveTo(0, 44, 3, 38); ctx.lineTo(4, 0); ctx.closePath(); ctx.fill();
      ctx.fillStyle = '#aaa'; ctx.fillRect(-4, 33, 8, 3);
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.arc(0, 42, 4.5, 0, Math.PI * 2); ctx.fill();
      ctx.restore();

      // Left arm (fret)
      ctx.save();
      ctx.translate(-24, -68);
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.moveTo(-3, 0); ctx.lineTo(-18, 24); ctx.quadraticCurveTo(-22, 28, -18, 30); ctx.lineTo(-1, 10); ctx.closePath(); ctx.fill();
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.arc(-20, 30, 4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#aaa'; ctx.lineWidth = 1.5; ctx.strokeStyle = '#aaa';
      ctx.beginPath(); ctx.arc(-18, 28, 4.5, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();

      // ===== LAYER 6: HEAD / FACE (clearly visible) =====
      ctx.save();
      ctx.rotate(headTilt);

      // Neck
      ctx.fillStyle = '#b07850';
      ctx.fillRect(-6, -98, 12, 16);

      // Face oval -- clearly visible, clean
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.ellipse(0, -114, 15, 18, 0, 0, Math.PI * 2); ctx.fill();

      // Forehead hair (small band between hat brim and glasses)
      ctx.fillStyle = '#0c0800';
      ctx.beginPath();
      ctx.moveTo(-16, -128);
      ctx.quadraticCurveTo(-18, -135, -14, -138);
      ctx.quadraticCurveTo(0, -142, 14, -138);
      ctx.quadraticCurveTo(18, -135, 16, -128);
      ctx.quadraticCurveTo(8, -126, 0, -127);
      ctx.quadraticCurveTo(-8, -126, -16, -128);
      ctx.fill();

      // Sunglasses -- large, prominent aviators
      ctx.fillStyle = '#0a0a0a';
      ctx.strokeStyle = '#555';
      ctx.lineWidth = 2;
      // Left lens
      ctx.beginPath(); ctx.ellipse(-9, -120, 10, 7, -0.05, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      // Right lens
      ctx.beginPath(); ctx.ellipse(9, -120, 10, 7, 0.05, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      // Bridge
      ctx.strokeStyle = '#777'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(-1, -120); ctx.lineTo(1, -120); ctx.stroke();
      // Arms of glasses going into hair
      ctx.strokeStyle = '#555'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(-19, -119); ctx.lineTo(-24, -118); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(19, -119); ctx.lineTo(24, -118); ctx.stroke();
      // Glare
      ctx.strokeStyle = 'rgba(255,255,255,0.2)'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(-11, -122, 4, 0.3, 1.5); ctx.stroke();
      ctx.beginPath(); ctx.arc(7, -122, 4, 0.3, 1.5); ctx.stroke();

      // Nose
      ctx.fillStyle = '#a06842';
      ctx.beginPath(); ctx.moveTo(-2, -112); ctx.lineTo(0, -105); ctx.lineTo(2, -112); ctx.closePath(); ctx.fill();

      // Mouth / lips
      if (event === 'perfect' && el < 450) {
        // Grin
        ctx.fillStyle = '#eee';
        ctx.beginPath(); ctx.arc(0, -100, 4, 0, Math.PI); ctx.fill();
        ctx.strokeStyle = '#905a3a'; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(0, -100, 4, 0, Math.PI); ctx.stroke();
      } else if (event === 'miss' && el < 400) {
        // Frown
        ctx.strokeStyle = '#905a3a'; ctx.lineWidth = 1.8;
        ctx.beginPath(); ctx.arc(0, -98, 3, Math.PI, 0); ctx.stroke();
      } else {
        // Lips - slightly parted
        ctx.fillStyle = '#8a4a30';
        ctx.beginPath();
        ctx.moveTo(-5, -101); ctx.quadraticCurveTo(0, -98, 5, -101);
        ctx.quadraticCurveTo(0, -96, -5, -101);
        ctx.fill();

        // Cigarette
        ctx.save();
        ctx.translate(5, -100);
        ctx.rotate(0.18);
        ctx.fillStyle = '#ede8d8'; ctx.fillRect(0, -1, 18, 2.5);
        ctx.fillStyle = '#c08838'; ctx.fillRect(0, -1, 4, 2.5);
        const g = 0.5 + Math.sin(t * 4) * 0.4;
        ctx.fillStyle = `rgba(255,70,0,${g})`;
        ctx.beginPath(); ctx.arc(18, 0.3, 2, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(180,180,180,${0.1 + Math.sin(t * 1.5) * 0.05})`;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(18, -1);
        ctx.quadraticCurveTo(22 + Math.sin(t * 1.2) * 3, -12, 20 + Math.sin(t * 1.6) * 5, -25);
        ctx.stroke();
        ctx.restore();
      }

      // Chin
      ctx.fillStyle = '#b07850';
      ctx.beginPath(); ctx.ellipse(0, -93, 8, 5, 0, 0, Math.PI * 2); ctx.fill();

      // ===== LAYER 7: SIDE HAIR (frames the face, does NOT cover it) =====
      ctx.strokeStyle = '#0c0800';
      ctx.fillStyle = '#0c0800';

      // Draw curly locks cascading down on each side
      for (const side of [-1, 1]) {
        for (const strand of HAIR_STRANDS) {
          const baseX = side * (16 + strand.startOffsetX);
          const baseY = -132 + strand.startOffsetY;
          const w = Math.sin(t * 0.6 + strand.startOffsetY * 0.1 + side) * 3;

          ctx.lineWidth = strand.thickness;
          ctx.beginPath();
          ctx.moveTo(baseX, baseY);
          ctx.bezierCurveTo(
            baseX + side * strand.cp1dx + w,
            baseY + strand.cp1dy,
            baseX + side * strand.cp2dx - w * 0.5,
            baseY + strand.cp2dy,
            baseX + side * strand.endDx + w * 0.3,
            baseY + strand.endDy
          );
          ctx.stroke();
        }

        // Extra volume: thick dark shapes at the side-top where hair exits under hat
        ctx.fillStyle = '#0c0800';
        ctx.beginPath();
        ctx.ellipse(side * 24, -125, 12, 16, side * 0.2, 0, Math.PI * 2);
        ctx.fill();
      }

      // ===== LAYER 8: TOP HAT (on top of everything) =====
      ctx.save();
      ctx.rotate(-0.04);

      // Brim
      ctx.fillStyle = '#141414';
      ctx.beginPath(); ctx.ellipse(0, -136, 32, 9, 0, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#333'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.ellipse(0, -136, 32, 9, 0, 0, Math.PI * 2); ctx.stroke();

      // Crown
      ctx.fillStyle = '#141414';
      ctx.beginPath();
      ctx.moveTo(-20, -136);
      ctx.bezierCurveTo(-21, -155, -19, -178, 0, -181);
      ctx.bezierCurveTo(19, -178, 21, -155, 20, -136);
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = '#333'; ctx.lineWidth = 1; ctx.stroke();

      // Top
      ctx.beginPath(); ctx.ellipse(0, -178, 18, 5, 0, 0, Math.PI * 2); ctx.fill();

      // Chrome band
      const bnd = ctx.createLinearGradient(-20, 0, 20, 0);
      bnd.addColorStop(0, '#777'); bnd.addColorStop(0.3, '#ddd');
      bnd.addColorStop(0.5, '#fff'); bnd.addColorStop(0.7, '#ddd'); bnd.addColorStop(1, '#777');
      ctx.fillStyle = bnd;
      ctx.beginPath();
      ctx.moveTo(-20, -143); ctx.lineTo(-20, -136);
      ctx.quadraticCurveTo(0, -133, 20, -136);
      ctx.lineTo(20, -143); ctx.quadraticCurveTo(0, -140, -20, -143);
      ctx.closePath(); ctx.fill();

      // Conchos
      for (let ci = -2; ci <= 2; ci++) {
        ctx.fillStyle = '#eee';
        ctx.beginPath(); ctx.arc(ci * 7, -139.5, 3, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#999';
        ctx.beginPath(); ctx.arc(ci * 7, -139.5, 1.3, 0, Math.PI * 2); ctx.fill();
      }

      // Highlight
      ctx.strokeStyle = 'rgba(255,255,255,0.07)'; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(-11, -176); ctx.quadraticCurveTo(-13, -158, -13, -138); ctx.stroke();

      ctx.restore(); // hat

      ctx.restore(); // head

      // ===== EFFECTS =====
      if (star) {
        const p = el / 300;
        ctx.save(); ctx.globalAlpha = 1 - p;
        ctx.strokeStyle = '#facc15'; ctx.lineWidth = 2.5;
        for (let i = 0; i < 12; i++) {
          const a = (i / 12) * Math.PI * 2 + t * 4;
          const r1 = 45 + p * 30, r2 = r1 + 15;
          ctx.beginPath();
          ctx.moveTo(Math.cos(a) * r1, -115 + Math.sin(a) * r1);
          ctx.lineTo(Math.cos(a) * r2, -115 + Math.sin(a) * r2);
          ctx.stroke();
        }
        ctx.restore();
      }

      // Smoke
      const sa = 0.025 + (streak > 5 ? Math.min(0.1, (streak - 5) * 0.006) : 0);
      for (let i = 0; i < 4; i++) {
        ctx.fillStyle = `rgba(120,120,150,${sa})`;
        ctx.beginPath();
        ctx.arc(-50 + i * 33 + Math.sin(t * 0.2 + i) * 8, 105 + Math.sin(t * 0.35 + i * 1.4) * 4, 14 + Math.sin(t * 0.3 + i) * 4, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
      animRef.current = requestAnimationFrame(frame);
    }

    animRef.current = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(animRef.current);
  }, [event, eventTime, bpm, streak]);

  return <canvas ref={canvasRef} width={W} height={H} className="flex-shrink-0" />;
}
