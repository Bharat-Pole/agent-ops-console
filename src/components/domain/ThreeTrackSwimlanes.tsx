import type { AgentRecord, Track } from '@/types';
import { isLive } from '@/types';
import { StatusPill } from '@/components/primitives/StatusPill';
import { fmtDateTime } from '@/utils/format';
import { CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn } from '@/utils/cn';

// Section 3.3 / 1.2 #2 — three tracks; agent is LIVE iff all three are ready.
const TRACK_META = [
  { key: 'registry', label: 'REGISTRY', blurb: 'describes / governs' },
  { key: 'runtime', label: 'RUNTIME', blurb: 'executes' },
  { key: 'content', label: 'CONTENT', blurb: 'feeds' },
] as const;

function TrackCard({ label, blurb, track, compact }: { label: string; blurb: string; track: Track; compact: boolean }) {
  return (
    <div className="flex-1 rounded-card border border-border bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-[11px] font-semibold tracking-wide text-text-hi">{label}</div>
          <div className="text-[10px] text-text-low">{blurb}</div>
        </div>
        <StatusPill status={track.status} />
      </div>
      {!compact && (
        <ul className="space-y-1">
          {track.steps.map((s, i) => (
            <li key={i} className="flex items-center justify-between gap-2 text-[12px]">
              <span className="flex items-center gap-1.5">
                <StatusPill status={s.status} label="" size="xs" />
                <span className={cn(s.status === 'ready' ? 'text-text-mid' : 'text-text-hi')}>{s.name}</span>
              </span>
              {s.at && <span className="mono text-[10px] text-text-low">{fmtDateTime(s.at)}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ThreeTrackSwimlanes({ agent, compact = false }: { agent: AgentRecord; compact?: boolean }) {
  const live = isLive(agent);
  const waiting = TRACK_META.filter((t) => agent.tracks[t.key].status !== 'ready').map((t) => t.label.toLowerCase());

  return (
    <div>
      <div
        className={cn(
          'mb-2 flex items-center gap-2 rounded-card border px-3 py-2 text-[13px] font-semibold',
          live ? 'border-ok/40 bg-ok/10 text-ok' : 'border-warn/40 bg-warn/10 text-warn',
        )}
      >
        {live ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        {live ? (
          <span>Agent Status: LIVE</span>
        ) : (
          <span>
            NOT LIVE <span className="font-normal opacity-90">(waiting on: {waiting.join(', ')})</span>
          </span>
        )}
      </div>
      <div className="flex gap-2">
        {TRACK_META.map((t) => (
          <TrackCard key={t.key} label={t.label} blurb={t.blurb} track={agent.tracks[t.key]} compact={compact} />
        ))}
      </div>
    </div>
  );
}
