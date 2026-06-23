import { useMemo } from 'react';

/**
 * Clean SVG-based Line and Area Chart for trend visualization.
 */
export function LineChart({ data = [], stroke = '#2563eb', fill = 'rgba(37, 99, 235, 0.08)', height = 120, minVal = null, maxVal = null }) {
  const points = useMemo(() => {
    if (data.length === 0) return [];
    
    // Normalize data points
    const values = data.map(d => typeof d === 'object' ? d.value : d);
    const min = minVal !== null ? minVal : Math.min(0, ...values);
    const max = maxVal !== null ? Math.max(1, maxVal) : Math.max(1, ...values);
    const range = max - min;
    
    const w = 400; // SVG internal coordinate system width
    const h = 100; // SVG internal coordinate system height
    
    return values.map((val, idx) => {
      const x = data.length > 1 ? (idx / (data.length - 1)) * w : w / 2;
      const y = range > 0 ? h - ((val - min) / range) * h : h / 2;
      return { x, y, value: val };
    });
  }, [data, minVal, maxVal]);

  const pathD = useMemo(() => {
    if (points.length === 0) return '';
    return points.reduce((acc, p, idx) => {
      return idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
    }, '');
  }, [points]);

  const areaD = useMemo(() => {
    if (points.length === 0) return '';
    return `${pathD} L ${points[points.length - 1].x} 100 L ${points[0].x} 100 Z`;
  }, [points, pathD]);

  // Labels for rendering
  const maxLabel = useMemo(() => {
    if (data.length === 0) return '0';
    const values = data.map(d => typeof d === 'object' ? d.value : d);
    return Math.max(...values).toFixed(0);
  }, [data]);

  return (
    <div style={{ width: '100%', height: `${height}px`, position: 'relative' }}>
      <svg viewBox="0 0 400 100" preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
        {/* Horizontal grid lines */}
        <line x1="0" y1="25" x2="400" y2="25" stroke="#f1f3f5" strokeWidth="1" strokeDasharray="3,3" />
        <line x1="0" y1="50" x2="400" y2="50" stroke="#f1f3f5" strokeWidth="1" strokeDasharray="3,3" />
        <line x1="0" y1="75" x2="400" y2="75" stroke="#f1f3f5" strokeWidth="1" strokeDasharray="3,3" />
        
        {/* Area fill under curve */}
        {points.length > 0 && <path d={areaD} fill={fill} />}
        
        {/* Trend line */}
        {points.length > 0 && <path d={pathD} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />}
      </svg>
      {/* Absolute overlay labels to avoid rendering small SVG texts */}
      <div style={{ position: 'absolute', top: 0, left: 4, fontSize: '0.625rem', color: '#94a3b8', pointerEvents: 'none' }}>{maxLabel}</div>
      <div style={{ position: 'absolute', bottom: 0, left: 4, fontSize: '0.625rem', color: '#94a3b8', pointerEvents: 'none' }}>0</div>
    </div>
  );
}

/**
 * Clean SVG Bar Chart with rounded rects for distributions.
 */
export function BarChart({ data = [], color = '#2563eb', height = 120 }) {
  const max = useMemo(() => {
    if (data.length === 0) return 1;
    return Math.max(1, ...data.map(d => d.value));
  }, [data]);

  return (
    <div style={{ width: '100%', height: `${height}px`, display: 'flex', flexDirection: 'column', padding: '0.5rem 0.25rem 0' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: '8px', borderBottom: '1px solid #e2e8f0', paddingBottom: '2px' }}>
        {data.map((bar, idx) => {
          const pct = (bar.value / max) * 100;
          return (
            <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end', position: 'relative' }} title={`${bar.label}: ${bar.value}`}>
              {/* Tooltip or hover label */}
              {bar.value > 0 && (
                <span style={{ fontSize: '0.625rem', fontWeight: 'bold', color: '#475569', marginBottom: '2px' }}>
                  {bar.value.toFixed(0)}
                </span>
              )}
              {/* Rect bar using div with border-radius */}
              <div style={{
                width: '100%',
                maxWidth: '24px',
                height: `${pct}%`,
                background: color,
                borderRadius: '3px 3px 0 0',
                transition: 'height 0.3s ease-in-out'
              }} />
            </div>
          );
        })}
      </div>
      {/* Horizontal labels */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
        {data.map((bar, idx) => (
          <div key={idx} style={{ flex: 1, fontSize: '0.625rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.2px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', textAlign: 'center' }}>
            {bar.label}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Apple-watch style progress circle showing negotiation success or safety percentages.
 */
export function ProgressRing({ percentage = 100, size = 110, strokeWidth = 10, color = '#2563eb', label = 'Success' }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, percentage)) / 100) * circumference;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
      <div style={{ width: size, height: size, position: 'relative' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          {/* Background circle track */}
          <circle
            r={radius}
            cx={size / 2}
            cy={size / 2}
            fill="transparent"
            stroke="#f1f3f9"
            strokeWidth={strokeWidth}
          />
          {/* Progress circle arc */}
          <circle
            r={radius}
            cx={size / 2}
            cy={size / 2}
            fill="transparent"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.4s ease-in-out' }}
          />
        </svg>
        {/* Percent readout centered inside circle */}
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center'
        }}>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#1e293b' }}>
            {percentage.toFixed(0)}%
          </span>
        </div>
      </div>
      <span style={{ fontSize: '0.72rem', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {label}
      </span>
    </div>
  );
}
