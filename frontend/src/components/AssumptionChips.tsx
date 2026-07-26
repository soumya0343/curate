import { useState } from "react";
import type { Assumption } from "../types";

const VERIFIED_FIELDS = new Set(["budget", "price", "min_price", "max_price"]);

export function AssumptionChips({
  assumptions, question, onAnswer,
}: {
  assumptions: Assumption[];
  question: string | null;
  onAnswer: (answer: string) => void;
}) {
  const [answer, setAnswer] = useState("");
  if (assumptions.length === 0 && !question) return null;

  return (
    <div className="mb-6 rounded-xl border border-gold-200 bg-gold-50 p-4">
      {assumptions.length > 0 && (
        <>
          <p className="mb-3 text-xs font-medium uppercase tracking-widest text-gold-500">
            What I understood
          </p>
          <ul className="flex flex-wrap gap-2">
            {assumptions.map((a) => (
              <li
                key={`${a.field}-${a.value}`}
                title={a.reason}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                  VERIFIED_FIELDS.has(a.field)
                    ? "border-gold-300 bg-white text-primary"
                    : "border-gold-200 bg-gold-50 text-primary/70"
                }`}
              >
                {a.value}
                <span className={`text-[10px] font-medium ${
                  VERIFIED_FIELDS.has(a.field) ? "text-gold-500" : "text-primary/35"
                }`}>
                  {VERIFIED_FIELDS.has(a.field) ? "✓" : a.confidence}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {question && (
        <div className="mt-4 border-t border-gold-200 pt-3">
          <p className="text-sm text-primary/80">{question}</p>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (answer.trim()) { onAnswer(answer.trim()); setAnswer(""); }
            }}
          >
            <input
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Your answer…"
              className="flex-1 rounded-lg border border-gold-200 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gold-300"
            />
            <button
              type="submit"
              className="rounded-lg bg-primary px-3 py-1.5 text-sm text-surface"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
