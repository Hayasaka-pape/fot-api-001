export const MIN_POLL_SECONDS = 30;

export function pollDelayMs(value) {
  const seconds = Number(value);
  return Math.max(MIN_POLL_SECONDS, Number.isFinite(seconds) && seconds > 0 ? seconds : MIN_POLL_SECONDS) * 1000;
}

export function startPolling({ load, onResult, onError, intervalSeconds = MIN_POLL_SECONDS, shouldPoll = () => true, immediate = true, clock = globalThis }) {
  let stopped = false, timer;
  const controller = new AbortController();
  const schedule = () => { timer = clock.setTimeout(poll, pollDelayMs(typeof intervalSeconds === 'function' ? intervalSeconds() : intervalSeconds)); };
  async function poll() {
    if (stopped) return;
    try {
      if (shouldPoll()) {
        const value = await load(controller.signal);
        if (!stopped) onResult?.(value);
      }
    } catch (failure) {
      if (!stopped && failure.name !== 'AbortError') onError?.(failure);
    } finally {
      // Completion-based scheduling avoids overlapping requests when upstream takes longer than the interval.
      if (!stopped) schedule();
    }
  }
  if (immediate) poll(); else schedule();
  return () => { stopped = true; clock.clearTimeout(timer); controller.abort(); };
}
