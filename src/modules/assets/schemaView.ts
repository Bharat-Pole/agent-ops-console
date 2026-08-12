/**
 * Minimal JSON Schema flattener for the read-only tool contract viewer.
 *
 * Deliberately NOT a JSON Schema implementation. It understands the shapes
 * tools actually declare — objects with typed properties, enums, defaults,
 * arrays, one level of nesting — and refuses to guess at anything else.
 * Constructs it does not understand ($ref, oneOf/anyOf/allOf) make the whole
 * schema "unrenderable" so the UI shows raw JSON instead of a confident but
 * wrong summary.
 */

export interface SchemaField {
  /** Dotted path, e.g. "filters.status". */
  path: string;
  type: string;
  required: boolean;
  description?: string;
  enumValues?: string[];
  defaultValue?: unknown;
}

const UNSUPPORTED_KEYS = ['$ref', 'oneOf', 'anyOf', 'allOf', 'not'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Human-readable type, tolerating `type` given as an array (nullable unions). */
export function describeType(node: Record<string, unknown>): string {
  const raw = node.type;
  let base: string;
  if (typeof raw === 'string') base = raw;
  else if (Array.isArray(raw) && raw.every((t) => typeof t === 'string')) base = raw.join(' | ');
  else base = 'unspecified';

  if (base === 'array') {
    const items = node.items;
    if (isRecord(items)) return `array<${describeType(items)}>`;
    return 'array';
  }
  return base;
}

/**
 * True when the structured view can be trusted. An empty schema is renderable
 * (it renders as "no fields declared"); an unsupported construct is not.
 */
export function isRenderableSchema(schema: unknown): boolean {
  if (!isRecord(schema)) return false;
  if (Object.keys(schema).length === 0) return true;
  if (UNSUPPORTED_KEYS.some((k) => k in schema)) return false;
  const properties = schema.properties;
  if (properties === undefined) return false;      // nothing to structure
  if (!isRecord(properties)) return false;
  return !Object.values(properties).some(
    (p) => isRecord(p) && UNSUPPORTED_KEYS.some((k) => k in p),
  );
}

/**
 * Flatten `properties` into a display list. Nested objects recurse up to
 * `maxDepth` and then stop rather than expanding indefinitely.
 */
export function flattenSchema(schema: unknown, maxDepth = 3): SchemaField[] {
  if (!isRecord(schema)) return [];

  const walk = (node: Record<string, unknown>, prefix: string, depth: number): SchemaField[] => {
    const properties = node.properties;
    if (!isRecord(properties)) return [];
    const requiredList = Array.isArray(node.required)
      ? node.required.filter((r): r is string => typeof r === 'string')
      : [];

    const out: SchemaField[] = [];
    for (const [name, rawField] of Object.entries(properties)) {
      const field = isRecord(rawField) ? rawField : {};
      const path = prefix ? `${prefix}.${name}` : name;
      const type = describeType(field);

      out.push({
        path,
        type,
        required: requiredList.includes(name),
        description: typeof field.description === 'string' ? field.description : undefined,
        enumValues: Array.isArray(field.enum) ? field.enum.map((v) => String(v)) : undefined,
        defaultValue: 'default' in field ? field.default : undefined,
      });

      // one level down for nested objects, and for arrays of objects
      if (depth < maxDepth) {
        if (type === 'object' && isRecord(field.properties)) {
          out.push(...walk(field, path, depth + 1));
        } else if (type.startsWith('array<') && isRecord(field.items)
                   && isRecord((field.items as Record<string, unknown>).properties)) {
          out.push(...walk(field.items as Record<string, unknown>, `${path}[]`, depth + 1));
        }
      }
    }
    return out;
  };

  try {
    return walk(schema, '', 0);
  } catch {
    return [];   // never let a malformed contract break the page
  }
}
