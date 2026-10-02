import { motion } from 'motion/react';
import { formatMs } from '../engine/live.js';

const show = (value) => {
  if (value == null) return '—';
  if (typeof value === 'string') return value.length > 600 ? `${value.slice(0, 600)}…` : value;
  if (Array.isArray(value)) return value.join(', ') || '—';
  return JSON.stringify(value);
};

// What exactly happened in one step: every value the Python side sent, readable.
export function StepDetails({ phase, steps, onClose }) {
  return (
    <motion.div className="step-details" role="dialog" aria-label={`${phase} details`}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.16 }}>
      <button type="button" className="step-details-close" aria-label="Close" onClick={onClose}>×</button>
      {steps.length === 0 && <p className="step-details-empty">Nothing yet in this step.</p>}
      {steps.map((step, i) => (
        <section key={`${step.key}-${i}`}>
          <h4>{step.label}{step.ms != null && <small>{formatMs(step.ms)}</small>}{step.ok === false && <em>failed</em>}</h4>
          {step.detail && (
            <dl>
              {Object.entries(step.detail).map(([key, value]) => (
                <div key={key}><dt>{key}</dt><dd>{show(value)}</dd></div>
              ))}
            </dl>
          )}
        </section>
      ))}
    </motion.div>
  );
}
