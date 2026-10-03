/* What the buttons and keys do — shared by the components and the 3D network. */
import { store } from './store.js';
import { api } from './util.js';
import { voice } from './engine/voice.js';

let input = null;
export const registerInput = (element) => { input = element; };

// The input box is always ready unless the user has chosen another element.
export function refocus() {
  const active = document.activeElement;
  if (!active || active === document.body) input?.focus({ preventScroll: true });
}

export function focusInput() {
  input?.focus();
}

// Speak. A tap while Orion is speaking = interrupt.
export function talk() {
  if (voice.playing) { voice.stop(); return; }
  api()?.listen();
}

export function send(text) {
  if (voice.playing) voice.stop();
  api()?.send_text(text);
}

// Decision on code written by Orion or an action to confirm. The dialog hides at once; Python carries on.
export function decide(approved) {
  if (voice.playing) voice.stop();
  store.set({ approval: null });
  api()?.resolve_approval(approved);
}

export function setSwitch(name, checked) {
  store.set((s) => ({ switches: { ...s.switches, [name]: checked } }));
  if (name === 'wake') api()?.set_always_listen(checked);
  if (name === 'voice') {
    if (!checked && voice.playing) voice.stop();
    api()?.set_muted(!checked);
  }
  if (name === 'test') api()?.set_test_mode(checked);
  if (name === 'demo') api()?.set_demo_mode(checked);
  if (name === 'real') api()?.set_real_trading(checked);
}

export function toggleMaximize() {
  const maximized = !store.get().maximized;
  store.set({ maximized });
  api()?.window_maximize(maximized);
}
