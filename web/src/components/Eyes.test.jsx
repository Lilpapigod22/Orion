import { render } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { Eyes } from './Eyes.jsx';

// The 3D eyes (three.js) are not needed here and print a deprecation warning when loaded.
vi.mock('./Eyes3D.jsx', () => ({ default: () => null }));

// jsdom has no canvas: answer "no context" quietly instead of printing "Not implemented".
const realGetContext = HTMLCanvasElement.prototype.getContext;
beforeAll(() => { HTMLCanvasElement.prototype.getContext = () => null; });
afterAll(() => { HTMLCanvasElement.prototype.getContext = realGetContext; });

describe('Eyes', () => {
  it('falls back to 2D eyes without WebGL (jsdom has none)', () => {
    const { container } = render(<Eyes layout={{ x: 200, y: 150, core: 120 }} />);
    expect(container.querySelector('.eyes--2d canvas')).not.toBeNull();
  });
  it('waits for the layout', () => {
    const { container } = render(<Eyes layout={null} />);
    expect(container.innerHTML).toBe('');
  });
});
