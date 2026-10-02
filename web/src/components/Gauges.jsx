import { formatMs, lastTps } from '../engine/live.js';
import { useStore } from '../store.js';

// Live gauges in the top bar (from orion/telemetry.py) and the speed and time of the last answer.
export function Gauges() {
  const g = useStore((s) => s.gauges);
  const traces = useStore((s) => s.live.traces);
  const last = [...traces].reverse().find((t) => t.done);
  const items = [];
  if (g.gpu != null) items.push(['GPU', `${g.gpu}%`]);
  if (g.vramUsed != null && g.vramTotal) items.push(['VRAM', `${(g.vramUsed / 1024).toFixed(1)}/${Math.round(g.vramTotal / 1024)} GB`]);
  if (g.cpu != null) items.push(['CPU', `${g.cpu}%`]);
  if (g.ram != null) items.push(['RAM', `${g.ram}%`]);
  const tps = last ? lastTps(last) : null;
  if (tps != null) items.push(['speed', `${tps} tok/s`]);
  if (last?.ms != null) items.push(['last', formatMs(last.ms)]);
  if (!items.length) return null;
  return (
    <span className="gauges pywebview-drag-region">
      {items.map(([name, value]) => <span key={name} className="gauge"><i>{name}</i> {value}</span>)}
    </span>
  );
}
