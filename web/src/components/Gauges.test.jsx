import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Gauges } from './Gauges.jsx';

describe('Gauges', () => {
  it('shows the values it has and hides the missing ones', () => {
    store.set({ gauges: { cpu: 12, ram: 48 }, live: { traces: [] } });
    const { container } = render(<Gauges />);
    expect(container.textContent).toContain('CPU 12%');
    expect(container.textContent).toContain('RAM 48%');
    expect(container.textContent).not.toContain('GPU');
  });

  it('shows GPU, video memory and the last answer', () => {
    store.set({ gauges: { gpu: 22, vramUsed: 8192, vramTotal: 10240, cpu: 5, ram: 40 }, live: { traces: [{
      id: 1, done: true, ok: true, ms: 2100, steps: [{ phase: 'thinking', state: 'done', detail: { tps: 34.2 } }] }] } });
    const { container } = render(<Gauges />);
    expect(container.textContent).toContain('GPU 22%');
    expect(container.textContent).toContain('VRAM 8.0/10 GB');
    expect(container.textContent).toContain('34.2 tok/s');
    expect(container.textContent).toContain('last 2.1 s');
  });
});
