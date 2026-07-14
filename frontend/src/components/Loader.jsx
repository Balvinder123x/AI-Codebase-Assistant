/**
 * Loader
 * ======
 * A spinner with a message. Used while indexing (slow) and while waiting
 * for an answer (also slow).
 *
 * UX note: never show a bare spinner. Tell the user WHAT is happening.
 * Indexing takes up to two minutes; a silent spinner for two minutes feels
 * like a crash.
 */
export default function Loader({ message = "Loading..." }) {
  return (
    <div className="flex items-center gap-3 text-slate-400">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400" />
      <span className="text-sm">{message}</span>
    </div>
  );
}
