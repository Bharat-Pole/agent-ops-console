/**
 * Tool schema viewer — pure rendering logic.
 *
 * The viewer is deliberately partial, so what matters most is that it is
 * HONEST about the limit: anything it cannot model must fall back to raw JSON
 * rather than produce a confident, wrong summary.
 */
import assert from 'node:assert';
import {
  describeType, flattenSchema, isRenderableSchema,
} from '../src/modules/assets/schemaView';

let passed = 0;
function test(name: string, fn: () => void) {
  fn();
  passed += 1;
  console.log(`  ok   ${name}`);
}

console.log('== Tool schema viewer ==');

test('flattens a normal object schema with types and descriptions', () => {
  const fields = flattenSchema({
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Search text' },
      limit: { type: 'integer', default: 10 },
    },
    required: ['query'],
  });
  assert.equal(fields.length, 2);
  assert.equal(fields[0].path, 'query');
  assert.equal(fields[0].type, 'string');
  assert.equal(fields[0].required, true);
  assert.equal(fields[0].description, 'Search text');
  assert.equal(fields[1].required, false);
  assert.equal(fields[1].defaultValue, 10);
});

test('surfaces enum values', () => {
  const [field] = flattenSchema({
    type: 'object',
    properties: { severity: { type: 'string', enum: ['P1', 'P2', 'P3'] } },
  });
  assert.deepEqual(field.enumValues, ['P1', 'P2', 'P3']);
});

test('describes arrays by item type', () => {
  assert.equal(describeType({ type: 'array', items: { type: 'string' } }), 'array<string>');
  assert.equal(describeType({ type: 'array' }), 'array');
});

test('handles a nullable union type', () => {
  assert.equal(describeType({ type: ['string', 'null'] }), 'string | null');
});

test('recurses into nested objects without crashing', () => {
  const fields = flattenSchema({
    type: 'object',
    properties: {
      filters: {
        type: 'object',
        properties: { status: { type: 'string' } },
        required: ['status'],
      },
    },
  });
  const paths = fields.map((f) => f.path);
  assert.ok(paths.includes('filters'));
  assert.ok(paths.includes('filters.status'), 'nested field should be flattened');
  assert.equal(fields.find((f) => f.path === 'filters.status')?.required, true);
});

test('recurses into arrays of objects', () => {
  const paths = flattenSchema({
    type: 'object',
    properties: {
      rows: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' } } } },
    },
  }).map((f) => f.path);
  assert.ok(paths.includes('rows[].id'));
});

test('stops recursing at the depth limit', () => {
  const deep = {
    type: 'object',
    properties: {
      a: { type: 'object', properties: {
        b: { type: 'object', properties: {
          c: { type: 'object', properties: {
            d: { type: 'string' } } } } } } },
    },
  };
  const paths = flattenSchema(deep, 2).map((f) => f.path);
  assert.ok(paths.includes('a.b'));
  assert.ok(!paths.some((p) => p.startsWith('a.b.c.d')), 'must not expand past maxDepth');
});

test('empty schema is renderable and yields no fields', () => {
  assert.equal(isRenderableSchema({}), true);
  assert.deepEqual(flattenSchema({}), []);
});

test('schema with no properties is not renderable', () => {
  assert.equal(isRenderableSchema({ type: 'object' }), false);
});

test('unsupported constructs fall back to raw rather than guessing', () => {
  assert.equal(isRenderableSchema({ $ref: '#/definitions/Thing' }), false);
  assert.equal(isRenderableSchema({ oneOf: [{ type: 'string' }] }), false);
  assert.equal(isRenderableSchema({
    type: 'object',
    properties: { x: { anyOf: [{ type: 'string' }, { type: 'number' }] } },
  }), false, 'an unsupported construct inside a property must also fall back');
});

test('malformed input never throws', () => {
  assert.deepEqual(flattenSchema(null), []);
  assert.deepEqual(flattenSchema('not a schema'), []);
  assert.deepEqual(flattenSchema({ properties: 'nonsense' }), []);
  assert.deepEqual(flattenSchema({ properties: { a: 'not-an-object' } })[0], {
    path: 'a', type: 'unspecified', required: false,
    description: undefined, enumValues: undefined, defaultValue: undefined,
  });
  assert.equal(isRenderableSchema(null), false);
  assert.equal(isRenderableSchema([]), false);
});

console.log(`\nALL SCHEMA VIEWER TESTS PASSED (${passed})`);
