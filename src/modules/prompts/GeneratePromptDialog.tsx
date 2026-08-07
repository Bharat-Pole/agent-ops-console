import { useState } from 'react';
import { Modal, Button } from '@/components/primitives';
import { api } from '@/kernel/api';
import type { PromptCategory, PromptKind } from '@/types';
import { Sparkles, Loader2, RotateCcw } from 'lucide-react';

const inputCls = 'w-full rounded-control border border-border bg-canvas px-2.5 py-2 text-[13px] text-text-hi placeholder:text-text-low focus-ring';

// Two-step "Generate with AI" flow for creating a brand-new prompt asset:
// 1. Instruction — user optionally describes what the prompt should say.
// 2. Review — AI's drafted name + body, editable, before anything is saved.
// Nothing is persisted to the Prompt Repository until Accept is clicked.
export function GeneratePromptDialog({
  open,
  onClose,
  kind,
  category,
  baseContext,
  onAccept,
}: {
  open: boolean;
  onClose: () => void;
  kind: PromptKind;
  category: PromptCategory;
  baseContext: Record<string, unknown>;
  onAccept: (result: { name: string; body: string }) => void;
}) {
  const [step, setStep] = useState<'instruction' | 'review'>('instruction');
  const [instruction, setInstruction] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [body, setBody] = useState('');

  const reset = () => { setStep('instruction'); setInstruction(''); setName(''); setBody(''); };
  const close = () => { reset(); onClose(); };

  const generate = async () => {
    setBusy(true);
    const result = await api.generatePromptBody({ kind, category, context: { ...baseContext, user_instruction: instruction } });
    setBusy(false);
    if (!result) return;
    setName(result.name);
    setBody(result.body);
    setStep('review');
  };

  const accept = () => {
    onAccept({ name, body });
    close();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={step === 'instruction' ? 'Generate prompt with AI' : 'Review AI-drafted prompt'}
      footer={
        step === 'instruction' ? (
          <>
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button variant="primary" icon={busy ? <Loader2 size={14} className="animate-spin-slow" /> : <Sparkles size={14} />} disabled={busy} onClick={generate}>
              {busy ? 'Generating…' : 'Generate'}
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={close}>Discard</Button>
            <Button variant="subtle" icon={busy ? <Loader2 size={14} className="animate-spin-slow" /> : <RotateCcw size={13} />} disabled={busy} onClick={generate}>Regenerate</Button>
            <Button variant="primary" onClick={accept}>Accept</Button>
          </>
        )
      }
    >
      {step === 'instruction' ? (
        <div>
          <div className="mb-1 text-[12px] font-medium text-text-mid">What should this prompt say? (optional)</div>
          <textarea
            className={inputCls}
            rows={5}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Describe what you want, e.g. “Always cite the incident ID and never speculate about root cause.” Leave blank to let AI draft it from the agent's objective."
          />
          <div className="mt-2 text-[11px] text-text-low">The AI will rephrase your instruction into a governed prompt, using the agent's objective and context either way.</div>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Name</div>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-text-mid">Body</div>
            <textarea className={`${inputCls} mono`} rows={9} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
        </div>
      )}
    </Modal>
  );
}
