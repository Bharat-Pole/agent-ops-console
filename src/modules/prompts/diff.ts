export type DiffLine = { type: 'same' | 'add' | 'del'; text: string };

// Classic LCS-based line diff — no external dependency, fine at prompt-body
// scale (tens of lines, not megabytes).
export function diffLines(a: string, b: string): DiffLine[] {
  const linesA = a.split('\n');
  const linesB = b.split('\n');
  const n = linesA.length;
  const m = linesB.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = linesA[i] === linesB[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (linesA[i] === linesB[j]) {
      result.push({ type: 'same', text: linesA[i] });
      i++; j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: 'del', text: linesA[i] });
      i++;
    } else {
      result.push({ type: 'add', text: linesB[j] });
      j++;
    }
  }
  while (i < n) { result.push({ type: 'del', text: linesA[i] }); i++; }
  while (j < m) { result.push({ type: 'add', text: linesB[j] }); j++; }
  return result;
}
