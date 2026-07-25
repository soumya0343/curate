import { useState } from "react";
import type { Assumption } from "../types";

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
    <div className="mb-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
      {assumptions.length > 0 && (
        <>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            What I assumed
          </p>
          <ul className="flex flex-wrap gap-2">
            {assumptions.map((a) => (
              <li
                key={`${a.field}-${a.value}`}
                title={a.reason}
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-700"
              >
                {a.value}
                <span className="ml-1.5 text-slate-400">{a.confidence}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {question && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <p className="text-sm text-slate-700">{question}</p>
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
              className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded bg-slate-900 px-3 py-1 text-sm text-white"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
