// src/lib/busyCursor.ts
type Listener = () => void;

let manualCount = 0;
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((fn) => fn());
}

export const BusyCursor = {
  start() {
    manualCount++;
    notify();
    return () => BusyCursor.stop();
  },
  stop() {
    if (manualCount > 0) {
      manualCount--;
      notify();
    }
  },
  get count() {
    return manualCount;
  },
  // 👇 Ensure the return type is a cleanup that returns void
  subscribe(fn: Listener): () => void {
    listeners.add(fn);
    // DON'T: return () => listeners.delete(fn); // returns boolean ❌
    return () => { listeners.delete(fn); };    // swallow the boolean ✅
  },
};
