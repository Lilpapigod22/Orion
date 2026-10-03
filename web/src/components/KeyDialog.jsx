import { useEffect, useRef, useState } from 'react';
import { store, useStore } from '../store.js';
import { api } from '../util.js';

// The Hyperliquid API key — typed here, never in the chat, so it reaches neither the journal nor the model.
export function KeyDialog() {
  const dialog = useStore((s) => s.keyDialog);
  const [address, setAddress] = useState('');
  const [key, setKey] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const first = useRef(null);
  useEffect(() => {
    if (!dialog) return;
    setAddress('');
    setKey('');
    setMessage('');
    first.current?.focus();
  }, [dialog]);
  if (!dialog) return null;
  const testnet = dialog.network !== 'mainnet';
  const close = () => store.set({ keyDialog: null });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api()?.save_trading_key(dialog.network, address.trim(), key.trim());
      if (result?.ok) close();
      else setMessage(result?.message || 'Could not save the key.');
    } finally {
      setBusy(false);
      setKey('');
    }
  };
  return (
    <form className="approval key-dialog" role="dialog" aria-labelledby="key-title" onSubmit={save}>
      <p className="approval-kind">{testnet ? 'Hyperliquid · TESTNET' : 'Hyperliquid · REAL MONEY'}</p>
      <h2 className="approval-title" id="key-title">Connect the API wallet</h2>
      <p className="key-warning">
        Никога не поставяйте думите за възстановяване (seed фразата). Тук — само API ключът от{' '}
        {testnet ? 'app.hyperliquid-testnet.xyz/API' : 'app.hyperliquid.xyz/API'}: той търгува, но не може да тегли.
      </p>
      <label className="key-field">
        Wallet address (Trust Wallet)
        <input ref={first} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="0x…"
          spellCheck={false} autoComplete="off" />
      </label>
      <label className="key-field">
        API wallet private key
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="0x…"
          spellCheck={false} autoComplete="off" />
      </label>
      {message && <p className="key-message" role="alert">{message}</p>}
      <div className="approval-actions">
        <button type="button" className="btn-reject" onClick={close}>Cancel</button>
        <button type="submit" className="btn-accept" disabled={busy || !address || !key}>Save key</button>
      </div>
    </form>
  );
}
