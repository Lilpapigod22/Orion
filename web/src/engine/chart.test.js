import { describe, expect, it } from 'vitest';
import { drawChart } from './chart.js';

// A canvas stand-in that records every drawing call in order.
function recordingCanvas() {
  const calls = [];
  const ctx = new Proxy({}, {
    get(target, name) {
      if (name in target) return target[name];
      if (name === 'measureText') return (text) => ({ width: String(text).length * 6 });
      if (name === 'createLinearGradient') return () => ({ addColorStop() {} });
      return (...args) => calls.push([name, ...args]);
    },
    set(target, name, value) { target[name] = value; return true; },
  });
  return { calls, canvas: { clientWidth: 600, clientHeight: 220, getContext: () => ctx } };
}

const forecast = {
  time: ['a', 'b', 'c', 'd'], close: [100, 101, 99, 100.5], sma20: [null, 100, 100, 100], sma50: [null, null, 100, 100],
  support: 98, resistance: 103, entry: 100.5, stop: 99.2, target: 103.1,
};

describe('chart', () => {
  it("a forecast's entry, stop and target labels are drawn over the price line", () => {
    const { calls, canvas } = recordingCanvas();
    drawChart(canvas, forecast);
    const lastStroke = calls.map((c) => c[0]).lastIndexOf('stroke');
    const labels = ['entry', 'stop', 'target'].map((word) =>
      calls.findIndex((c) => c[0] === 'fillText' && String(c[1]).startsWith(`${word} `)));
    labels.forEach((index) => expect(index).toBeGreaterThan(lastStroke));
  });

  it('a market analysis without levels draws no level labels', () => {
    const { calls, canvas } = recordingCanvas();
    drawChart(canvas, { ...forecast, entry: undefined, stop: undefined, target: undefined });
    expect(calls.some((c) => c[0] === 'fillText' && /^(entry|stop|target) /.test(String(c[1])))).toBe(false);
  });
});
