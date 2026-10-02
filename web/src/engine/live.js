/* The live board's data: every request is a trace of steps (from orion/live.py). Pure functions — the
   store keeps the result, the components only read it. */
export const PIPELINE = ['heard', 'understood', 'thinking', 'skill', 'speaking'];
const KEEP = 20;

export function applyLiveEvent(live, event, now = Date.now()) {
  let traces = live.traces;
  if (event.phase === 'heard' && !traces.some((t) => t.id === event.trace)) {
    const trace = { id: event.trace, text: event.label, source: event.detail?.source || 'text', startedAt: now,
      steps: [], done: false, ok: null, ms: null };
    traces = [...traces, trace].slice(-KEEP);
  }
  const index = traces.findIndex((t) => t.id === event.trace);
  if (index < 0 || traces[index].done) return live;
  const trace = { ...traces[index], steps: [...traces[index].steps] };
  if (event.phase === 'done') {
    Object.assign(trace, { done: true, ok: event.ok, ms: event.ms });
  } else if (event.state === 'start') {
    trace.steps.push({ key: event.key, phase: event.phase, label: event.label, detail: event.detail, state: 'run',
      ok: null, ms: null, t: event.t });
  } else {
    const at = findLast(trace.steps, (s) => s.key === event.key && s.state === 'run');
    if (event.state === 'update') {
      if (at < 0) return live;
      trace.steps[at] = { ...trace.steps[at], label: event.label, detail: { ...trace.steps[at].detail, ...event.detail } };
    } else if (at >= 0) {
      const step = trace.steps[at];
      trace.steps[at] = { ...step, label: event.label || step.label, detail: { ...step.detail, ...event.detail },
        state: 'done', ok: event.ok, ms: event.ms };
    } else {
      trace.steps.push({ key: event.key, phase: event.phase, label: event.label, detail: event.detail, state: 'done',
        ok: event.ok, ms: event.ms, t: event.t });
    }
  }
  const next = [...traces];
  next[index] = trace;
  return { ...live, traces: next };
}

function findLast(items, test) {
  for (let i = items.length - 1; i >= 0; i--) if (test(items[i])) return i;
  return -1;
}

export function phaseSummary(trace) {
  return PIPELINE.map((phase) => {
    const steps = trace.steps.filter((s) => s.phase === phase);
    const status = !steps.length ? 'idle'
      : steps.some((s) => s.state === 'run') ? 'run'
      : steps.some((s) => s.ok === false) ? 'fail' : 'done';
    const times = steps.map((s) => s.ms).filter((ms) => ms != null);
    return { phase, status, ms: times.length ? times.reduce((a, b) => a + b, 0) : null, steps };
  });
}

export function nowLine(trace) {
  if (!trace || trace.done) return '';
  const running = [...trace.steps].reverse().find((s) => s.state === 'run');
  if (!running) return '';
  if (running.phase === 'thinking') return (running.detail?.text || '').replace(/\s+/g, ' ').trim().slice(-140);
  if (running.phase === 'skill') return `skill · ${running.label}`;
  return running.label;
}

export function lastTps(trace) {
  const ends = trace.steps.filter((s) => s.phase === 'thinking' && s.detail?.tps != null);
  return ends.length ? ends.at(-1).detail.tps : null;
}

export const formatMs = (ms) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
