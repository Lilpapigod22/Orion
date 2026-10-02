import { describe, expect, it } from 'vitest';
import { applyLiveEvent, formatMs, lastTps, nowLine, phaseSummary } from './live.js';

const ev = (o) => ({ trace: 1, detail: null, key: o.key || o.phase, t: 0, ms: null, ok: null, ...o });
const run = (events) => events.reduce((live, e) => applyLiveEvent(live, e, 1000), { traces: [] });

describe('applyLiveEvent', () => {
  it('builds a trace from its events', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'Колко е 17 по 23?', detail: { source: 'text' } }),
      ev({ phase: 'understood', state: 'start', label: 'choosing' }),
      ev({ phase: 'understood', state: 'end', label: 'model', ms: 4, ok: true }),
      ev({ phase: 'thinking', state: 'start', label: 'round 1', key: 'thinking-0' }),
      ev({ phase: 'thinking', state: 'update', label: 'reasoning', key: 'thinking-0', detail: { text: 'Трябва да умножа' } }),
    ]);
    const trace = live.traces[0];
    expect(trace.text).toBe('Колко е 17 по 23?');
    expect(trace.steps.map((s) => [s.phase, s.state])).toEqual([['heard', 'done'], ['understood', 'done'], ['thinking', 'run']]);
    expect(nowLine(trace)).toBe('Трябва да умножа');
  });

  it('ignores events of unknown or finished traces and late steps', () => {
    let live = run([ev({ phase: 'heard', state: 'end', label: 'x' }), ev({ phase: 'done', state: 'end', label: 'done', ok: true, ms: 900 })]);
    const before = live;
    live = applyLiveEvent(live, ev({ trace: 99, phase: 'skill', state: 'end', label: 'a' }), 1000);
    live = applyLiveEvent(live, ev({ phase: 'skill', state: 'end', label: 'late' }), 1000);
    expect(live).toBe(before);
  });

  it('keeps only the last 20 traces', () => {
    let live = { traces: [] };
    for (let i = 1; i <= 25; i++) live = applyLiveEvent(live, ev({ trace: i, phase: 'heard', state: 'end', label: `q${i}` }), i);
    expect(live.traces).toHaveLength(20);
    expect(live.traces[0].id).toBe(6);
  });
});

describe('phaseSummary', () => {
  it('reports status and total time per phase', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'x', ms: 120, ok: true }),
      ev({ phase: 'skill', state: 'start', label: 'a', key: 'a' }),
      ev({ phase: 'skill', state: 'end', label: 'a', key: 'a', ms: 300, ok: true }),
      ev({ phase: 'skill', state: 'start', label: 'b', key: 'b' }),
      ev({ phase: 'skill', state: 'end', label: 'b', key: 'b', ms: 200, ok: false }),
    ]);
    const byPhase = Object.fromEntries(phaseSummary(live.traces[0]).map((p) => [p.phase, p]));
    expect(byPhase.heard).toMatchObject({ status: 'done', ms: 120 });
    expect(byPhase.skill).toMatchObject({ status: 'fail', ms: 500 });
    expect(byPhase.speaking.status).toBe('idle');
  });
});

describe('helpers', () => {
  it('formats durations', () => {
    expect(formatMs(120)).toBe('120 ms');
    expect(formatMs(1234)).toBe('1.2 s');
  });
  it('reads the speed of the last model round', () => {
    const live = run([
      ev({ phase: 'heard', state: 'end', label: 'x' }),
      ev({ phase: 'thinking', state: 'end', label: 'r', key: 'thinking-0', detail: { tps: 31.5 } }),
    ]);
    expect(lastTps(live.traces[0])).toBe(31.5);
  });
});
