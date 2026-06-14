import React from 'react';
import StatsBar from '../components/StatsBar';
import EventChart from '../components/EventChart';
import AlertFeed from '../components/AlertFeed';
import HostRiskPanel from '../components/HostRiskPanel';
import TacticalResponseLog from '../components/TacticalResponseLog';

export default function Overview({ liveAlert, liveEvent, connected }) {
  return (
    <div className="flex-1 overflow-auto p-6">
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ color: 'var(--text)', fontSize: 20, fontWeight: 600, margin: 0 }}>Overview</h2>
          <p style={{ color: 'var(--muted)', fontSize: 13, margin: '2px 0 0' }}>Real-time ransomware detection status</p>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px',
          borderRadius: 8, fontSize: 13, fontWeight: 500,
          background: connected ? 'rgba(22,163,74,0.12)' : 'rgba(220,38,38,0.10)',
          border: `1px solid ${connected ? 'rgba(22,163,74,0.4)' : 'rgba(220,38,38,0.4)'}`,
          color: connected ? 'var(--ok)' : 'var(--crit)',
        }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: connected ? 'var(--ok)' : 'var(--crit)', display: 'inline-block' }} />
          {connected ? 'LIVE' : 'DISCONNECTED'}
        </div>
      </div>

      <StatsBar liveAlert={liveAlert} liveEvent={liveEvent} />

      {/* Event chart — full width */}
      <div className="mb-6">
        <EventChart />
      </div>

      {/* Bottom section: 4-column grid
          - Tactical Response Log : 1 col (25%)
          - Live Alert Feed       : 2 cols (50%) — widest, most important
          - Host Risk Panel       : 1 col (25%) — read-only risk view   */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6" style={{ minHeight: 420 }}>
        <div className="overflow-hidden" style={{ maxHeight: 560 }}>
          <TacticalResponseLog liveEvent={liveEvent} />
        </div>
        <div className="lg:col-span-2 overflow-hidden" style={{ maxHeight: 560 }}>
          <AlertFeed newAlert={liveAlert} />
        </div>
        <div style={{ maxHeight: 560 }}>
          <HostRiskPanel />
        </div>
      </div>
    </div>
  );
}
