import { describe, expect, it } from 'vitest';
import { expressionFor } from './expression.js';
import { createRig } from './eyesRig.js';

const still = { x: 0, y: 0, focus: null };
const quiet = new Float32Array(24);
const run = (rig, expr, seconds, gaze = still, spectrum = quiet) => {
  let pose;
  for (let i = 0; i < seconds * 30; i++) pose = rig.step(1 / 30, expr, gaze, spectrum, i * 33, i / 30);
  return pose;
};

describe('eyes rig', () => {
  it('blinks every few seconds', () => {
    const rig = createRig(() => 0.5);
    let closed = 0;
    for (let i = 0; i < 30 * 8; i++) if (rig.step(1 / 30, expressionFor({ mode: 'idle' }), still, quiet, i * 33, i / 30).open < 0.3) closed++;
    expect(closed).toBeGreaterThan(0);
  });
  it('squints while thinking', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'thinking' }), 1.5);
    expect(pose.open).toBeGreaterThan(0.45);
    expect(pose.open).toBeLessThan(0.7);
  });
  it('follows the mouse', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'idle' }), 1.5, { x: 1, y: 0, focus: null });
    expect(pose.lookX).toBeGreaterThan(0.25);
  });
  it('a skill bubble wins over the mouse while it lasts', () => {
    const pose = run(createRig(() => 0.99), expressionFor({ mode: 'idle' }), 0.8, { x: 1, y: 0, focus: { x: -1, y: 0, until: 1e12 } });
    expect(pose.lookX).toBeLessThan(-0.2);
  });
  it('stays stable after a long frame', () => {
    const rig = createRig(() => 0.99);
    const idle = expressionFor({ mode: 'idle' });
    run(rig, idle, 0.3);
    for (let i = 0; i < 6; i++) {
      const pose = rig.step(0.1, idle, still, quiet, 1e6 + i * 100, 10 + i * 0.1);
      expect(pose.open).toBeGreaterThanOrEqual(0);
      expect(pose.open).toBeLessThanOrEqual(1.1);
      expect(Number.isFinite(pose.lookX)).toBe(true);
      expect(Math.abs(pose.lookX)).toBeLessThanOrEqual(1.5);
    }
  });
  it('the voice wave only while speaking', () => {
    const loud = new Float32Array(24).fill(0.8);
    expect(Math.max(...run(createRig(), expressionFor({ mode: 'speaking' }), 0.5, still, loud).bars)).toBeGreaterThan(0.5);
    expect(Math.max(...run(createRig(), expressionFor({ mode: 'idle' }), 0.5, still, loud).bars)).toBeLessThan(0.1);
  });
});
