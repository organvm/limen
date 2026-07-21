import React from 'react';

interface CameraFeed {
  id: string;
  name: string;
  resolution: string;
  fps: number;
  status: 'ACTIVE' | 'STANDBY' | 'OFFLINE';
  bitrate: string;
  isProgramOutput?: boolean;
}

const cameraFeeds: CameraFeed[] = [
  { id: 'CAM-01', name: 'Stage Main Center', resolution: '4K (3840x2160)', fps: 60, status: 'ACTIVE', bitrate: '18.5 Mbps', isProgramOutput: true },
  { id: 'CAM-02', name: 'Crowd Wide Angle', resolution: '1080p (1920x1080)', fps: 60, status: 'ACTIVE', bitrate: '9.2 Mbps' },
  { id: 'CAM-03', name: 'Backstage VIP Lounge', resolution: '1080p (1920x1080)', fps: 30, status: 'STANDBY', bitrate: '4.8 Mbps' },
  { id: 'CAM-04', name: 'Aerial Overlay Drone', resolution: '4K (3840x2160)', fps: 60, status: 'STANDBY', bitrate: '16.0 Mbps' },
];

export default function LiveCameraPage() {
  return (
    <main style={{ minHeight: '100vh', padding: '2rem', maxWidth: '1280px', margin: '0 auto' }}>
      <header style={{ borderBottom: '1px solid #27272a', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <h1 style={{ margin: 0, fontSize: '2rem', color: '#ef4444', letterSpacing: '-0.025em' }}>Live Camera Broadcast</h1>
              <span style={{ backgroundColor: '#dc2626', color: '#ffffff', fontSize: '0.75rem', fontWeight: 700, padding: '0.2rem 0.6rem', borderRadius: '0.25rem', letterSpacing: '0.05em' }}>
                LIVE ON AIR
              </span>
            </div>
            <p style={{ margin: '0.5rem 0 0 0', color: '#a1a1aa', fontSize: '0.95rem' }}>
              Public Audience Surfaces • Multi-Camera Livestream Broadcast Framework
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ display: 'inline-block', padding: '0.25rem 0.75rem', borderRadius: '9999px', backgroundColor: '#14532d', color: '#4ade80', fontSize: '0.85rem', fontWeight: 600 }}>
              ● Webhook Broadcast Active
            </span>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#71717a' }}>Route: /api/webhook</p>
          </div>
        </div>
      </header>

      {/* Program Output Banner */}
      <section style={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '0.75rem', padding: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0, fontSize: '1.1rem', color: '#f4f4f5', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ color: '#ef4444' }}>●</span> Program Output (Master Feed)
          </h2>
          <span style={{ fontSize: '0.85rem', color: '#a1a1aa', fontFamily: 'monospace' }}>CAM-01 • 3840x2160 @ 60fps</span>
        </div>
        <div style={{ backgroundColor: '#000000', borderRadius: '0.5rem', height: '260px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', border: '1px solid #27272a', position: 'relative' }}>
          <div style={{ position: 'absolute', top: '12px', left: '12px', backgroundColor: 'rgba(0,0,0,0.75)', border: '1px solid #3f3f46', borderRadius: '0.25rem', padding: '0.25rem 0.5rem', fontSize: '0.75rem', color: '#ef4444', fontWeight: 700 }}>
            REC 🔴 01:42:19
          </div>
          <p style={{ color: '#71717a', fontSize: '1rem', margin: 0 }}>[ Master Video Feed Placeholder ]</p>
          <span style={{ color: '#52525b', fontSize: '0.85rem', marginTop: '0.5rem' }}>Stage Main Center Stream • Ultra HD</span>
        </div>
      </section>

      {/* Camera Grid */}
      <section>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.25rem', color: '#f4f4f5' }}>Multi-Camera Feed Matrix</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
          {cameraFeeds.map((feed) => (
            <div key={feed.id} style={{ backgroundColor: '#18181b', border: feed.isProgramOutput ? '2px solid #ef4444' : '1px solid #27272a', borderRadius: '0.5rem', padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                <span style={{ fontWeight: 700, color: '#ef4444', fontSize: '0.9rem' }}>{feed.id}</span>
                <span style={{
                  padding: '0.15rem 0.5rem',
                  borderRadius: '0.25rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  backgroundColor: feed.status === 'ACTIVE' ? '#14532d' : '#27272a',
                  color: feed.status === 'ACTIVE' ? '#4ade80' : '#a1a1aa'
                }}>
                  {feed.status}
                </span>
              </div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem', color: '#f4f4f5' }}>{feed.name}</h4>
              <div style={{ fontSize: '0.8rem', color: '#71717a', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span>Res: {feed.resolution}</span>
                <span>FPS: {feed.fps} frames/sec</span>
                <span>Bitrate: {feed.bitrate}</span>
              </div>
              {feed.isProgramOutput && (
                <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: '#ef4444', fontWeight: 600 }}>
                  ★ Active Program Target
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
