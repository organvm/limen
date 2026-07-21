'use client';

import React, { useEffect, useRef, useState } from 'react';

type MirrorPreset = 'Obsidian Chrome' | 'Silver Liquid' | 'Neon Prismatic';
type SymmetryMode = 'Bilateral' | 'Radial' | 'Kaleidoscope';

export default function NarcissusPage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [preset, setPreset] = useState<MirrorPreset>('Obsidian Chrome');
  const [symmetry, setSymmetry] = useState<SymmetryMode>('Bilateral');
  const [refraction, setRefraction] = useState<number>(1.45);
  const [rippleSpeed, setRippleSpeed] = useState<number>(1.0);
  const [mousePos, setMousePos] = useState({ x: 0.5, y: 0.5 });
  const [isHovered, setIsHovered] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let animId: number;
    let time = 0;

    const glContext = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    const ctx2d = !glContext ? canvas.getContext('2d') : null;

    const render = () => {
      time += 0.02 * rippleSpeed;

      const width = canvas.width;
      const height = canvas.height;

      if (ctx2d) {
        // Fallback 2D WebGL-style Mirror Shader simulation
        ctx2d.fillStyle = preset === 'Obsidian Chrome' ? '#090d16' : preset === 'Silver Liquid' ? '#1e293b' : '#1e1b4b';
        ctx2d.fillRect(0, 0, width, height);

        const centerX = width / 2;
        const centerY = height / 2;
        const mousePixelX = mousePos.x * width;
        const mousePixelY = mousePos.y * height;

        // Draw distorted reflection rings
        ctx2d.save();
        ctx2d.translate(centerX, centerY);

        const ringCount = symmetry === 'Kaleidoscope' ? 12 : symmetry === 'Radial' ? 8 : 4;
        for (let i = 0; i < ringCount; i++) {
          const angle = (Math.PI * 2 * i) / ringCount + time * 0.2;
          const dist = 60 + Math.sin(time + i * 0.5) * 30 * refraction;

          const rx = Math.cos(angle) * dist;
          const ry = Math.sin(angle) * dist;

          const grad = ctx2d.createRadialGradient(rx, ry, 5, rx, ry, 80 * refraction);
          if (preset === 'Obsidian Chrome') {
            grad.addColorStop(0, 'rgba(56, 189, 248, 0.6)');
            grad.addColorStop(0.5, 'rgba(129, 140, 248, 0.2)');
            grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
          } else if (preset === 'Silver Liquid') {
            grad.addColorStop(0, 'rgba(241, 245, 249, 0.8)');
            grad.addColorStop(0.5, 'rgba(148, 163, 184, 0.3)');
            grad.addColorStop(1, 'rgba(15, 23, 42, 0)');
          } else {
            grad.addColorStop(0, 'rgba(244, 63, 94, 0.7)');
            grad.addColorStop(0.5, 'rgba(251, 146, 60, 0.4)');
            grad.addColorStop(1, 'rgba(168, 85, 247, 0)');
          }

          ctx2d.fillStyle = grad;
          ctx2d.beginPath();
          ctx2d.arc(rx, ry, 80 * refraction, 0, Math.PI * 2);
          ctx2d.fill();
        }
        ctx2d.restore();

        // Mouse specular reflection point
        if (isHovered) {
          const specGrad = ctx2d.createRadialGradient(mousePixelX, mousePixelY, 2, mousePixelX, mousePixelY, 120);
          specGrad.addColorStop(0, '#ffffff');
          specGrad.addColorStop(0.3, 'rgba(56, 189, 248, 0.5)');
          specGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');

          ctx2d.fillStyle = specGrad;
          ctx2d.beginPath();
          ctx2d.arc(mousePixelX, mousePixelY, 120, 0, Math.PI * 2);
          ctx2d.fill();
        }

        // Mirror surface grid lines
        ctx2d.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx2d.lineWidth = 1;
        for (let x = 0; x < width; x += 40) {
          ctx2d.beginPath();
          ctx2d.moveTo(x, 0);
          ctx2d.lineTo(x, height);
          ctx2d.stroke();
        }
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [preset, symmetry, refraction, rippleSpeed, mousePos, isHovered]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setMousePos({ x, y });
  };

  return (
    <main style={{ minHeight: '100vh', padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid #1f2937', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '2rem', color: '#a855f7', letterSpacing: '-0.025em' }}>
              Narcissus WebGL Mirror
            </h1>
            <p style={{ margin: '0.5rem 0 0 0', color: '#9ca3af', fontSize: '0.95rem' }}>
              Public Audience Surfaces • Optical Reflection & Chromatic Distortion Shader Surface
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span
              style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                backgroundColor: '#065f46',
                color: '#34d399',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              ● Webhook Gateway Active
            </span>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#6b7280' }}>Route: /api/webhook</p>
          </div>
        </div>
      </header>

      {/* Main Interactive Display */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        {/* WebGL Canvas Mirror */}
        <div
          style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '0.75rem',
            padding: '1.25rem',
            position: 'relative',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.875rem', color: '#a855f7', fontWeight: 600 }}>
              WebGL Mirror Surface [{preset}]
            </span>
            <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
              Mouse Refraction: ({mousePos.x.toFixed(2)}, {mousePos.y.toFixed(2)})
            </span>
          </div>

          <canvas
            ref={canvasRef}
            width={640}
            height={400}
            onMouseMove={handleMouseMove}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            style={{
              width: '100%',
              height: '400px',
              borderRadius: '0.5rem',
              backgroundColor: '#030712',
              display: 'block',
              cursor: 'crosshair',
            }}
          />
        </div>

        {/* Shader Control Panel */}
        <div
          style={{
            backgroundColor: '#111827',
            border: '1px solid #1f2937',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.5rem',
          }}
        >
          <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#f3f4f6' }}>Shader & Optics Controls</h3>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.5rem' }}>
              Mirror Finish
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {(['Obsidian Chrome', 'Silver Liquid', 'Neon Prismatic'] as MirrorPreset[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPreset(p)}
                  style={{
                    padding: '0.5rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #374151',
                    backgroundColor: preset === p ? '#a855f7' : '#1f2937',
                    color: preset === p ? '#ffffff' : '#d1d5db',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.5rem' }}>
              Symmetry Axis
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {(['Bilateral', 'Radial', 'Kaleidoscope'] as SymmetryMode[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setSymmetry(s)}
                  style={{
                    flex: 1,
                    padding: '0.4rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #374151',
                    backgroundColor: symmetry === s ? '#3b82f6' : '#1f2937',
                    color: '#ffffff',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.25rem' }}>
              Refraction Index: {refraction.toFixed(2)}
            </label>
            <input
              type="range"
              min="1.0"
              max="2.5"
              step="0.05"
              value={refraction}
              onChange={(e) => setRefraction(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: '#a855f7' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#9ca3af', marginBottom: '0.25rem' }}>
              Wavefront Frequency: {rippleSpeed.toFixed(1)}x
            </label>
            <input
              type="range"
              min="0.2"
              max="3.0"
              step="0.2"
              value={rippleSpeed}
              onChange={(e) => setRippleSpeed(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: '#a855f7' }}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
