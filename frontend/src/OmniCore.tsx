import { useEffect, useRef } from "react";

/**
 * OMNI core: a hand-rolled canvas particle orb with thin orbiting rings.
 * Decorative only (aria-hidden, no text). Cheap by design: a few hundred points, ~30 fps cap,
 * paused while the tab is hidden. With prefers-reduced-motion it draws one static frame.
 */
type Props = { size?: number; points?: number; ambient?: boolean; className?: string };

const CYAN = "34,211,238";
const SKY = "56,189,248";
const MAGENTA = "217,70,239";

export default function OmniCore({ size = 220, points = 320, ambient = false, className = "" }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return; // no canvas support: the CSS glow behind it still shows
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const R = size * 0.3;
    const c = size / 2;
    // Fibonacci sphere: even point spread, deterministic (no Math.random in the render path).
    const pts = Array.from({ length: points }, (_, i) => {
      const y = 1 - (2 * (i + 0.5)) / points;
      const r = Math.sqrt(1 - y * y);
      const th = i * 2.399963229728653;
      return { x: Math.cos(th) * r, y, z: Math.sin(th) * r, m: i % 19 === 0 };
    });
    const rings = [
      { rx: 1.55, tilt: 0.35, speed: 0.6, phase: 0 },
      { rx: 1.9, tilt: -0.9, speed: -0.4, phase: 2 },
      { rx: 2.25, tilt: 1.35, speed: 0.25, phase: 4 },
    ];
    const bits = ambient
      ? Array.from({ length: 14 }, (_, i) => ({
          x: ((i * 37) % 100) / 100,
          y: ((i * 61) % 100) / 100,
          s: 0.02 + (i % 5) * 0.008,
          t: i % 3 === 0 ? "1" : i % 3 === 1 ? "0" : "01",
        }))
      : [];

    const draw = (t: number) => {
      ctx.clearRect(0, 0, size, size);
      const glow = ctx.createRadialGradient(c, c, R * 0.2, c, c, R * 2.1);
      glow.addColorStop(0, `rgba(${CYAN},0.22)`);
      glow.addColorStop(1, `rgba(${CYAN},0)`);
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, size, size);

      const a = t * 0.00022;
      const ca = Math.cos(a);
      const sa = Math.sin(a);
      for (const p of pts) {
        const x = p.x * ca + p.z * sa;
        const z = -p.x * sa + p.z * ca;
        const depth = (z + 1) / 2; // 0 far .. 1 near
        ctx.fillStyle = `rgba(${p.m ? MAGENTA : depth > 0.5 ? CYAN : SKY},${(0.15 + depth * 0.85).toFixed(2)})`;
        ctx.beginPath();
        ctx.arc(c + x * R, c + p.y * R, 0.5 + depth * 1.1, 0, 6.2832);
        ctx.fill();
      }
      ctx.lineWidth = 0.7;
      for (const r of rings) {
        ctx.save();
        ctx.translate(c, c);
        ctx.rotate(r.tilt);
        ctx.strokeStyle = `rgba(${CYAN},0.28)`;
        ctx.beginPath();
        ctx.ellipse(0, 0, R * r.rx * 0.62, R * r.rx * 0.2, 0, 0, 6.2832);
        ctx.stroke();
        const ang = r.phase + t * 0.001 * r.speed;
        ctx.fillStyle = `rgba(${SKY},0.95)`;
        ctx.shadowColor = `rgb(${CYAN})`;
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(Math.cos(ang) * R * r.rx * 0.62, Math.sin(ang) * R * r.rx * 0.2, 1.8, 0, 6.2832);
        ctx.fill();
        ctx.restore();
      }
      if (bits.length) {
        ctx.font = "11px ui-monospace, Menlo, Consolas, monospace";
        for (const b of bits) {
          const yy = (b.y - (t * 0.00002 * (b.s * 40)) + 1) % 1;
          ctx.fillStyle = `rgba(${CYAN},${(0.1 + 0.3 * Math.abs(Math.sin(yy * 6.28))).toFixed(2)})`;
          ctx.fillText(b.t, b.x * size, yy * size);
        }
      }
    };

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) {
      draw(4000); // one static frame, no animation loop
      return;
    }
    let raf = 0;
    let last = 0;
    const loop = (t: number) => {
      raf = requestAnimationFrame(loop);
      if (document.hidden || t - last < 33) return;
      last = t;
      draw(t);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [size, points, ambient]);

  return <canvas ref={ref} className={`omni-core ${className}`} style={{ width: size, height: size }} aria-hidden="true" />;
}
