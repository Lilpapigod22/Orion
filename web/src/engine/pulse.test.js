import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { COLORS } from './expression.js';
import { pulse } from './pulse.js';

describe('pulse', () => {
  it('moves the colour towards the state colour', () => {
    store.set({ mode: 'listening', mood: { kind: null, until: 0 }, test: null, lastActivity: Date.now() });
    for (let i = 0; i < 60; i++) pulse.frame(1 / 30);
    pulse.color.forEach((c, i) => expect(Math.abs(c - COLORS.amber[i])).toBeLessThan(3));
    expect(pulse.expr.color).toBe('amber');
  });
});
