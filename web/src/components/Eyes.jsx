import { Component, useState } from 'react';
import { api } from '../util.js';
import { Eyes2D } from './Eyes2D.jsx';
import Eyes3D from './Eyes3D.jsx';

export function webglAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

// A 3D failure (lost context, driver) must never leave the centre empty — 2D eyes take over.
class Fallback extends Component {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  componentDidCatch(error) { api()?.report_error(`3D eyes: ${error.message}`); }

  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

// Orion's eyes in the centre of the network. The 2D network canvas lies on top and leaves a hole here.
export function Eyes({ layout }) {
  const [three] = useState(webglAvailable);
  if (!layout) return null;
  const size = layout.core * 1.9;
  const style = { left: layout.x - size / 2, top: layout.y - size / 2, width: size, height: size };
  const flat = <div className="eyes eyes--2d" style={style} aria-hidden="true"><Eyes2D /></div>;
  if (!three) return flat;
  return (
    <Fallback fallback={flat}>
      <div className="eyes eyes--3d" style={style} aria-hidden="true"><Eyes3D /></div>
    </Fallback>
  );
}
