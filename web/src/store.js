/* The window's state — one store; Python changes it through window.hud (bridge.js),
   the components read it with useStore(selector). */
import { useSyncExternalStore } from 'react';

let state = {
  mode: 'boot',                    // boot, idle, standby, calibrating, listening, thinking, speaking, offline, approval
  booted: false,                   // the system check gives way to the subtitles
  bootLines: [],                   // [{ id, label, status: 'ok' | 'run' | 'fail', detail }]
  subtitle: { text: '', user: false, n: 0 },
  log: [],                         // [{ id, kind, time, text, chart? }]
  telemetry: 'core · —',
  test: null,                      // chip text while test mode works
  reels: null,                     // chip text while reels are being made
  approval: null,                  // code for approval or an action to confirm
  switches: { wake: false, voice: true, test: false },
  maximized: false,
};

const listeners = new Set();

export const store = {
  get: () => state,
  set(patch) {
    state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
    listeners.forEach((listener) => listener());
  },
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

// The selector must return a part of the state as it is (not a new object) — otherwise React redraws forever.
export const useStore = (selector) => useSyncExternalStore(store.subscribe, () => selector(state));
