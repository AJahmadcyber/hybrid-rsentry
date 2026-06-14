import React, { useEffect, useState, useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { getEvents } from '../api/client';
import EventDetailModal from './EventDetailModal';

// ─── Response procedure mapping ───────────────────────────────────────────

const PROCEDURES = {
  CANARY_TOUCHED:          { name: 'Immediate Isolation Protocol',     color: '#f87171', bg: '#7f1d1d40', icon: '🛡' },
  ENTROPY_SPIKE:           { name: 'Entropy Containment Response',     color: '#fbbf24', bg: '#78350f40', icon: '📈' },
  PROCESS_ANOMALY:         { name: 'Process Lineage Investigation',    color: '#fb923c', bg: '#7c2d1240', icon: '🔍' },
  COMBINED_ALERT:          { name: 'Multi-Vector Threat Response',     color: '#f43f5e', bg: '#88172540', icon: '⚡' },
  CONTAINMENT_TRIGGERED:   { name: 'Host Isolation Initiated',         color: '#ef4444', bg: '#7f1d1d50', icon: '🔒' },
  CONTAINMENT_COMPLETE:    { name: 'Containment Verified',             color: '#22c55e', bg: '#14532d40', icon: '✅' },
  MARKOV_REPOSITION:       { name: 'Adaptive Canary Reposition',       color: '#818cf8', bg: '#1e1b4b40', icon: '🔄' },
  HEARTBEAT:               { name: 'System Heartbeat',                 color: '#6b7280', bg: '#11182740', icon: '💓' },
};

function getProcedure(event) {
  if (event.event_type === 'HEARTBEAT' && event.details?.sub_type === 'MARKOV_REPOSITION') {
    return PROCEDURES.MARKOV_REPOSITION;
  }
  return PROCEDURES[event.event_type] || { name: event.event_type, color: '#6b7280', bg: '#11182740', icon: '•' };
}

// ─── Single event row ──────────────────────────────────────────────────────

function EventRow({ event, isNew, onSelect }) {
  const proc = getProcedure(event);
  const isMov = event.event_type === 'HEARTBEAT' && event.details?.sub_type === 'MARKOV_REPOSITION';
  const eColor = (d) => d > 5 ? '#ef4444' : d > 3.5 ? '#f59e0b' : '#22c55e';

  return (
    <div
      onClick={() => onSelect(event)}
      style={{ borderLeft: `2px solid ${proc.color}`, paddingLeft: 10, paddingTop: 7, paddingBottom: 7, marginBottom: 8, borderRadius: '0 6px 6px 0', cursor: 'pointer', opacity: isNew ? 1 : 0.85, backgroundColor: proc.bg }}
      title="Click to view details"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13 }}>{proc.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: proc.color }}>{proc.name}</span>
        {isNew && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 10, background: 'rgba(234,179,8,0.15)', color: '#f59e0b', fontWeight: 700 }}>NEW</span>}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--muted)' }}>
          {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
        </span>
      </div>
      <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {event.file_path && !isMov && (
          <p style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-2)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{event.file_path}</p>
        )}
        {event.process_name && event.process_name !== 'unknown' && event.process_name !== 'markov-repositioner' && (
          <p style={{ fontSize: 10, color: 'var(--muted)', margin: 0 }}>Process: <span style={{ color: 'var(--text-2)' }}>{event.process_name}</span></p>
        )}
        {event.entropy_delta > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>Entropy:</span>
            <span style={{ width: 64, height: 5, borderRadius: 3, background: 'var(--border)', overflow: 'hidden', display: 'inline-block' }}>
              <span style={{ display: 'block', height: '100%', borderRadius: 3, width: `${Math.min(100, (event.entropy_delta / 8) * 100)}%`, backgroundColor: eColor(event.entropy_delta) }} />
            </span>
            <span style={{ fontSize: 10, color: eColor(event.entropy_delta) }}>{event.entropy_delta.toFixed(2)}</span>
          </div>
        )}
        {isMov && event.details?.moved?.length > 0 && (
          <>
            {event.details.moved.slice(0, 3).map((m, i) => (
              <p key={i} style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-2)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                <span style={{ color: '#06b6d4' }}>{m.from?.split('/').pop()}</span>
                <span style={{ color: 'var(--muted)' }}> → </span>
                <span style={{ color: 'var(--accent)' }}>{m.to?.replace('/home/', '~/')}</span>
              </p>
            ))}
            {event.details?.hotspots?.length > 0 && (
              <p style={{ fontSize: 10, color: 'var(--muted)', margin: 0 }}>
                Hotspots: {event.details.hotspots.slice(0, 2).map(h => h.split('/').pop()).join(', ')}
              </p>
            )}
          </>
        )}
        {event.canary_hit && <p style={{ fontSize: 10, color: 'var(--crit)', fontWeight: 700, margin: 0 }}>⚠ Canary file triggered</p>}
        <p style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--faint)', margin: 0 }}>{event.host_id}</p>
      </div>
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────────

const FILTER_OPTIONS = ['ALL', 'CANARY', 'ENTROPY', 'MARKOV', 'PROCESS', 'CONTAINMENT'];

export default function TacticalResponseLog({ liveEvent }) {
  const [events,        setEvents]        = useState([]);
  const [newIds,        setNewIds]        = useState(new Set());
  const [filter,        setFilter]        = useState('ALL');
  const [selectedEvent, setSelectedEvent] = useState(null);

  const fetchEvents = useCallback(async () => {
    try {
      const { data } = await getEvents({ limit: 100 });
      setEvents(data);
    } catch (err) { console.error(err); }
  }, []);

  useEffect(() => {
    fetchEvents();
    const t = setInterval(fetchEvents, 10000);
    return () => clearInterval(t);
  }, [fetchEvents]);

  // Inject live WS event instantly
  useEffect(() => {
    if (!liveEvent || liveEvent.type !== 'new_event') return;
    const synth = {
      id: liveEvent.event_id,
      host_id: liveEvent.host_id,
      event_type: liveEvent.event_type,
      severity: liveEvent.severity,
      file_path: liveEvent.file_path || '',
      entropy_delta: liveEvent.entropy_delta || 0,
      canary_hit: liveEvent.canary_hit || false,
      process_name: liveEvent.process_name || '',
      details: liveEvent.details || {},
      timestamp: new Date().toISOString(),
    };
    setEvents((prev) => {
      if (prev.find((e) => e.id === synth.id)) return prev;
      return [synth, ...prev];
    });
    setNewIds((prev) => new Set([...prev, synth.id]));
    setTimeout(() => setNewIds((prev) => { const n = new Set(prev); n.delete(synth.id); return n; }), 5000);
  }, [liveEvent]);

  const filtered = events.filter((e) => {
    if (filter === 'ALL') return true;
    if (filter === 'CANARY') return e.event_type === 'CANARY_TOUCHED' || e.canary_hit;
    if (filter === 'ENTROPY') return e.event_type === 'ENTROPY_SPIKE';
    if (filter === 'MARKOV') return e.event_type === 'HEARTBEAT' && e.details?.sub_type === 'MARKOV_REPOSITION';
    if (filter === 'PROCESS') return e.event_type === 'PROCESS_ANOMALY' || e.event_type === 'COMBINED_ALERT';
    if (filter === 'CONTAINMENT') return e.event_type === 'CONTAINMENT_TRIGGERED' || e.event_type === 'CONTAINMENT_COMPLETE';
    return true;
  });

  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 12, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <h2 style={{ color: 'var(--text)', fontSize: 13, fontWeight: 600, margin: 0 }}>Tactical Response Log</h2>
        <p style={{ color: 'var(--muted)', fontSize: 11, margin: '2px 0 0' }}>Live detection & automated response procedures</p>
      </div>

      {/* Filters */}
      <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 4, flexWrap: 'wrap', flexShrink: 0 }}>
        {FILTER_OPTIONS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '2px 8px', fontSize: 10, borderRadius: 4, fontWeight: 500, cursor: 'pointer',
              background: filter === f ? 'var(--accent)' : 'var(--panel-2)',
              color: filter === f ? '#fff' : 'var(--muted)',
              border: `1px solid ${filter === f ? 'transparent' : 'var(--border)'}`,
            }}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Events */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 10 }}>
        {filtered.length === 0 ? (
          <p style={{ color: 'var(--faint)', fontSize: 11, fontStyle: 'italic', textAlign: 'center', marginTop: 16 }}>No events yet. Run a simulation to see activity.</p>
        ) : (
          filtered.map((event) => (
            <EventRow key={event.id} event={event} isNew={newIds.has(event.id)} onSelect={setSelectedEvent} />
          ))
        )}
      </div>

      <EventDetailModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}
