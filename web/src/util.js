export const api = () => (window.pywebview && window.pywebview.api) || null;

export const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const pad = (n) => String(n).padStart(2, '0');
export const clockTime = (d = new Date(), seconds = false) =>
  `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ''}`;

export const STATE_LABELS = {
  boot: 'Starting',
  idle: 'Standing by',
  standby: 'Say “Orion”',
  calibrating: 'Calibrating microphone',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Speaking',
  offline: 'Core unavailable',
  approval: 'Awaiting approval',
};

export const STATUS_TEXT = {
  boot: 'Starting', offline: 'Offline', listening: 'Listening', standby: 'Listening',
  calibrating: 'Listening', thinking: 'Thinking', speaking: 'Speaking', idle: 'Online', approval: 'Waiting',
};

export const WHO = {
  user: 'Sir', orion: 'Orion', tool: '▸ skill', evolve: '▸ evolution', system: 'System', guide: '▸ tip',
  claude: '▸ Claude', chart: '▸ market', test: '▸ test', reels: '▸ reels', trading: '▸ trading',
};
