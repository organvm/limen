import React from 'react';

interface ConciergeRequest {
  id: string;
  guestName: string;
  room: string;
  category: 'Dining' | 'Transport' | 'Suite Service' | 'Special Event';
  status: 'Pending' | 'In Progress' | 'Fulfilled';
  requestedAt: string;
}

const mockRequests: ConciergeRequest[] = [
  { id: 'REQ-8801', guestName: 'Lady Eleanor Vance', room: 'Penthouse 902', category: 'Dining', status: 'In Progress', requestedAt: '14:32' },
  { id: 'REQ-8802', guestName: 'Lord Julian Sterling', room: 'Suite 405', category: 'Transport', status: 'Pending', requestedAt: '14:45' },
  { id: 'REQ-8803', guestName: 'Dr. Alistair Thorne', room: 'Suite 310', category: 'Suite Service', status: 'Fulfilled', requestedAt: '13:15' },
  { id: 'REQ-8804', guestName: 'Sophia Montgomery', room: 'Villa B', category: 'Special Event', status: 'Pending', requestedAt: '14:50' },
];

export default function HospesPage() {
  return (
    <main style={{ minHeight: '100vh', padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ borderBottom: '1px solid #334155', paddingBottom: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '2rem', color: '#38bdf8', letterSpacing: '-0.025em' }}>Hospes Concierge</h1>
            <p style={{ margin: '0.5rem 0 0 0', color: '#94a3b8', fontSize: '0.95rem' }}>
              Public Audience Surfaces • Unified Concierge & Guest Experience Interface
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ display: 'inline-block', padding: '0.25rem 0.75rem', borderRadius: '9999px', backgroundColor: '#065f46', color: '#34d399', fontSize: '0.85rem', fontWeight: 600 }}>
              ● Webhook Gateway Active
            </span>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#64748b' }}>Route: /api/webhook</p>
          </div>
        </div>
      </header>

      {/* Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem', padding: '1.25rem' }}>
          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Active Guest Suites</span>
          <h2 style={{ margin: '0.5rem 0 0 0', fontSize: '1.75rem', color: '#f8fafc' }}>24 / 28</h2>
        </div>
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem', padding: '1.25rem' }}>
          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Pending Requests</span>
          <h2 style={{ margin: '0.5rem 0 0 0', fontSize: '1.75rem', color: '#fbbf24' }}>2 Active</h2>
        </div>
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem', padding: '1.25rem' }}>
          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Fulfilled Today</span>
          <h2 style={{ margin: '0.5rem 0 0 0', fontSize: '1.75rem', color: '#34d399' }}>18 Requests</h2>
        </div>
        <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem', padding: '1.25rem' }}>
          <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>Avg Response Time</span>
          <h2 style={{ margin: '0.5rem 0 0 0', fontSize: '1.75rem', color: '#38bdf8' }}>3.2 min</h2>
        </div>
      </div>

      {/* Main Request Queue */}
      <section style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.75rem', overflow: 'hidden' }}>
        <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>Concierge Request Dispatcher</h3>
          <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Real-Time Queue</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ backgroundColor: '#0f172a', color: '#94a3b8', borderBottom: '1px solid #334155' }}>
                <th style={{ padding: '0.75rem 1.5rem' }}>ID</th>
                <th style={{ padding: '0.75rem 1.5rem' }}>Guest Name</th>
                <th style={{ padding: '0.75rem 1.5rem' }}>Suite/Room</th>
                <th style={{ padding: '0.75rem 1.5rem' }}>Category</th>
                <th style={{ padding: '0.75rem 1.5rem' }}>Status</th>
                <th style={{ padding: '0.75rem 1.5rem' }}>Time</th>
              </tr>
            </thead>
            <tbody>
              {mockRequests.map((req) => (
                <tr key={req.id} style={{ borderBottom: '1px solid #334155' }}>
                  <td style={{ padding: '1rem 1.5rem', fontWeight: 600, color: '#38bdf8' }}>{req.id}</td>
                  <td style={{ padding: '1rem 1.5rem', color: '#f8fafc' }}>{req.guestName}</td>
                  <td style={{ padding: '1rem 1.5rem', color: '#cbd5e1' }}>{req.room}</td>
                  <td style={{ padding: '1rem 1.5rem', color: '#cbd5e1' }}>{req.category}</td>
                  <td style={{ padding: '1rem 1.5rem' }}>
                    <span style={{
                      padding: '0.2rem 0.6rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      backgroundColor: req.status === 'Pending' ? '#78350f' : req.status === 'In Progress' ? '#1e3a8a' : '#064e3b',
                      color: req.status === 'Pending' ? '#fde047' : req.status === 'In Progress' ? '#93c5fd' : '#6ee7b7'
                    }}>
                      {req.status}
                    </span>
                  </td>
                  <td style={{ padding: '1rem 1.5rem', color: '#64748b' }}>{req.requestedAt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
