'use client';

import React, { useEffect, useState } from 'react';

type MotionMode = 'Wave Cascade' | 'Elastic Bounce' | 'Variable Weight' | 'Orbiting Spiral';

const textPresets = [
  'KINETIC FLUIDITY',
  'AMPLIFY SURFACE ENGINE',
  'TYPOGRAPHIC CHOREOGRAPHY',
  'COMMERCE IN MOTION',
];

export default function BallerinaPage() {
  const [inputText, setInputText] = useState('KINETIC FLUIDITY');
  const [motionMode, setMotionMode] = useState<MotionMode>('Wave Cascade');
  const [speed, setSpeed] = useState<number>(1.2);
  const [amplitude, setAmplitude] = useState<number>(25);
  const [fontSize, setFontSize] = useState<number>(56);
  const [letterSpacing, setLetterSpacing] = useState<number>(8);
  const [time, setTime] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);

  useEffect(() => {
    let animId: number;
    let currTime = 0;

    const animate = () => {
      currTime += 0.04 * speed;
      setTime(currTime);
      if (isPlaying) {
        animId = requestAnimationFrame(animate);
      }
    };

    if (isPlaying) {
      animId = requestAnimationFrame(animate);
    }

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [speed, isPlaying]);

  const characters = inputText.split('');

  return (
    <main style={{ minHeight: '100vh', padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid #2e1065', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '2rem', color: '#c084fc', letterSpacing: '-0.025em' }}>
              Ballerina Kinetic Typography
            </h1>
            <p style={{ margin: '0.5rem 0 0 0', color: '#a78bfa', fontSize: '0.95rem' }}>
              Public Audience Surfaces • Real-Time Fluid Kinetic Text & Motion Choreography Engine
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
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#7c3aed' }}>Route: /api/webhook</p>
          </div>
        </div>
      </header>

      {/* Interactive Kinetic Typography Stage */}
      <section
        style={{
          backgroundColor: '#1e1b4b',
          border: '1px solid #3b0764',
          borderRadius: '0.75rem',
          padding: '4rem 2rem',
          marginBottom: '2rem',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '300px',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center' }}>
          {characters.map((char, idx) => {
            let translateY = 0;
            let scale = 1;
            let rotate = 0;
            let opacity = 1;
            let fontWeight = 700;

            const charPhase = idx * 0.35 + time;

            if (motionMode === 'Wave Cascade') {
              translateY = Math.sin(charPhase) * amplitude;
              rotate = Math.cos(charPhase * 0.5) * (amplitude * 0.3);
            } else if (motionMode === 'Elastic Bounce') {
              translateY = -Math.abs(Math.sin(charPhase * 1.5)) * amplitude * 1.2;
              scale = 1 + Math.sin(charPhase) * 0.15;
            } else if (motionMode === 'Variable Weight') {
              fontWeight = Math.floor(300 + Math.abs(Math.sin(charPhase)) * 600);
              translateY = Math.sin(charPhase) * (amplitude * 0.4);
            } else if (motionMode === 'Orbiting Spiral') {
              translateY = Math.sin(charPhase) * amplitude;
              rotate = charPhase * 20;
              opacity = 0.5 + Math.cos(charPhase) * 0.5;
            }

            return (
              <span
                key={idx}
                style={{
                  display: 'inline-block',
                  fontSize: `${fontSize}px`,
                  fontWeight: fontWeight,
                  color: idx % 2 === 0 ? '#e9d5ff' : '#c084fc',
                  marginRight: `${letterSpacing}px`,
                  transform: `translateY(${translateY}px) scale(${scale}) rotate(${rotate}deg)`,
                  opacity: opacity,
                  transition: isPlaying ? 'none' : 'transform 0.3s ease',
                  textShadow: '0 0 20px rgba(192, 132, 252, 0.5)',
                  whiteSpace: char === ' ' ? 'pre' : 'normal',
                }}
              >
                {char === ' ' ? '\u00A0' : char}
              </span>
            );
          })}
        </div>
      </section>

      {/* Control Dashboard */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
        {/* Left Column: Text & Mode Selector */}
        <div
          style={{
            backgroundColor: '#1e1b4b',
            border: '1px solid #3b0764',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#f3e8ff' }}>Text Input & Presets</h3>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.5rem' }}>
              Custom Phrase
            </label>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              style={{
                width: '100%',
                padding: '0.65rem 1rem',
                borderRadius: '0.375rem',
                border: '1px solid #5b21b6',
                backgroundColor: '#0f051d',
                color: '#faf5ff',
                fontSize: '1rem',
                fontWeight: 600,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.5rem' }}>
              Quick Presets
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {textPresets.map((preset) => (
                <button
                  key={preset}
                  onClick={() => setInputText(preset)}
                  style={{
                    padding: '0.4rem 0.8rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #5b21b6',
                    backgroundColor: inputText === preset ? '#7c3aed' : '#2e1065',
                    color: '#faf5ff',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.5rem' }}>
              Motion Mode
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              {(['Wave Cascade', 'Elastic Bounce', 'Variable Weight', 'Orbiting Spiral'] as MotionMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setMotionMode(mode)}
                  style={{
                    padding: '0.5rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #5b21b6',
                    backgroundColor: motionMode === mode ? '#c084fc' : '#2e1065',
                    color: motionMode === mode ? '#0f051d' : '#e9d5ff',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                  }}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Motion Dynamics Slider */}
        <div
          style={{
            backgroundColor: '#1e1b4b',
            border: '1px solid #3b0764',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#f3e8ff' }}>Choreography Parameters</h3>
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '0.375rem',
                border: 'none',
                backgroundColor: isPlaying ? '#ef4444' : '#10b981',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '0.8rem',
                cursor: 'pointer',
              }}
            >
              {isPlaying ? 'Pause Motion' : 'Play Motion'}
            </button>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.25rem' }}>
              Tempo Speed: {speed.toFixed(1)}x
            </label>
            <input
              type="range"
              min="0.2"
              max="3.0"
              step="0.1"
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: '#c084fc' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.25rem' }}>
              Wave Amplitude: {amplitude}px
            </label>
            <input
              type="range"
              min="5"
              max="60"
              step="5"
              value={amplitude}
              onChange={(e) => setAmplitude(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: '#c084fc' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.25rem' }}>
              Font Size: {fontSize}px
            </label>
            <input
              type="range"
              min="24"
              max="80"
              step="4"
              value={fontSize}
              onChange={(e) => setFontSize(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: '#c084fc' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', color: '#a78bfa', marginBottom: '0.25rem' }}>
              Letter Spacing: {letterSpacing}px
            </label>
            <input
              type="range"
              min="0"
              max="24"
              step="2"
              value={letterSpacing}
              onChange={(e) => setLetterSpacing(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: '#c084fc' }}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
