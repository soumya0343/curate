import { useState } from "react";

const QUICK = ["Make it cheaper", "More premium", "Show more options"];

export function RefineBar({
  onRefine, busy,
}: { onRefine: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div className="sticky bottom-0 mt-8 border-t border-slate-200 bg-white/95 py-3 backdrop-blur">
      <div className="mb-2 flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button
            key={q}
            onClick={() => onRefine(q)}
            disabled={busy}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-slate-500 disabled:opacity-40"
          >
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) { onRefine(value.trim()); setValue(""); }
        }}
      >
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Refine these results…"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          Refine
        </button>
      </form>
    </div>
  );
}
