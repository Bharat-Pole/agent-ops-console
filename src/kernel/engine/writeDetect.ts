// Stage 3b — Write-action detection (Section 7.4), the advisory-only guardrail.
// Ensemble simulated as two passes: (1) keyword list, (2) a context
// disambiguator distinguishing advisory phrasings ("draft an email" → advisory)
// from write phrasings ("send an email" → write). Any suspected write: the tool
// is FLAGGED, never bound. risk_tier floor rises to `high` when write intent is
// detected.

import type { Intent, WriteDetection } from './types';

// (1) keyword list — write verbs paired with an object noun.
const WRITE_VERBS = [
  'send', 'approve', 'deploy', 'update', 'create', 'delete', 'close', 'assign',
  'notify', 'post', 'execute', 'modify', 'file', 'submit', 'remove', 'email',
];

// Tool-name fragments that imply a write capability.
const WRITE_TOOL_FRAGMENTS = ['notifier', 'sender', 'updater', 'writer', 'poster', 'creator', 'deleter', 'approver', 'deployer'];

// (2) advisory disambiguator — these framings neutralize a nearby write verb.
const ADVISORY_FRAMES = ['draft', 'recommend', 'suggest', 'propose', 'summarize', 'summarise', 'prepare a draft', 'review'];

const OBJECT_NOUNS = ['email', 'message', 'ticket', 'record', 'notification', 'notifications', 'comms', 'update', 'filing', 'report', 'slack', 'alert', 'account'];

export function detectWriteActions(intent: Intent): WriteDetection {
  const text = (intent.objective || '').toLowerCase();
  const tools = intent.tools ?? [];

  // Pass 1 — flag tools whose names imply write capability.
  const flagged = tools.filter((t) => {
    const name = t.toLowerCase();
    return WRITE_TOOL_FRAGMENTS.some((f) => name.includes(f)) || WRITE_VERBS.some((v) => name.includes(v));
  });

  // Pass 2 — write intent in the objective, disambiguated by advisory framing.
  const write_intents: WriteDetection['write_intents'] = [];
  for (const verb of WRITE_VERBS) {
    const re = new RegExp(`\\b${verb}\\w*\\b`);
    const m = re.exec(text);
    if (!m) continue;
    const idx = m.index;
    const before = text.slice(Math.max(0, idx - 20), idx);
    const after = text.slice(idx, idx + 40);
    const advisory = ADVISORY_FRAMES.some((f) => before.includes(f));
    const hasObject = OBJECT_NOUNS.some((n) => after.includes(n));
    if (!advisory && hasObject) {
      write_intents.push({
        phrase: m[0],
        verb,
        note: `Write phrasing "${m[0]}" paired with an object noun — advisory-only enforced.`,
      });
    }
  }

  const anyWrite = flagged.length > 0 || write_intents.length > 0;
  return {
    flagged_tools: [...new Set(flagged)],
    write_intents,
    risk_floor: anyWrite ? 'high' : null,
  };
}
