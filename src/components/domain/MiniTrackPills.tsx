import type { AgentRecord, TrackStatus } from '@/types';
import { Tooltip } from '@/components/primitives/Tooltip';
import { cn } from '@/utils/cn';

// Three compact R/R/C track dots for the registry list (Section 9.2).
const DOT: Record<TrackStatus, string> = {
  ready: 'bg-ok',
  in_progress: 'bg-warn animate-pulse-dot',
  blocked: 'bg-err',
  not_started: 'bg-border-strong',
};

const TRACKS = [
  { key: 'registry', letter: 'R', name: 'Registry' },
  { key: 'runtime', letter: 'R', name: 'Runtime' },
  { key: 'content', letter: 'C', name: 'Content' },
] as const;

export function MiniTrackPills({ agent }: { agent: AgentRecord }) {
  return (
    <span className="inline-flex items-center gap-1">
      {TRACKS.map((t, i) => {
        const st = agent.tracks[t.key].status;
        return (
          <Tooltip key={i} content={`${t.name}: ${st.replace('_', ' ')}`}>
            <span className="inline-flex items-center gap-0.5">
              <span className={cn('inline-block h-2 w-2 rounded-full', DOT[st])} />
              <span className="text-[9px] text-text-low">{t.letter}</span>
            </span>
          </Tooltip>
        );
      })}
    </span>
  );
}
