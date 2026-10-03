import { useStore } from '../store.js';

// Background work — test mode, reels, open trades, a proposal waiting for approval — always in sight.
export function Jobs() {
  const test = useStore((s) => s.test);
  const reels = useStore((s) => s.reels);
  const trading = useStore((s) => s.trading);
  const approval = useStore((s) => s.approval);
  const jobs = [test && ['test', test], reels && ['reels', reels], trading && ['trading', trading],
    approval && ['approval', 'waiting for your approval']].filter(Boolean);
  if (!jobs.length) return null;
  return (
    <span className="jobs pywebview-drag-region">
      {jobs.map(([kind, text]) => <span key={kind} className={`tele-chip tele-chip--${kind}`}>{text}</span>)}
    </span>
  );
}
