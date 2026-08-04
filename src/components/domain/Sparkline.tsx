import { LineChart, Line, ResponsiveContainer, YAxis, Tooltip as RTooltip } from 'recharts';

// Small sparkline for telemetry rows. Deterministic data in, static render out.
export function Sparkline({
  data,
  dataKey,
  color = 'var(--accent)',
  height = 34,
  label,
}: {
  data: Array<Record<string, number | string>>;
  dataKey: string;
  color?: string;
  height?: number;
  label?: string;
}) {
  return (
    <div style={{ height, width: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 3, bottom: 3, left: 0, right: 0 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <RTooltip
            cursor={{ stroke: 'var(--border-strong)' }}
            contentStyle={{
              background: 'var(--bg-raised)',
              border: '1px solid var(--border-strong)',
              borderRadius: 6,
              fontSize: 11,
              color: 'var(--text-hi)',
            }}
            labelFormatter={() => label ?? ''}
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
