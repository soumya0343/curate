import { useState } from "react";

const EXAMPLES = [
  { label: "Trek to Hampta Pass", query: "I am going for a trek to Hampta Pass in the last week of October for one week. Please find me trekking essentials and clothing." },
  { label: "Wedding in March", query: "Find me good traditional wear for my friend's wedding in March next year." },
  { label: "25th Anniversary gift", query: "I need a premium gifting hamper for my parents' 25th anniversary next month." },
];

export function InputPanel({
  onSubmit, busy,
}: { onSubmit: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div className="w-full">
      <form
        onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}
        className="relative"
      >
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          placeholder="Tell me what you need — occasion, destination, budget, anything…"
          className="w-full resize-none rounded-xl border border-primary/15 bg-white px-5 py-4 pr-28 text-sm text-primary placeholder:text-primary/35 shadow-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/10 transition"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="absolute bottom-3 right-3 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-surface transition hover:bg-primary/80 disabled:opacity-30"
        >
          {busy ? "Thinking…" : "Find"}
        </button>
      </form>

      <div className="mt-4 flex flex-wrap gap-2">
        <span className="self-center text-xs text-primary/35 mr-1">Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            onClick={() => { setValue(ex.query); onSubmit(ex.query); }}
            disabled={busy}
            className="rounded-full border border-primary/15 bg-white px-3 py-1.5 text-xs text-primary/60 transition hover:border-gold-300 hover:text-primary disabled:opacity-40"
          >
            {ex.label}
          </button>
        ))}
      </div>
    </div>
  );
}
