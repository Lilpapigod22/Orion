/* What the eyes should look like for Orion's state — a pure function, so every state is testable. */
export const COLORS = { holo: [127, 219, 255], amber: [255, 181, 71], alert: [255, 90, 78], test: [140, 227, 176] };
export const MODES = ['boot', 'idle', 'standby', 'calibrating', 'listening', 'thinking', 'speaking', 'offline', 'approval'];
export const SLEEP_AFTER_MS = 10 * 60 * 1000;

export function expressionFor({ mode = 'idle', mood = null, testActive = false, idleMs = 0, now = 0 } = {}) {
  const e = { color: 'holo', open: 1, scale: 1, lookX: 0, lookY: 0, tilt: 0, shape: 'box', rightEye: 1,
    spin: 0.18, sleepy: false, wave: 'flat' };
  const moodKind = mood && now < mood.until ? mood.kind : null;
  if (testActive) e.color = 'test';
  if (['listening', 'standby', 'calibrating', 'approval'].includes(mode)) e.color = 'amber';
  if (mode === 'listening' || mode === 'calibrating') Object.assign(e, { scale: 1.15, spin: 0.45 });
  if (mode === 'thinking' || mode === 'boot') {
    Object.assign(e, { open: 0.55, lookX: 0.3, lookY: 0.3, spin: mode === 'boot' ? 0.9 : 2.6, wave: 'think' });
  }
  if (mode === 'speaking') Object.assign(e, { spin: 0.3, wave: 'voice' });
  if (moodKind === 'happy') e.shape = 'arc';
  if (moodKind === 'confused' || mode === 'offline') Object.assign(e, { color: 'alert', tilt: 0.18, rightEye: 0.65, spin: 0.05 });
  if (mode === 'idle' && !moodKind && idleMs > SLEEP_AFTER_MS) Object.assign(e, { sleepy: true, open: 0.35, lookY: -0.15, spin: 0.06 });
  return e;
}
