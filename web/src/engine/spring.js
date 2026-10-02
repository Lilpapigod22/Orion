/* Springs: a value follows its target with velocity — soft, natural movement instead of jumps. */
export const spring = (x = 0) => ({ x, v: 0, target: x });

export function stepSpring(s, dt, stiffness = 120, damping = 14) {
  const a = stiffness * (s.target - s.x) - damping * s.v;
  s.v += a * dt;
  s.x += s.v * dt;
  return s.x;
}
