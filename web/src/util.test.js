import { describe, expect, it } from 'vitest';
import { clockTime } from './util.js';

describe('clockTime', () => {
  it('pads hours and minutes', () => {
    expect(clockTime(new Date(2026, 0, 1, 7, 5, 9))).toBe('07:05');
    expect(clockTime(new Date(2026, 0, 1, 7, 5, 9), true)).toBe('07:05:09');
  });
});
