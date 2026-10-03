import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hud } from '../bridge.js';
import { store } from '../store.js';
import { Console } from './Console.jsx';
import { Jobs } from './Jobs.jsx';

describe('the trading buttons', () => {
  afterEach(() => {
    cleanup();
    store.set({ trading: null, switches: { wake: false, voice: true, test: false, demo: false, real: false } });
    delete window.pywebview;
  });

  it('the console has Demo test and Real trade next to Test mode', () => {
    const { getByLabelText } = render(<Console />);
    expect(getByLabelText('Test mode')).toBeTruthy();
    expect(getByLabelText('Demo test')).toBeTruthy();
    expect(getByLabelText('Real trade')).toBeTruthy();
  });

  it('Real trade says that Orion trades by itself', () => {
    const { getByLabelText } = render(<Console />);
    expect(getByLabelText('Real trade').closest('label').title).toMatch(/Phantom Perps\): Orion trades by itself/);
  });

  it('switching them tells Python', () => {
    const demo = vi.fn();
    const real = vi.fn();
    window.pywebview = { api: { set_demo_mode: demo, set_real_trading: real } };
    const { getByLabelText } = render(<Console />);
    fireEvent.click(getByLabelText('Demo test'));
    fireEvent.click(getByLabelText('Real trade'));
    expect(demo).toHaveBeenCalledWith(true);
    expect(real).toHaveBeenCalledWith(true);
  });

  it('Python can move them', () => {
    hud.setSwitch('demo', true);
    hud.setSwitch('real', true);
    expect(store.get().switches.demo).toBe(true);
    expect(store.get().switches.real).toBe(true);
  });

  it('the chip shows the demo accounts even without a key', () => {
    hud.setTrading({ network: null, positions: [], demo: [{ name: 'демо 1', pct: 3.24 }, { name: 'смел', pct: -0.4 }] });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('trading · DEMO демо 1 +3.2% · DEMO смел -0.4%');
  });
});
