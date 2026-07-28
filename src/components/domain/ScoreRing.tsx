import { DEEP_EVAL_PASS_SCORE } from '@/kernel/constants';

// Circular score ring (0–100). Colored by the Deep-path pass threshold.
export function ScoreRing({ score, size = 84 }: { score: number; size?: number }) {
  const r = size / 2 - 7;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = score >= DEEP_EVAL_PASS_SCORE ? 'var(--ok)' : score >= 75 ? 'var(--warn)' : 'var(--err)';
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={7} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={7}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-[18px] font-semibold text-text-hi">{Math.round(score)}</span>
        <span className="text-[9px] text-text-low">/ 100</span>
      </div>
    </div>
  );
}
