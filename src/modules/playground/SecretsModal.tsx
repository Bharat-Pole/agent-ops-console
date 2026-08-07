import { KeyRound } from 'lucide-react';
import { Modal, Button } from '@/components/primitives';
import { SecretsInner } from '@/modules/secrets/SecretsInner';

// Thin modal wrapper around the shared vault manager, used from the Playground.
export function SecretsModal({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged?: (names: string[]) => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={<span className="flex items-center gap-2"><KeyRound size={15} /> Secrets vault (engine-side)</span>}
      width="max-w-lg"
      footer={<Button variant="ghost" onClick={onClose}>Close</Button>}
    >
      {open && <SecretsInner onChanged={onChanged} />}
    </Modal>
  );
}
