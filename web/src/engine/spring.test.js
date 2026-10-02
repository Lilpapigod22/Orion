import { describe, expect, it } from 'vitest';
import { spring, stepSpring } from './spring.js';

describe('spring', () => {
  it('settles on the target within a second without wild overshoot', () => {
    const s = spring(0);
    s.target = 1;
    let peak = 0;
    for (let i = 0; i < 60; i++) peak = Math.max(peak, stepSpring(s, 1 / 60));
    expect(Math.abs(s.x - 1)).toBeLessThan(0.05);
    expect(peak).toBeLessThan(1.25);
  });
});
