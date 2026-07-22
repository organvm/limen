"use client";

import React, { useState } from 'react';

export default function WaitlistLanding() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setStatus('loading');
    
    try {
      // Calling the existing Waitlist API endpoint
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });

      // Simple handling, assuming API returns 200 for success
      if (response.ok) {
        setStatus('success');
        setMessage('Welcome to the future. You are on the list.');
        setEmail('');
      } else {
        throw new Error('Failed to join waitlist');
      }
    } catch (error) {
      // For beta testing, we could also just show success unconditionally if API isn't live on same port
      // But we stick to error if fetch fails.
      setStatus('error');
      setMessage('Something went wrong. Please try again.');
    }
  };

  return (
    <main className="landing-container">
      <div className="glass-panel">
        <h1 className="hero-title">
          The Future of <span>Behavioral Blockchain</span>
        </h1>
        
        <p className="hero-subtitle">
          Join the exclusive closed beta. Be among the first to experience the next evolution in decentralized behavioral synthesis.
        </p>

        <form onSubmit={handleSubmit} className="waitlist-form" role="form" aria-label="Waitlist Form">
          <div className="input-group">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email address"
              className="email-input"
              aria-label="Email address"
              required
              disabled={status === 'loading' || status === 'success'}
            />
            <button 
              type="submit" 
              className="submit-btn"
              disabled={status === 'loading' || status === 'success' || !email}
            >
              {status === 'loading' ? 'Joining...' : 'Join Waitlist'}
            </button>
          </div>
          
          {message && (
            <div role="status" className={`status-message ${status === 'success' ? 'status-success' : 'status-error'}`}>
              {message}
            </div>
          )}
        </form>
      </div>
    </main>
  );
}
