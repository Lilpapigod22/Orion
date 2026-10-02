import { beforeEach, describe, expect, it } from 'vitest';
import { hud } from './bridge.js';
import { store } from './store.js';

const ev = (o) => ({ trace: 7, detail: null, key: o.key || o.phase, t: 0, ms: null, ok: null, ...o });

describe('bridge', () => {
  beforeEach(() => store.set({ live: { traces: [] }, mood: { kind: null, until: 0 }, log: [], gauges: {} }));

  it('hud.live fills the store and a successful skill makes Orion happy', () => {
    hud.live(ev({ phase: 'heard', state: 'end', label: 'Хвърли монета' }));
    hud.live(ev({ phase: 'skill', state: 'start', label: 'flip_coin', key: 'flip_coin' }));
    hud.live(ev({ phase: 'skill', state: 'end', label: 'flip_coin', key: 'flip_coin', ok: true, ms: 3 }));
    hud.live(ev({ phase: 'done', state: 'end', label: 'done', ok: true, ms: 50 }));
    expect(store.get().live.traces[0].done).toBe(true);
    expect(store.get().mood.kind).toBe('happy');
  });

  it('a failed skill makes Orion confused', () => {
    hud.live(ev({ phase: 'heard', state: 'end', label: 'x' }));
    hud.live(ev({ phase: 'skill', state: 'end', label: 'a', key: 'a', ok: false }));
    expect(store.get().mood.kind).toBe('confused');
  });

  it('toolDone writes the duration on the journal entry', () => {
    hud.addLog('tool', 'flip_coin');
    hud.toolDone('flip_coin', 'Падна се ези.', true, 412);
    expect(store.get().log.at(-1).ms).toBe(412);
  });

  it('setGauges stores the values', () => {
    hud.setGauges({ gpu: 20, cpu: 5 });
    expect(store.get().gauges).toEqual({ gpu: 20, cpu: 5 });
  });
});
