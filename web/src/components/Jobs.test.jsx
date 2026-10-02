import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { store } from '../store.js';
import { Jobs } from './Jobs.jsx';

describe('Jobs', () => {
  it('lists the background work', () => {
    store.set({ test: 'test · round 2', reels: 'reels · cutting reel 1/3', approval: { confirm: false } });
    const { container } = render(<Jobs />);
    expect(container.textContent).toContain('test · round 2');
    expect(container.textContent).toContain('reels · cutting reel 1/3');
    expect(container.textContent).toContain('waiting for your approval');
  });
  it('is empty when nothing runs', () => {
    store.set({ test: null, reels: null, approval: null });
    const { container } = render(<Jobs />);
    expect(container.innerHTML).toBe('');
  });
});
