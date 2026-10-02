import { describe, expect, it } from 'vitest';
import { expressionFor, SLEEP_AFTER_MS } from './expression.js';

describe('expressionFor', () => {
  it('idle: blue, open, looking ahead', () => {
    expect(expressionFor({ mode: 'idle' })).toMatchObject({ color: 'holo', open: 1, shape: 'box', wave: 'flat', sleepy: false });
  });
  it('listening: amber and larger', () => {
    expect(expressionFor({ mode: 'listening' })).toMatchObject({ color: 'amber', scale: 1.15 });
  });
  it('thinking: squint, look up, fast network, thinking wave', () => {
    expect(expressionFor({ mode: 'thinking' })).toMatchObject({ open: 0.55, lookY: 0.3, spin: 2.6, wave: 'think' });
  });
  it('speaking: the voice wave', () => {
    expect(expressionFor({ mode: 'speaking' }).wave).toBe('voice');
  });
  it('happy mood: arcs while it lasts', () => {
    expect(expressionFor({ mode: 'idle', mood: { kind: 'happy', until: 10 }, now: 5 }).shape).toBe('arc');
    expect(expressionFor({ mode: 'idle', mood: { kind: 'happy', until: 10 }, now: 11 }).shape).toBe('box');
  });
  it('confused or offline: red, tilted, smaller right eye', () => {
    for (const e of [expressionFor({ mode: 'idle', mood: { kind: 'confused', until: 10 }, now: 5 }), expressionFor({ mode: 'offline' })]) {
      expect(e).toMatchObject({ color: 'alert', tilt: 0.18, rightEye: 0.65 });
    }
  });
  it('test mode: green unless listening', () => {
    expect(expressionFor({ mode: 'idle', testActive: true }).color).toBe('test');
    expect(expressionFor({ mode: 'listening', testActive: true }).color).toBe('amber');
  });
  it('sleepy after 10 minutes of quiet', () => {
    expect(expressionFor({ mode: 'idle', idleMs: SLEEP_AFTER_MS + 1 })).toMatchObject({ sleepy: true, open: 0.35 });
    expect(expressionFor({ mode: 'thinking', idleMs: SLEEP_AFTER_MS + 1 }).sleepy).toBe(false);
  });
});
