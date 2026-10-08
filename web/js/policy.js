// Pure decisions of the web app, kept free of the DOM so they can be tested with Node.

// After this many failed frames in a row, live view gives up.
export const MAX_FRAME_FAILURES = 5;

// What the live view loop does after its `failures`-th consecutive failed frame:
// the delay in milliseconds before the next request, or null to stop.
// 409 means the camera refuses live view (dial, missing card): retrying cannot help.
// Anything else (busy right after a shot, a dropped request) is retried with backoff.
export function afterFrameError(status, failures) {
  if (status === 409 || failures >= MAX_FRAME_FAILURES) return null;
  return Math.min(2000, 250 * 2 ** (failures - 1));
}
