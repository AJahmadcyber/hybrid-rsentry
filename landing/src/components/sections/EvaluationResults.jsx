import { motion, useInView } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

function useCounter(target, duration = 1800, active = false) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active) return;
    let startTime = null;
    const step = (ts) => {
      if (!startTime) startTime = ts;
      const progress = Math.min((ts - startTime) / duration, 1);
      setVal(Math.floor(progress * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration, active]);
  return val;
}

const AXES = [
  {
    id: 'efficacy',
    label: 'EFFICACY',
    question: 'Does it detect ransomware without false positives?',
    color: '#00ff88',
    headline: { display: '1.000', label: 'F1 Score', animated: false },
    stats: [
      { label: 'Recall',      value: '1.000' },
      { label: 'Precision',   value: '1.000' },
      { label: 'FPR',         value: '0.000' },
      { label: 'Specificity', value: '1.000' },
    ],
    trials: '270 trials · N=30 per group',
    note: '4 malicious families · 5 benign classes',
  },
  {
    id: 'efficiency',
    label: 'EFFICIENCY',
    question: 'How fast and at what cost to the host?',
    color: '#00f5ff',
    headline: { value: 150, suffix: 'ms', label: 'MTTD p50', animated: true },
    stats: [
      { label: 'Containment',  value: '91ms' },
      { label: 'Overhead',     value: '1.70µs/op' },
      { label: 'Files frozen', value: '2' },
      { label: 'LSM cost',     value: '+0.12µs' },
    ],
    trials: '120 malicious trials · N=30',
    note: 'akira · qilin · lockbit · entropy_only',
  },
  {
    id: 'robustness',
    label: 'ROBUSTNESS',
    question: 'Is every detection layer necessary?',
    color: '#b537f2',
    headline: { display: '4 / 4', label: 'Layers Necessary', animated: false },
    stats: [
      { label: 'Holm p-value',  value: '0.001' },
      { label: 'Off-diagonal',  value: 'p=1.000' },
      { label: 'Attack classes', value: '6' },
      { label: 'Trials',        value: '450' },
    ],
    trials: '450 trials · N=15',
    note: 'ablation × 6 attack classes · full necessity diagonal',
  },
];

function AxisCard({ axis, index }) {
  const ref = useRef();
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const count = useCounter(
    axis.headline.value || 0,
    1800,
    inView && axis.headline.animated
  );

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 60 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.6, delay: index * 0.12 }}
      className="glass rounded-2xl p-6 flex flex-col relative overflow-hidden"
      style={{
        border: `1px solid ${axis.color}40`,
        boxShadow: `0 20px 40px ${axis.color}15, 0 0 20px ${axis.color}10`,
      }}
    >
      {/* Top edge line */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${axis.color}, transparent)` }}
      />

      {/* COMPLETE badge */}
      <div className="absolute top-4 right-4">
        <span
          className="font-mono text-[9px] px-2 py-0.5 rounded-full font-bold"
          style={{
            background: `${axis.color}18`,
            border: `1px solid ${axis.color}60`,
            color: axis.color,
          }}
        >
          COMPLETE ✓
        </span>
      </div>

      {/* Axis label */}
      <p
        className="font-mono text-[10px] tracking-widest mb-1 uppercase"
        style={{ color: axis.color }}
      >
        {axis.label}
      </p>

      {/* Question */}
      <p className="font-mono text-[11px] text-gray-500 mb-5 leading-relaxed pr-16">
        {axis.question}
      </p>

      {/* Headline metric */}
      <div className="mb-5">
        <div
          className="font-mono font-bold stat-num"
          style={{
            fontSize: 'clamp(2rem, 4vw, 2.8rem)',
            color: axis.color,
            textShadow: `0 0 20px ${axis.color}60`,
          }}
        >
          {axis.headline.animated
            ? `${count}${axis.headline.suffix}`
            : axis.headline.display}
        </div>
        <div className="font-mono text-[10px] text-gray-500 tracking-widest uppercase mt-0.5">
          {axis.headline.label}
        </div>
      </div>

      {/* Supporting stats grid */}
      <div className="grid grid-cols-2 gap-2 mb-5 flex-1">
        {axis.stats.map((s) => (
          <div
            key={s.label}
            className="rounded-lg p-2"
            style={{ background: `${axis.color}08`, border: `1px solid ${axis.color}20` }}
          >
            <div
              className="font-mono font-bold text-xs stat-num"
              style={{ color: axis.color }}
            >
              {s.value}
            </div>
            <div className="font-mono text-[9px] text-gray-600 tracking-widest uppercase mt-0.5">
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="pt-3" style={{ borderTop: `1px solid ${axis.color}20` }}>
        <p className="font-mono text-[9px] text-gray-500">{axis.trials}</p>
        <p className="font-mono text-[9px] text-gray-700 mt-0.5">{axis.note}</p>
      </div>
    </motion.div>
  );
}

export default function EvaluationResults() {
  return (
    <section id="evaluation" className="section py-28 px-6">
      <div className="max-w-6xl mx-auto">

        {/* Section header */}
        <div className="text-center mb-16">
          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="font-mono text-xs tracking-widest text-[#ffd700] mb-3 uppercase"
          >
            Formal Evaluation
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
            className="font-heading font-bold"
            style={{ fontSize: 'clamp(1.8rem, 4vw, 3rem)', color: '#fff' }}
          >
            840 Trials.{' '}
            <span style={{ color: '#ffd700' }}>Three Axes. Zero Gaps.</span>
          </motion.h2>
          <motion.p
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
            className="font-mono text-xs text-gray-500 mt-3 max-w-xl mx-auto leading-relaxed"
          >
            Empirical evaluation across efficacy, efficiency, and robustness.
            NIST SP 800-61 · Wilson CIs · Holm–Bonferroni correction.
          </motion.p>
        </div>

        {/* 3-column card grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {AXES.map((axis, i) => (
            <AxisCard key={axis.id} axis={axis} index={i} />
          ))}
        </div>

        {/* Bottom bar */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4 }}
          className="mt-10 glass rounded-xl px-6 py-4 flex flex-wrap items-center justify-between gap-4"
          style={{ border: '1px solid rgba(255,215,0,0.15)' }}
        >
          <div className="flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-[#ffd700] animate-blink" />
            <span className="font-mono text-xs text-gray-400">
              <span className="font-bold" style={{ color: '#ffd700' }}>840 total trials</span>
              {' · '}all results reproducible from{' '}
              <span className="text-gray-600">evaluation_artifacts/</span>
            </span>
          </div>
          <div className="flex gap-4 flex-wrap">
            {['NIST SP 800-61', 'Wilson CIs', 'Bootstrap (Efron 1979)', 'Holm–Bonferroni'].map((m) => (
              <span key={m} className="font-mono text-[9px] text-gray-700 tracking-wider">
                {m}
              </span>
            ))}
          </div>
        </motion.div>

      </div>
    </section>
  );
}
