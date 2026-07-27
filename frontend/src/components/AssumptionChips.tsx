import { useState } from "react";
import type { Assumption } from "../types";

// Fields the customer stated outright rather than something the model guessed -
// shown with a checkmark instead of a confidence label, same as a verified
// product attribute (spec: assumptions are for judgement calls, not facts).
const VERIFIED_FIELDS = new Set([
  "budget", "price", "min_price", "max_price",
  "destination", "activity", "occasion", "gender", "duration",
]);

const INTENT_FIELD_LABELS: Record<string, (value: unknown) => string | null> = {
  destination: (v) => String(v),
  activity: (v) => String(v),
  occasion: (v) => String(v),
  gender: (v) => (v === "unisex" ? null : String(v)), // unisex already shown as an assumption when defaulted
  season: (v) => String(v),
  duration_days: (v) => `${v} day${Number(v) === 1 ? "" : "s"}`,
  budget_max: (v) => `Under ₹${Number(v).toLocaleString("en-IN")}`,
};

const INTENT_FIELD_NAMES: Record<string, string> = {
  duration_days: "duration", budget_max: "budget",
};

/** Stated facts (destination, budget, gender, ...) never show up in `assumptions` -
 * those are reserved for the model's inferred guesses. Build chips for the facts
 * too, so a customer sees confirmation of what they explicitly told the app. */
export function statedFactChips(
  intent: Record<string, unknown> | undefined,
  alreadyShown: Set<string>,
): Assumption[] {
  if (!intent) return [];
  const chips: Assumption[] = [];
  for (const [key, format] of Object.entries(INTENT_FIELD_LABELS)) {
    const raw = intent[key];
    if (raw === null || raw === undefined) continue;
    const field = INTENT_FIELD_NAMES[key] ?? key;
    if (alreadyShown.has(field)) continue;
    const value = format(raw);
    if (!value) continue;
    chips.push({ field, value, reason: "You told me this", confidence: "high", editable: false });
  }
  return chips;
}

export function AssumptionChips({
  assumptions, questions, onAnswer,
}: {
  assumptions: Assumption[];
  questions: string[];
  onAnswer: (answer: string) => void;
}) {
  const [answer, setAnswer] = useState("");
  if (assumptions.length === 0 && questions.length === 0) return null;

  return (
    <div className="mb-6 rounded-xl border border-gold-200 bg-gold-50 p-4">
      {assumptions.length > 0 && (
        <>
          <p className="mb-3 text-xs font-medium uppercase tracking-widest text-gold-500">
            {questions.length > 0
              ? "While you answer, here's what I assumed so far"
              : "What I understood"}
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

      {questions.length > 0 && (
        <div className="mt-4 border-t border-gold-200 pt-3">
          <p className="mb-2 text-xs text-primary/50">
            Answer these and I'll narrow the picks above down to what you actually need:
          </p>
          <ul className="mb-2 space-y-1">
            {questions.map((q) => (
              <li key={q} className="text-sm text-primary/80">{q}</li>
            ))}
          </ul>
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
