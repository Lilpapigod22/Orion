import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Pipeline } from './Pipeline.jsx';

const trace = {
  id: 1, text: 'Ще вали ли утре?', source: 'text', startedAt: 0, done: false, ok: null, ms: null,
  steps: [
    { key: 'heard', phase: 'heard', label: 'Ще вали ли утре?', detail: { source: 'text' }, state: 'done', ok: true, ms: null, t: 0 },
    { key: 'understood', phase: 'understood', label: 'quick command', detail: { command: 'will_it_rain' }, state: 'done', ok: true, ms: 3, t: 0 },
    { key: 'will_it_rain', phase: 'skill', label: 'will_it_rain', detail: { args: { day: 'утре' } }, state: 'run', ok: null, ms: null, t: 0.01 },
  ],
};

describe('Pipeline', () => {
  afterEach(cleanup);
  beforeEach(() => store.set({ live: { traces: [trace] } }));

  it('shows the five steps and highlights the running one', () => {
    render(<Pipeline />);
    const steps = screen.getAllByRole('button');
    expect(steps.map((b) => b.dataset.phase)).toEqual(['heard', 'understood', 'thinking', 'skill', 'speaking']);
    expect(steps[3].className).toContain('is-run');
    expect(steps[1].textContent).toContain('3 ms');
    expect(screen.getByText('skill · will_it_rain')).toBeTruthy();
  });

  it('opens the details of a step', () => {
    render(<Pipeline />);
    fireEvent.click(screen.getAllByRole('button')[1]);
    expect(screen.getByRole('dialog').textContent).toContain('will_it_rain');
  });

  it('closes the details with Escape and returns focus to the step', async () => {
    render(<Pipeline />);
    const step = screen.getAllByRole('button')[1];
    fireEvent.click(step);
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(step);
  });

  it('shows nothing before the first request', () => {
    store.set({ live: { traces: [] } });
    const { container } = render(<Pipeline />);
    expect(container.innerHTML).toBe('');
  });
});
