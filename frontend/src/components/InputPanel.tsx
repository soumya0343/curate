import { useState } from "react";

const EXAMPLES = [
  "I am going for a trek to Hampta Pass in the last week of October for one week. Please find me trekking essentials and clothing.",
  "Find me good traditional wear for my friend's wedding in March next year.",
  "I need a premium gifting hamper for my parents' 25th anniversary next month.",
];

export function InputPanel({
  onSubmit, busy,
}: { onSubmit: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div>
      <form
        onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}
      >
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          placeholder="Describe what you're shopping for…"
          className="w-full resize-none rounded-lg border border-slate-300 p-3 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Thinking…" : "Find products"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            onClick={() => { setValue(example); onSubmit(example); }}
            disabled={busy}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-slate-500 disabled:opacity-40"
          >
            {example.slice(0, 42)}…
          </button>
        ))}
      </div>
    </div>
  );
}
