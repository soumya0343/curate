import { useState } from "react";

const QUICK = ["Make it cheaper", "More premium", "Show more options"];

export function RefineBar({
  onRefine, busy,
}: { onRefine: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button
            key={q}
            onClick={() => onRefine(q)}
            disabled={busy}
            className="rounded-full border border-primary/15 bg-white px-3 py-1.5 text-xs text-primary/60 transition hover:border-gold-300 hover:text-primary disabled:opacity-40"
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
          className="flex-1 rounded-xl border border-primary/15 bg-white px-4 py-2.5 text-sm text-primary placeholder:text-primary/35 focus:outline-none focus:ring-2 focus:ring-primary/10"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-surface transition hover:bg-primary/80 disabled:opacity-30"
        >
          Refine
        </button>
      </form>
    </div>
  );
}
