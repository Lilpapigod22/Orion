/* The eyes' motion, shared by the 3D and the 2D eyes: springs towards the expression, blinking, the
   gaze (mouse or a skill bubble) and the wave under the eyes. */
import { spring, stepSpring } from './spring.js';

export function createRig(random = Math.random) {
  const s = { lookX: spring(0), lookY: spring(0), open: spring(1), scale: spring(1), tilt: spring(0), right: spring(1) };
  let nextBlink = 2 + random() * 3;
  let blinking = 0;
  return {
    step(dt, expr, gaze, spectrum, now, t) {
      const focus = gaze.focus && now < gaze.focus.until ? gaze.focus : null;
      const drift = expr.wave === 'flat' && !expr.sleepy ? Math.sin(t * 0.7) * 0.12 : 0;
      s.lookX.target = (focus ? focus.x : gaze.x) * 0.35 + expr.lookX + drift;
      s.lookY.target = (focus ? focus.y : gaze.y) * 0.25 + expr.lookY;
      nextBlink -= dt;
      if (nextBlink <= 0) {
        blinking = 0.14;
        nextBlink = 2 + random() * 3;
      }
      s.open.target = blinking > 0 ? 0.05 : expr.open;
      blinking -= dt;
      s.scale.target = expr.scale;
      s.tilt.target = expr.tilt;
      s.right.target = expr.rightEye;
      stepSpring(s.open, dt, 600, 40);  // eyelids are quick
      for (const key of ['lookX', 'lookY', 'scale', 'tilt', 'right']) stepSpring(s[key], dt);
      const bars = Array.from({ length: 25 }, (_, i) => {
        const k = Math.abs(i - 12) / 12;
        if (expr.wave === 'voice') return Math.max(0.05, (spectrum[Math.min(23, Math.round(k * 23))] || 0) * 1.6 * (1 - k * 0.6));
        if (expr.wave === 'think') return 0.05 + 0.25 * Math.max(0, Math.sin(t * 6 - i * 0.5));
        return 0.05;
      });
      return { lookX: s.lookX.x, lookY: s.lookY.x, open: Math.max(0.04, s.open.x), scale: s.scale.x,
        tilt: s.tilt.x, right: s.right.x, shape: expr.shape, bars };
    },
  };
}
