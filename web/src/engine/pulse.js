/* The heartbeat shared by the network and the eyes: Orion's state colour, spin and the voice level.
   Updated once per frame by engine/mind.js. */
import { store } from '../store.js';
import { reduceMotion } from '../util.js';
import { COLORS, expressionFor } from './expression.js';
import { voice } from './voice.js';

export const pulse = {
  mode: 'boot',
  expr: expressionFor({ mode: 'boot' }),
  color: [...COLORS.holo],
  spin: 0.9,
  level: 0,
  spectrum: new Float32Array(24),
  t: 0,

  frame(dt) {
    const s = store.get();
    const now = Date.now();
    this.mode = s.mode;
    this.expr = expressionFor({ mode: s.mode, mood: s.mood, testActive: Boolean(s.test), idleMs: now - s.lastActivity, now });
    this.t += dt;
    const ease = (k) => Math.min(1, dt * k);
    const target = COLORS[this.expr.color];
    for (let i = 0; i < 3; i++) this.color[i] += (target[i] - this.color[i]) * ease(4);
    this.spin += (this.expr.spin - this.spin) * ease(3);
    if (voice.analyser && voice.playing) {
      voice.analyser.getByteFrequencyData(voice.bins);
      let sum = 0;
      for (let i = 0; i < 24; i++) {
        const v = Math.min(1, (voice.bins[2 + Math.round(i * 1.6)] / 255) * (0.8 + i / 14));
        this.spectrum[i] += (v - this.spectrum[i]) * ease(18);
        sum += v;
      }
      this.level += (Math.min(1, (sum / 24) * 2.2) - this.level) * ease(20);
    } else {
      for (let i = 0; i < 24; i++) this.spectrum[i] *= 1 - ease(6);
      const breathe = Math.sin(this.t * 1.3) * 0.06 * (reduceMotion ? 0.15 : 1);
      this.level += (0.3 + breathe - this.level) * ease(4);
    }
  },
};
