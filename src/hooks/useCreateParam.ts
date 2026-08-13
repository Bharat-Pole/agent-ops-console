import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * `?new=1` deep-link support for the left-nav "+ New" quick actions.
 *
 * Those actions used to point at dedicated wizard routes (/tools/new and
 * friends) that were removed when these pages became server-backed, so every
 * one of them 404'd. They now land on the real list page and open its create
 * modal, which keeps ONE creation path per asset type rather than reviving a
 * second one.
 *
 * The param is stripped once consumed, so closing the modal (or refreshing)
 * doesn't re-open it — and picking the same menu item again re-adds the param,
 * which re-fires this effect even though the page never unmounted.
 */
export function useCreateParam(open: (v: boolean) => void): void {
  const [params, setParams] = useSearchParams();
  const requested = params.get('new') === '1';

  useEffect(() => {
    if (!requested) return;
    open(true);
    const next = new URLSearchParams(params);
    next.delete('new');
    setParams(next, { replace: true });
    // `open` and `params` are intentionally not deps: this must run on the
    // false→true edge of the param only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested]);
}
