import React, { useEffect, useState, useCallback } from 'react';
import { getEvents } from '../api/client';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { format, subMinutes, eachMinuteOfInterval } from 'date-fns';

const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#3b82f6',
};

function bucketsLastN(events, minutes = 30) {
  const now = new Date();
  const start = subMinutes(now, minutes);
  const minuteSlots = eachMinuteOfInterval({ start, end: now });

  const buckets = {};
  minuteSlots.forEach((m) => {
    const key = format(m, 'HH:mm');
    buckets[key] = { time: key, CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  });

  events.forEach((e) => {
    const ts = new Date(e.timestamp);
    if (ts < start) return;
    const key = format(ts, 'HH:mm');
    if (buckets[key]) {
      buckets[key][e.severity] = (buckets[key][e.severity] || 0) + 1;
    }
  });

  return Object.values(buckets);
}

export default function EventChart() {
  const [data, setData] = useState([]);
  const isLight = document.documentElement.dataset.theme === 'light';
  const chartGrid   = isLight ? '#cbd5e1' : '#374151';
  const chartMuted  = isLight ? '#64748b' : '#9ca3af';
  const chartBg     = isLight ? '#ffffff' : '#1f2937';
  const chartText   = isLight ? '#0f172a' : '#f9fafb';

  const fetchAndBucket = useCallback(async () => {
    try {
      const { data: events } = await getEvents({ limit: 500 });
      setData(bucketsLastN(events, 30));
    } catch (err) {
      console.error('EventChart error:', err);
    }
  }, []);

  useEffect(() => {
    fetchAndBucket();
    const interval = setInterval(fetchAndBucket, 10000);
    return () => clearInterval(interval);
  }, [fetchAndBucket]);

  return (
    <div style={{ background: 'var(--panel)', borderRadius: 12, padding: 16 }}>
      <h2 style={{ color: 'var(--text)', fontSize: 16, fontWeight: 600, marginBottom: 16, marginTop: 0 }}>Events (last 30 min)</h2>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <defs>
            {Object.entries(SEVERITY_COLORS).map(([sev, color]) => (
              <linearGradient key={sev} id={`grad-${sev}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.4} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
          <XAxis dataKey="time" tick={{ fill: chartMuted, fontSize: 10 }} />
          <YAxis tick={{ fill: chartMuted, fontSize: 10 }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ backgroundColor: chartBg, border: `1px solid ${chartGrid}`, borderRadius: 8 }}
            labelStyle={{ color: chartText }}
          />
          <Legend wrapperStyle={{ color: chartMuted, fontSize: 12 }} />
          {Object.entries(SEVERITY_COLORS).map(([sev, color]) => (
            <Area
              key={sev}
              type="monotone"
              dataKey={sev}
              stroke={color}
              fill={`url(#grad-${sev})`}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
