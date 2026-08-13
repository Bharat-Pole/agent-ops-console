/**
 * Minimal line diff for comparing two prompt versions.
 *
 * Hand-rolled rather than pulling a diff package: the need is one read-only
 * review view, and a classic LCS over lines is ~30 lines with no dependency,
 * no bundle cost, and no supply-chain surface.
 */
export type DiffOp = 'same' | 'added' | 'removed';

export interface DiffLine {
  op: DiffOp;
  text: string;
  /** 1-based line number in the left/right document, when present there. */
  leftNo: number | null;
  rightNo: number | null;
}

/** Longest-common-subsequence line diff. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split('\n');
  const b = after.split('\n');

  // lengths[i][j] = LCS length of a[i..] and b[j..]
  const lengths: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lengths[i][j] = a[i] === b[j]
        ? lengths[i + 1][j + 1] + 1
        : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  let leftNo = 0;
  let rightNo = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ op: 'same', text: a[i], leftNo: ++leftNo, rightNo: ++rightNo });
      i++; j++;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      out.push({ op: 'removed', text: a[i], leftNo: ++leftNo, rightNo: null });
      i++;
    } else {
      out.push({ op: 'added', text: b[j], leftNo: null, rightNo: ++rightNo });
      j++;
    }
  }
  while (i < a.length) out.push({ op: 'removed', text: a[i++], leftNo: ++leftNo, rightNo: null });
  while (j < b.length) out.push({ op: 'added', text: b[j++], leftNo: null, rightNo: ++rightNo });
  return out;
}

export function diffStats(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.op === 'added').length,
    removed: lines.filter((l) => l.op === 'removed').length,
  };
}
