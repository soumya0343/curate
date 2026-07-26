import type { Assumption } from "../types";

interface Props {
  assumptions: Assumption[];
  stage: string;
}

const STAGE_LABEL: Record<string, string> = {
  idle: "Awaiting your request",
  understanding: "Understanding your intent…",
  searching: "Searching the catalogue…",
  ranking: "Choosing the best matches…",
  ready: "Results ready",
  error: "Something went wrong",
};

const VERIFIED_FIELDS = new Set(["budget", "price", "min_price", "max_price"]);

export function SideNavBar({ assumptions, stage }: Props) {
  const destination = assumptions.find((a) => a.field === "destination" || a.field === "occasion");
  const budget = assumptions.find((a) => a.field === "budget" || a.field === "max_price");
  const refinements = assumptions.filter(
    (a) => a !== destination && a !== budget,
  );

  return (
    <aside className="sticky top-20 hidden h-fit w-64 shrink-0 rounded-xl border border-primary/10 bg-white p-5 lg:block">
      <p className="mb-4 text-xs font-medium uppercase tracking-widest text-primary/40">
        Concierge
      </p>

      <div className="mb-4 text-xs text-primary/50">
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full mr-1.5 align-middle ${
            stage === "ready" ? "bg-green-400" :
            stage === "idle" || stage === "error" ? "bg-primary/20" :
            "bg-gold-400 animate-pulse"
          }`}
        />
        {STAGE_LABEL[stage] ?? stage}
      </div>

      {destination && (
        <div className="mb-3">
          <p className="text-xs text-primary/40 uppercase tracking-wider mb-0.5">Destination</p>
          <p className="text-sm font-medium text-primary">{destination.value}</p>
        </div>
      )}

      {budget && (
        <div className="mb-3">
          <p className="text-xs text-primary/40 uppercase tracking-wider mb-0.5">Budget</p>
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-medium text-primary">{budget.value}</p>
            {VERIFIED_FIELDS.has(budget.field) && (
              <span className="rounded-full bg-gold-100 px-1.5 py-0.5 text-[10px] text-gold-500 font-medium">
                verified
              </span>
            )}
          </div>
        </div>
      )}

      {refinements.length > 0 && (
        <div>
          <p className="text-xs text-primary/40 uppercase tracking-wider mb-1.5">Refinements</p>
          <ul className="flex flex-col gap-1.5">
            {refinements.map((a) => (
              <li key={`${a.field}-${a.value}`} className="flex items-start gap-1.5">
                <span
                  className={`mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                    VERIFIED_FIELDS.has(a.field)
                      ? "bg-gold-100 text-gold-500"
                      : "bg-primary/5 text-primary/50"
                  }`}
                >
                  {a.confidence}
                </span>
                <span className="text-xs text-primary/70" title={a.reason}>
                  {a.value}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {assumptions.length === 0 && stage === "idle" && (
        <p className="text-xs text-primary/30 italic">
          Your context will appear here as I understand your request.
        </p>
      )}
    </aside>
  );
}
