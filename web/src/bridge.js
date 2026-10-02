/* ==========================================================================
   The link with Python.

   Python -> window:  window.hud.<function>(...)         (app.py -> Orion.hud)
   Window -> Python:  window.pywebview.api.<method>(...) (app.py -> HudApi)

   window.hud exists before React draws anything, so no call from Python is lost.
   ========================================================================== */
import { focusInput, refocus } from './actions.js';
import { mind } from './engine/mind.js';
import { MODES } from './engine/reactor.js';
import { voice } from './engine/voice.js';
import { store } from './store.js';
import { api, clockTime } from './util.js';

window.addEventListener('error', (e) => api()?.report_error(`${e.message} @ ${e.lineno}`));
window.addEventListener('unhandledrejection', (e) => api()?.report_error(String(e.reason)));

let nextId = 1;
const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export const hud = {
  setState(mode) {
    if (!MODES[mode]) return;
    // While audio is playing, the reactor stays in “speaking” mode.
    if (voice.playing && mode !== 'speaking') return;
    store.set({ mode });
  },

  addLog(kind, text, chart = null) {
    store.set((s) => ({ log: [...s.log, { id: nextId++, kind, time: clockTime(), text, chart }] }));
  },

  setSubtitle(text, user = false) {
    store.set((s) => ({ subtitle: { text, user, n: s.subtitle.n + 1 } }));
  },

  say(text) {
    this.addLog('orion', text);
    this.setSubtitle(text);
    refocus();
  },

  heard(text) {
    this.setSubtitle(text, true);
  },

  playAudio(b64) {
    // Voice was switched off while the answer was being synthesised — do not play it.
    if (!store.get().switches.voice) { api()?.speech_finished(); return; }
    voice.play(b64);
  },
  stopAudio() { voice.stop(); },

  bootLine(id, label, status, detail) {
    store.set((s) => {
      const line = { id, label, status, detail: detail || '' };
      const known = s.bootLines.some((l) => l.id === id);
      return { bootLines: known ? s.bootLines.map((l) => (l.id === id ? line : l)) : [...s.bootLines, line] };
    });
  },

  // On success the list of checks gives way to the subtitles.
  // On failure it stays on screen so you can see what is wrong.
  bootDone(ok) {
    if (ok) setTimeout(() => store.set({ booted: true }), 700);
    else this.setState('offline');
  },

  // What Orion is thinking and doing — shown in the 3D network (engine/mind.js).
  toolStart(name, args, module, label) { mind.taskStart(name, args, module, label); },
  toolDone(name, result, ok) { mind.taskDone(name, result, ok); },
  thought(text) { mind.think(text); },
  setReminders(items) { mind.setReminders(items); },

  // The market analysis chart — a journal entry with a legend and values on hover.
  showChart(data) { this.addLog('chart', '', data); },

  setTelemetry({ model, skills, docs, lessons }) {
    store.set({ telemetry: [model, count(skills, 'skill', 'skills'), `${docs} docs`, count(lessons, 'lesson', 'lessons')].join(' · ') });
  },

  // Code written by Orion: shows it and waits for a decision. For a fix — only the difference.
  showApproval({ kind, title, reason, code, diff, warnings, tools, attempts }) {
    store.set({
      approval: {
        confirm: false,
        kind: `${kind === 'create' ? 'New skill' : 'Skill fix'} · passed checks on attempt ${attempts}`,
        title: tools.length ? tools.join(', ') : title,
        reason, warnings, code, diff, accept: 'Approve and enable',
      },
    });
  },

  // An action that cannot be undone (sending an email, deleting): the text and a button.
  showConfirm({ title, summary, body, accept }) {
    store.set({ approval: { confirm: true, kind: title, title: summary, reason: '', warnings: [], code: body, diff: '', accept } });
  },

  hideApproval() {
    store.set({ approval: null });
    refocus();
  },

  setSwitch(name, value) {
    if (!['wake', 'voice', 'test'].includes(name)) return;
    store.set((s) => ({ switches: { ...s.switches, [name]: Boolean(value) } }));
    if (name === 'test' && !value) this.setTest({ active: false });
  },

  // Test mode: how far the self-check has got (at the top, next to the status).
  setTest({ active, text }) {
    store.set({ test: active ? `test · ${text || 'preparing'}` : null });
  },

  // Reels from YouTube: how far the background job has got.
  setReels({ active, text }) {
    store.set({ reels: active ? `reels · ${text || 'starting'}` : null });
  },
};
window.hud = hud;

// Start-up: Python says what is switched on.
let started = false;
async function start() {
  if (started || !api()?.start) return;
  started = true;
  const settings = await api().start();
  hud.setSwitch('wake', settings.alwaysListen);
  hud.setSwitch('voice', !settings.muted);
  hud.setSwitch('test', settings.testMode);
  store.set({ maximized: Boolean(settings.maximized) });
  focusInput();
}
window.addEventListener('pywebviewready', start);
start();
