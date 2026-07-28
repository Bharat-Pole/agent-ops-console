// Section 6.4 — deterministic seeded PRNG. ALL randomness (latencies, telemetry
// curves, eval jitter, healthcheck flips) flows from a mulberry32 seeded with a
// fixed constant so two demo runs look identical. "Reset demo" restores the seed.
//
// Note (acceptance #10): we never call Math.random() or Date.now() for anything
// that affects rendered output — a fixed DEMO_TODAY drives all date math.

export const FIXED_SEED = 0x9e3779b9; // golden-ratio constant, fixed

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// A small stateful RNG wrapper with helpers, seeded deterministically.
export class Rng {
  private next: () => number;

  constructor(seed: number = FIXED_SEED) {
    this.next = mulberry32(seed);
  }

  float(): number {
    return this.next();
  }

  // inclusive-exclusive integer in [min, max)
  int(min: number, max: number): number {
    return Math.floor(min + this.next() * (max - min));
  }

  // inclusive float in [min, max]
  range(min: number, max: number): number {
    return min + this.next() * (max - min);
  }

  bool(pTrue: number): boolean {
    return this.next() < pTrue;
  }

  pick<T>(arr: T[]): T {
    return arr[Math.floor(this.next() * arr.length)];
  }
}

// A dedicated RNG for latency simulation, re-seedable on reset.
let latencyRng = new Rng(FIXED_SEED ^ 0x1234);

export function resetLatencyRng(): void {
  latencyRng = new Rng(FIXED_SEED ^ 0x1234);
}

// Seeded latency in [minMs, maxMs] (Section 6.3).
export function latency(minMs: number, maxMs: number): number {
  return Math.round(latencyRng.range(minMs, maxMs));
}
