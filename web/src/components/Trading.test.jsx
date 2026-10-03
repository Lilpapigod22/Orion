import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { hud } from '../bridge.js';
import { store } from '../store.js';
import { Jobs } from './Jobs.jsx';
import { KeyDialog } from './KeyDialog.jsx';

describe('trading in the window', () => {
  afterEach(() => {
    cleanup();
    store.set({ trading: null, keyDialog: null, test: null, reels: null, approval: null });
    delete window.pywebview;
  });

  it('the chip shows the network and the open positions', () => {
    hud.setTrading({ network: 'testnet', positions: [
      { coin: 'BTC', side: 'long', pnl_usd: 5, pnl_pct: 1.04 },
      { coin: 'ETH', side: 'short', pnl_usd: -2, pnl_pct: -0.4 },
    ] });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('trading · TESTNET · BTC LONG +1.0% · ETH SHORT -0.4%');
  });

  it('no key or no positions on real money — no chip', () => {
    hud.setTrading(null);
    expect(store.get().trading).toBeNull();
    hud.setTrading({ network: 'mainnet', positions: [] });
    expect(store.get().trading).toBeNull();
  });

  it('the key goes to Python through its own call, never through the chat', async () => {
    const save = vi.fn().mockResolvedValue({ ok: true, message: 'ok' });
    const send = vi.fn();
    window.pywebview = { api: { save_trading_key: save, send_text: send } };
    hud.showKeyDialog({ network: 'testnet' });
    const { getByLabelText, getByText } = render(<KeyDialog />);
    expect(getByText('Hyperliquid · TESTNET')).toBeTruthy();
    fireEvent.change(getByLabelText(/Wallet address/), { target: { value: '0xabc' } });
    fireEvent.change(getByLabelText(/API wallet private key/), { target: { value: 'f'.repeat(64) } });
    fireEvent.click(getByText('Save key'));
    await waitFor(() => expect(store.get().keyDialog).toBeNull());
    expect(save).toHaveBeenCalledWith('testnet', '0xabc', 'f'.repeat(64));
    expect(send).not.toHaveBeenCalled();
  });

  it('a refused key keeps the dialog open with the reason', async () => {
    window.pywebview = { api: { save_trading_key: vi.fn().mockResolvedValue({ ok: false, message: 'Адресът трябва…' }) } };
    hud.showKeyDialog({ network: 'mainnet' });
    const { getByLabelText, getByText, findByRole } = render(<KeyDialog />);
    expect(getByText('Hyperliquid · REAL MONEY')).toBeTruthy();
    fireEvent.change(getByLabelText(/Wallet address/), { target: { value: '0x1' } });
    fireEvent.change(getByLabelText(/API wallet private key/), { target: { value: 'x' } });
    fireEvent.click(getByText('Save key'));
    expect((await findByRole('alert')).textContent).toContain('Адресът');
    expect(store.get().keyDialog).toEqual({ network: 'mainnet' });
  });
});
