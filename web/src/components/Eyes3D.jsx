import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { createRig } from '../engine/eyesRig.js';
import { gaze } from '../engine/gaze.js';
import { pulse } from '../engine/pulse.js';

const FPS = 30;

// Renders on demand, 30 times a second at most and never while the window is hidden.
function Ticker() {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    const timer = setInterval(() => { if (!document.hidden) invalidate(); }, 1000 / FPS);
    return () => clearInterval(timer);
  }, [invalidate]);
  return null;
}

function Face() {
  const rig = useMemo(() => createRig(), []);
  const material = useMemo(() => new THREE.MeshBasicMaterial({ color: '#7FDBFF' }), []);
  const box = useMemo(() => new RoundedBoxGeometry(1.25, 1.5, 0.4, 6, 0.42), []);
  const arc = useMemo(() => new THREE.TorusGeometry(0.62, 0.16, 12, 40, Math.PI), []);
  const bar = useMemo(() => new THREE.BoxGeometry(0.12, 1, 0.12), []);
  const head = useRef();
  const eyes = useRef([]);
  const arcs = useRef([]);
  const bars = useRef([]);
  const last = useRef(performance.now());
  useFrame(() => {
    const now = performance.now();
    const dt = Math.min(0.1, (now - last.current) / 1000);
    last.current = now;
    const pose = rig.step(dt, pulse.expr, gaze, pulse.spectrum, Date.now(), pulse.t);
    const [r, g, b] = pulse.color;
    material.color.setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace).multiplyScalar(0.8);
    head.current.position.set(pose.lookX, pose.lookY, 0);
    head.current.rotation.set(-pose.lookY * 0.4, pose.lookX * 0.5, pose.tilt);
    head.current.scale.setScalar(pose.scale);
    const happy = pose.shape === 'arc';
    eyes.current.forEach((eye, i) => {
      eye.visible = !happy;
      eye.scale.set(1, pose.open * (i ? pose.right : 1), 1);
    });
    arcs.current.forEach((a) => { a.visible = happy; });
    bars.current.forEach((b, i) => { b.scale.y = pose.bars[i]; });
  });
  return (
    <group ref={head}>
      {[-1.25, 1.25].map((x, i) => (
        <mesh key={`eye${x}`} ref={(el) => { eyes.current[i] = el; }} geometry={box} material={material} position={[x, 0, 0]} />
      ))}
      {[-1.25, 1.25].map((x, i) => (
        <mesh key={`arc${x}`} ref={(el) => { arcs.current[i] = el; }} geometry={arc} material={material}
              position={[x, -0.25, 0]} visible={false} />
      ))}
      {Array.from({ length: 25 }, (_, i) => (
        <mesh key={i} ref={(el) => { bars.current[i] = el; }} geometry={bar} material={material} position={[(i - 12) * 0.2, -1.9, 0]} />
      ))}
    </group>
  );
}

export default function Eyes3D() {
  return (
    <Canvas frameloop="demand" dpr={[1, 1.5]} camera={{ position: [0, 0, 9], fov: 40 }}
            gl={{ antialias: true, powerPreference: 'low-power', alpha: false }}
            onCreated={({ gl }) => gl.setClearColor('#000000')}>
      <Ticker />
      <Face />
      <EffectComposer>
        <Bloom intensity={0.7} luminanceThreshold={0.12} mipmapBlur radius={0.32} />
      </EffectComposer>
    </Canvas>
  );
}
