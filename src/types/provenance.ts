// Section 5.1 — Provenance envelope (on EVERY leaf field).
// The store keeps every schema leaf wrapped in Prov<T>. UI reads `.value`;
// ProvenanceChip reads the whole envelope.

export type ValueSource = 'user' | 'system' | 'default' | 'inherited' | 'inferred';
export type Confidence = 'high' | 'medium' | 'low';

export interface Prov<T> {
  value: T;
  value_source: ValueSource;
  verified_flag: boolean;
  confidence: Confidence;
  gap_note: string | null;
}

// ProvenanceChip letter codes: the five-letter legend from Section 3.3 is
// U user · S system · D default · I inferred · G generated, where "generated" is
// an engine-inferred value at low confidence. The enum also has a sixth source,
// "inherited" (from a tier template), which the chip shows as H. All five legend
// codes plus H are reachable from value_source + confidence (see ProvenanceChip).
export const VALUE_SOURCE_CODE: Record<ValueSource, string> = {
  user: 'U',
  system: 'S',
  default: 'D',
  inherited: 'H',
  inferred: 'I',
};

export const VALUE_SOURCE_LABEL: Record<ValueSource, string> = {
  user: 'User-provided',
  system: 'System',
  default: 'Default',
  inherited: 'Inherited',
  inferred: 'Engine-inferred',
};

// Helper to build a provenance envelope tersely in seed data / engine output.
export function prov<T>(
  value: T,
  value_source: ValueSource = 'default',
  opts: Partial<Omit<Prov<T>, 'value' | 'value_source'>> = {},
): Prov<T> {
  const defaultConfidence: Confidence =
    value_source === 'user' || value_source === 'system' || value_source === 'default'
      ? 'high'
      : 'medium';
  return {
    value,
    value_source,
    verified_flag: opts.verified_flag ?? (value_source === 'user' || value_source === 'system'),
    confidence: opts.confidence ?? defaultConfidence,
    gap_note: opts.gap_note ?? null,
  };
}
