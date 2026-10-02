/* The reactor — the core of the 3D network. Drawn here on its own canvas;
   mind.js places it in the centre of the network every frame. */
import { store } from '../store.js';
import { reduceMotion } from '../util.js';
import { voice } from './voice.js';

const COLORS = {
  holo: [127, 219, 255],
  amber: [255, 181, 71],
  alert: [255, 90, 78],
};

// spin = rotation speed, energy = base brightness of the core, sweep = radar scan
export const MODES = {
  boot:        { color: 'holo',  spin: 0.9,  energy: 0.25 },
  idle:        { color: 'holo',  spin: 0.18, energy: 0.32 },
  standby:     { color: 'amber', spin: 0.12, energy: 0.22, sweep: 0.35 },
  calibrating: { color: 'amber', spin: 0.5,  energy: 0.3,  sweep: 1 },
  listening:   { color: 'amber', spin: 0.45, energy: 0.5,  sweep: 1 },
  thinking:    { color: 'holo',  spin: 2.6,  energy: 0.45 },
  speaking:    { color: 'holo',  spin: 0.3,  energy: 0.4 },
  offline:     { color: 'alert', spin: 0.05, energy: 0.15 },
  approval:    { color: 'amber', spin: 0.08, energy: 0.3 },
};

export const reactor = {
  canvas: document.createElement('canvas'),
  get ctx() { return this.canvas.getContext('2d'); },
  size: 0,
  dpr: 1,
  mode: MODES.boot,
  color: [...COLORS.holo],
  spin: MODES.boot.spin,
  sweep: 0,
  level: 0,
  rot: [0, 0, 0, 0],
  drawIn: 0,          // 0 -> 1 on start-up: the rings are “drawn in”
  spectrum: new Float32Array(24),
  t: 0,

  // The size comes from mind.js — the core is as large as the network around it allows.
  resize(size) {
    this.dpr = window.devicePixelRatio || 1;
    this.size = size;
    this.canvas.width = this.canvas.height = Math.round(size * this.dpr);
  },

  // Called by mind.js once per frame.
  frame(dt) {
    this.mode = MODES[store.get().mode] || MODES.boot;
    this.t += dt;
    const ease = (k) => Math.min(1, dt * k);
    const motion = reduceMotion ? 0.15 : 1;

    const target = COLORS[this.mode.color];
    for (let i = 0; i < 3; i++) this.color[i] += (target[i] - this.color[i]) * ease(4);
    this.spin += (this.mode.spin - this.spin) * ease(3);
    this.sweep += ((this.mode.sweep || 0) - this.sweep) * ease(4);
    this.drawIn = Math.min(1, this.drawIn + dt / 1.6);

    // The “energy” level follows the voice while Orion speaks; otherwise it breathes calmly.
    let targetLevel;
    if (voice.analyser && voice.playing) {
      voice.analyser.getByteFrequencyData(voice.bins);
      // 24 frequency bands across the speech range; higher ones are boosted because they are quieter.
      let sum = 0;
      for (let i = 0; i < 24; i++) {
        const v = Math.min(1, (voice.bins[2 + Math.round(i * 1.6)] / 255) * (0.8 + i / 14));
        this.spectrum[i] += (v - this.spectrum[i]) * ease(18);
        sum += v;
      }
      targetLevel = Math.min(1, (sum / 24) * 2.2);
    } else {
      for (let i = 0; i < 24; i++) this.spectrum[i] *= 1 - ease(6);
      const breathe = this.mode === MODES.thinking ? Math.sin(this.t * 7) * 0.12 : Math.sin(this.t * 1.3) * 0.06;
      targetLevel = this.mode.energy + breathe * motion;
    }
    this.level += (targetLevel - this.level) * ease(voice.playing ? 20 : 4);

    const s = this.spin * motion;
    this.rot[0] += dt * s * 0.22;
    this.rot[1] -= dt * s * 0.55;
    this.rot[2] += dt * s * 0.09;
    this.rot[3] += dt * (0.8 + s) * 1.4 * motion;

    this.draw();
  },

  draw() {
    const { ctx, size, dpr, level, drawIn } = this;
    if (!size) return;
    const [r, g, b] = this.color.map(Math.round);
    const rgba = (a) => `rgba(${r},${g},${b},${a})`;
    const R = size * 0.48;
    const u = R / 200; // scale: all sizes are for R = 200

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.translate(size / 2, size / 2);
    ctx.lineCap = 'butt';

    // 1. Outer tick scale.
    const ticks = 90;
    for (let i = 0; i < Math.floor(ticks * drawIn); i++) {
      const a = this.rot[0] + (i / ticks) * Math.PI * 2;
      const major = i % 5 === 0;
      const r1 = R, r2 = R - (major ? 11 : 5) * u;
      ctx.strokeStyle = rgba(major ? 0.55 : 0.22);
      ctx.lineWidth = (major ? 1.4 : 1) * u;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      ctx.stroke();
    }

    // 2. Thin ring.
    ctx.strokeStyle = rgba(0.16);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.9, 0, Math.PI * 2 * drawIn);
    ctx.stroke();

    // 3. Segmented arcs — counter-rotating; fast while “thinking”.
    const arcs = [[0, 0.95], [1.25, 2.2], [2.5, 2.8], [3.3, 4.7], [5.0, 5.85]];
    ctx.lineWidth = 2.2 * u;
    ctx.strokeStyle = rgba(0.75);
    for (const [a0, a1] of arcs) {
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.8, this.rot[1] + a0 * drawIn, this.rot[1] + a1 * drawIn);
      ctx.stroke();
    }

    // 4. Radar sweep while Orion listens (amber).
    if (this.sweep > 0.02 && ctx.createConicGradient) {
      const grad = ctx.createConicGradient(this.rot[3], 0, 0);
      grad.addColorStop(0, rgba(0.32 * this.sweep));
      grad.addColorStop(0.18, rgba(0));
      grad.addColorStop(1, rgba(0));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, R * 0.76, 0, Math.PI * 2);
      ctx.arc(0, 0, R * 0.62, 0, Math.PI * 2, true);
      ctx.fill();
    }

    // 5. Voice spectrum — rays around the core in four mirrored quarters,
    //    so the voice “breathes” evenly around the whole circle.
    const bars = 96;
    ctx.lineWidth = 2 * u;
    for (let i = 0; i < bars; i++) {
      const q = i % 48;
      const v = this.spectrum[q < 24 ? q : 47 - q];
      if (v < 0.02) continue;
      const a = -Math.PI / 2 + (i / bars) * Math.PI * 2;
      const r1 = R * 0.645, r2 = r1 + v * R * 0.2;
      ctx.strokeStyle = rgba(0.25 + v * 0.6);
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      ctx.stroke();
    }

    // 6. Reactor coils — 10 segments that glow with the energy level.
    const coils = 10, gap = 0.075;
    const inner = R * 0.44, outer = R * 0.6;
    for (let i = 0; i < coils; i++) {
      if (i / coils > drawIn) break;
      const a0 = this.rot[2] + (i / coils) * Math.PI * 2 + gap;
      const a1 = this.rot[2] + ((i + 1) / coils) * Math.PI * 2 - gap;
      ctx.beginPath();
      ctx.arc(0, 0, outer, a0, a1);
      ctx.arc(0, 0, inner, a1 - 0.02, a0 + 0.02, true);
      ctx.closePath();
      ctx.fillStyle = rgba(0.08 + level * 0.42);
      ctx.fill();
      ctx.strokeStyle = rgba(0.55);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // 7. Inner glowing ring.
    ctx.save();
    ctx.shadowColor = rgba(0.9);
    ctx.shadowBlur = (10 + level * 26) * u;
    ctx.strokeStyle = rgba(0.85);
    ctx.lineWidth = 2.6 * u;
    ctx.beginPath();
    ctx.arc(0, 0, R * 0.38, 0, Math.PI * 2 * drawIn);
    ctx.stroke();
    ctx.restore();

    // 8. Core — its white-blue size follows the voice.
    const coreR = R * (0.25 + level * 0.11) * drawIn;
    if (coreR > 1) {
      const core = ctx.createRadialGradient(0, 0, 0, 0, 0, coreR);
      core.addColorStop(0, `rgba(255,255,255,${0.75 + level * 0.25})`);
      core.addColorStop(0.3, rgba(0.55 + level * 0.35));
      core.addColorStop(1, rgba(0));
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(0, 0, coreR, 0, Math.PI * 2);
      ctx.fill();
    }
  },
};
