import { useEffect, useRef } from 'react';
import { createRig } from '../engine/eyesRig.js';
import { gaze } from '../engine/gaze.js';
import { pulse } from '../engine/pulse.js';

// The same eyes on a 2D canvas — when WebGL is missing or the 3D eyes fail.
export function Eyes2D() {
  const canvas = useRef(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el.getContext('2d');
    if (!ctx) return undefined;
    const rig = createRig();
    let last = performance.now();
    const draw = () => {
      if (document.hidden) return;
      const now = performance.now();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = el.clientWidth, h = el.clientHeight;
      if (el.width !== Math.round(w * dpr)) { el.width = Math.round(w * dpr); el.height = Math.round(h * dpr); }
      const pose = rig.step(dt, pulse.expr, gaze, pulse.spectrum, Date.now(), pulse.t);
      const [r, g, b] = pulse.color.map(Math.round);
      const u = w / 6.5;  // one 3D unit in pixels (the 3D camera sees ~6.5 units)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#04090F';
      ctx.fillRect(0, 0, w, h);
      ctx.translate(w / 2 + pose.lookX * u, h / 2 - pose.lookY * u);
      ctx.rotate(pose.tilt);
      ctx.scale(pose.scale, pose.scale);
      ctx.shadowColor = `rgba(${r},${g},${b},0.9)`;
      ctx.shadowBlur = 24;
      ctx.fillStyle = ctx.strokeStyle = `rgb(${r},${g},${b})`;
      for (const [side, factor] of [[-1, 1], [1, pose.right]]) {
        const x = side * 1.25 * u;
        if (pose.shape === 'arc') {
          ctx.lineWidth = 0.32 * u;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.arc(x, 0.25 * u, 0.62 * u, Math.PI * 1.1, Math.PI * 1.9);
          ctx.stroke();
        } else {
          const ew = 1.25 * u, eh = Math.max(2, 1.5 * u * pose.open * factor);
          ctx.beginPath();
          ctx.roundRect(x - ew / 2, -eh / 2, ew, eh, Math.min(0.42 * u, eh / 2));
          ctx.fill();
        }
      }
      ctx.shadowBlur = 10;
      pose.bars.forEach((v, i) => {
        const bh = Math.max(2, v * u);
        ctx.fillRect((i - 12) * 0.2 * u - 0.06 * u, 1.9 * u - bh / 2, 0.12 * u, bh);
      });
    };
    const timer = setInterval(draw, 1000 / 30);
    return () => clearInterval(timer);
  }, []);
  return <canvas ref={canvas} />;
}
