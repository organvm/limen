'use client';

import React, { useEffect, useRef, useState } from 'react';

interface CarouselSlide {
  id: string;
  title: string;
  subtitle: string;
  themeColor: string;
  accentColor: string;
  patternType: 'geometric' | 'sineWave' | 'particleField';
}

const slides: CarouselSlide[] = [
  {
    id: 'panel-01',
    title: 'Genesis Matrix',
    subtitle: 'Panel I: Geometric Lattice & Convergent Symmetry',
    themeColor: '#38bdf8',
    accentColor: '#818cf8',
    patternType: 'geometric',
  },
  {
    id: 'panel-02',
    title: 'Harmonic Resonance',
    subtitle: 'Panel II: Fluid Sine Waves & Phase Interferometry',
    themeColor: '#f43f5e',
    accentColor: '#fb923c',
    patternType: 'sineWave',
  },
  {
    id: 'panel-03',
    title: 'Starlight Swarm',
    subtitle: 'Panel III: Kinetic Particle Dynamics & Gravitational Field',
    themeColor: '#34d399',
    accentColor: '#a7f3d0',
    patternType: 'particleField',
  },
];

export default function TryptichPage() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isAnimating, setIsAnimating] = useState(true);
  const [rotationSpeed, setRotationSpeed] = useState(1);
  const [frameCount, setFrameCount] = useState(0);

  const canvasRef1 = useRef<HTMLCanvasElement | null>(null);
  const canvasRef2 = useRef<HTMLCanvasElement | null>(null);
  const canvasRef3 = useRef<HTMLCanvasElement | null>(null);

  const canvasRefs = [canvasRef1, canvasRef2, canvasRef3];

  useEffect(() => {
    let animId: number;
    let time = 0;

    const render = () => {
      time += 0.03 * rotationSpeed;
      setFrameCount((prev) => (prev + 1) % 100000);

      canvasRefs.forEach((ref, idx) => {
        const canvas = ref.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const width = canvas.width;
        const height = canvas.height;
        const slide = slides[idx];
        const isActive = idx === activeIndex;

        // Clear canvas
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(0, 0, width, height);

        // Border highlighting active slide
        if (isActive) {
          ctx.strokeStyle = slide.themeColor;
          ctx.lineWidth = 4;
          ctx.strokeRect(2, 2, width - 4, height - 4);
        }

        const centerX = width / 2;
        const centerY = height / 2;

        if (slide.patternType === 'geometric') {
          // Draw geometric spinning lattice
          ctx.save();
          ctx.translate(centerX, centerY);
          ctx.rotate(time * 0.5 * (idx + 1));
          for (let i = 0; i < 6; i++) {
            ctx.rotate((Math.PI * 2) / 6);
            ctx.strokeStyle = i % 2 === 0 ? slide.themeColor : slide.accentColor;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.rect(-40, -40, 80, 80);
            ctx.stroke();
          }
          ctx.restore();
        } else if (slide.patternType === 'sineWave') {
          // Draw sine waves
          ctx.strokeStyle = slide.themeColor;
          ctx.lineWidth = 3;
          ctx.beginPath();
          for (let x = 0; x < width; x += 4) {
            const y = centerY + Math.sin(x * 0.05 + time) * 35 * Math.cos(time * 0.5);
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();

          ctx.strokeStyle = slide.accentColor;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          for (let x = 0; x < width; x += 4) {
            const y = centerY + Math.cos(x * 0.04 - time * 1.2) * 25;
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
        } else if (slide.patternType === 'particleField') {
          // Draw particle field
          for (let i = 0; i < 30; i++) {
            const angle = i * 0.2 + time;
            const radius = 20 + (i * 3) % 60;
            const px = centerX + Math.cos(angle) * radius;
            const py = centerY + Math.sin(angle * 1.5) * radius;
            ctx.fillStyle = i % 3 === 0 ? slide.themeColor : slide.accentColor;
            ctx.beginPath();
            ctx.arc(px, py, 3 + (i % 3), 0, Math.PI * 2);
            ctx.fill();
          }
        }
      });

      if (isAnimating) {
        animId = requestAnimationFrame(render);
      }
    };

    if (isAnimating) {
      animId = requestAnimationFrame(render);
    } else {
      render();
    }

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [activeIndex, isAnimating, rotationSpeed]);

  const handlePrev = () => {
    setActiveIndex((prev) => (prev === 0 ? slides.length - 1 : prev - 1));
  };

  const handleNext = () => {
    setActiveIndex((prev) => (prev === slides.length - 1 ? 0 : prev + 1));
  };

  return (
    <main style={{ minHeight: '100vh', padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid #27272a', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '2rem', color: '#38bdf8', letterSpacing: '-0.025em' }}>
              Tryptich Canvas Carousel
            </h1>
            <p style={{ margin: '0.5rem 0 0 0', color: '#a1a1aa', fontSize: '0.95rem' }}>
              Public Audience Surfaces • Multi-Panel Interactive HTML5 Canvas Render Suite
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
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#71717a' }}>Route: /api/webhook</p>
          </div>
        </div>
      </header>

      {/* Control Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#18181b',
          border: '1px solid #27272a',
          borderRadius: '0.5rem',
          padding: '1rem 1.5rem',
          marginBottom: '2rem',
        }}
      >
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button
            onClick={handlePrev}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#27272a',
              color: '#f4f4f5',
              border: 'none',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            ← Previous
          </button>
          <button
            onClick={handleNext}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: '#38bdf8',
              color: '#09090b',
              border: 'none',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Next Panel →
          </button>
          <button
            onClick={() => setIsAnimating(!isAnimating)}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: isAnimating ? '#ef4444' : '#10b981',
              color: '#ffffff',
              border: 'none',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            {isAnimating ? 'Pause Canvas' : 'Play Canvas'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.875rem', color: '#a1a1aa', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            Velocity:
            <input
              type="range"
              min="0.2"
              max="3"
              step="0.2"
              value={rotationSpeed}
              onChange={(e) => setRotationSpeed(parseFloat(e.target.value))}
              style={{ accentColor: '#38bdf8' }}
            />
            <span style={{ color: '#f4f4f5', fontWeight: 600 }}>{rotationSpeed}x</span>
          </label>
          <span style={{ fontSize: '0.85rem', color: '#71717a' }}>Frame: #{frameCount}</span>
        </div>
      </div>

      {/* 3-Panel Tryptich Display */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        {slides.map((slide, idx) => {
          const isActive = idx === activeIndex;
          return (
            <div
              key={slide.id}
              onClick={() => setActiveIndex(idx)}
              style={{
                backgroundColor: '#18181b',
                border: isActive ? `2px solid ${slide.themeColor}` : '1px solid #27272a',
                borderRadius: '0.75rem',
                padding: '1.25rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                boxShadow: isActive ? `0 0 20px ${slide.themeColor}33` : 'none',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: slide.themeColor, textTransform: 'uppercase' }}>
                  {slide.id}
                </span>
                {isActive && (
                  <span
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.1rem 0.5rem',
                      borderRadius: '0.25rem',
                      backgroundColor: slide.themeColor,
                      color: '#09090b',
                      fontWeight: 700,
                    }}
                  >
                    ACTIVE
                  </span>
                )}
              </div>

              <canvas
                ref={canvasRefs[idx]}
                width={320}
                height={200}
                style={{
                  width: '100%',
                  height: '180px',
                  borderRadius: '0.5rem',
                  backgroundColor: '#0f172a',
                  display: 'block',
                }}
              />

              <div style={{ marginTop: '1rem' }}>
                <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#f4f4f5' }}>{slide.title}</h3>
                <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.8rem', color: '#a1a1aa' }}>{slide.subtitle}</p>
              </div>
            </div>
          );
        })}
      </section>

      {/* Active Panel Technical Card */}
      <section
        style={{
          backgroundColor: '#18181b',
          border: '1px solid #27272a',
          borderRadius: '0.75rem',
          padding: '1.5rem',
        }}
      >
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.25rem', color: '#f4f4f5' }}>
          Selected Composition Diagnostics: {slides[activeIndex].title}
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
          <div style={{ backgroundColor: '#09090b', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #27272a' }}>
            <span style={{ color: '#71717a', fontSize: '0.8rem' }}>Pattern Algorithm</span>
            <p style={{ margin: '0.25rem 0 0 0', fontWeight: 600, color: slides[activeIndex].themeColor }}>
              {slides[activeIndex].patternType}
            </p>
          </div>
          <div style={{ backgroundColor: '#09090b', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #27272a' }}>
            <span style={{ color: '#71717a', fontSize: '0.8rem' }}>Primary Palette</span>
            <p style={{ margin: '0.25rem 0 0 0', fontWeight: 600, color: slides[activeIndex].themeColor }}>
              {slides[activeIndex].themeColor}
            </p>
          </div>
          <div style={{ backgroundColor: '#09090b', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #27272a' }}>
            <span style={{ color: '#71717a', fontSize: '0.8rem' }}>Accent Palette</span>
            <p style={{ margin: '0.25rem 0 0 0', fontWeight: 600, color: slides[activeIndex].accentColor }}>
              {slides[activeIndex].accentColor}
            </p>
          </div>
          <div style={{ backgroundColor: '#09090b', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #27272a' }}>
            <span style={{ color: '#71717a', fontSize: '0.8rem' }}>Webhook Target</span>
            <p style={{ margin: '0.25rem 0 0 0', fontWeight: 600, color: '#38bdf8' }}>POST /api/webhook</p>
          </div>
        </div>
      </section>
    </main>
  );
}
