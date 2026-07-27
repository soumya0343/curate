// frontend/src/pages/DiscoverPage.tsx
import { AssumptionChips, statedFactChips } from "../components/AssumptionChips";
import { InputPanel } from "../components/InputPanel";
import { RefineBar } from "../components/RefineBar";
import { ResultGroup } from "../components/ResultGroup";
import { SideNavBar } from "../components/SideNavBar";
import { useRecommendation } from "../hooks/useRecommendation";

export function DiscoverPage() {
  const { status, response, error, submit, refine, stage, partial, queries } = useRecommendation();

  const baseAssumptions = response?.assumptions ?? partial?.assumptions ?? [];
  const intent = response?.intent ?? partial?.intent;
  const assumptions = [
    ...statedFactChips(intent, new Set(baseAssumptions.map((a) => a.field))),
    ...baseAssumptions,
  ];

  const isActive = stage !== "idle";
  const isLoading = status === "loading";

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 lg:flex lg:gap-10 lg:px-8">
      {/* Side concierge panel */}
      <SideNavBar assumptions={assumptions} stage={stage} />

      {/* Main content */}
      <main className="min-w-0 flex-1">

        {/* Landing hero — only shown before any query */}
        {!isActive && (
          <div className="mb-10 text-center">
            <h1 className="font-serif text-5xl font-medium tracking-tight text-primary sm:text-6xl">
              Your personal<br />
              <em>shopping concierge.</em>
            </h1>
            <p className="mx-auto mt-4 max-w-md text-sm text-primary/50">
              Tell me what you need — occasion, destination, budget. I'll find exactly what fits.
            </p>
          </div>
        )}

        {/* Prompt bar */}
        <div className={isActive ? "mb-8" : "mx-auto max-w-xl mb-10"}>
          <InputPanel onSubmit={submit} busy={isLoading} />
        </div>

        {/* Error */}
        {status === "error" && (
          <div className="mb-6 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
            {error?.message}
          </div>
        )}

        {/* What you've asked/answered so far this session — text only, not repeated results */}
        {queries.length > 0 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {queries.map((q, i) => (
              <span
                key={i}
                className="rounded-2xl bg-primary/5 px-4 py-2 text-sm text-primary/80"
              >
                {q}
              </span>
            ))}
          </div>
        )}

        {/* Streaming progress — a loud banner, not a faint dot, since old results
            now stay on screen underneath it and must not read as "up to date" */}
        {stage !== "idle" && stage !== "ready" && stage !== "error" && (
          <div className="mb-4 flex items-center gap-2.5 rounded-xl border border-gold-300 bg-gold-50 px-4 py-3 text-sm font-medium text-primary shadow-sm">
            <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-gold-500" />
            {stage === "understanding"
              ? "Understanding your request…"
              : stage === "searching"
              ? "Searching the catalogue…"
              : "Choosing the best matches…"}
          </div>
        )}
        {partial && stage !== "idle" && stage !== "ready" && stage !== "error" && (
          <AssumptionChips
            assumptions={[
              ...statedFactChips(partial.intent, new Set((partial.assumptions ?? []).map((a) => a.field))),
              ...(partial.assumptions ?? []),
            ]}
            questions={partial.clarifying_questions ?? []}
            onAnswer={refine}
          />
        )}

        {/* Results — stay visible (dimmed) while a follow-up is loading, rather
            than disappearing the instant a new request starts */}
        {response && !response.awaiting_clarification && (
          <div className={isLoading ? "pointer-events-none opacity-40 transition-opacity" : ""}>
            {status === "ready" && (
              <>
                <AssumptionChips
                  assumptions={[
                    ...statedFactChips(response.intent, new Set(response.assumptions.map((a) => a.field))),
                    ...response.assumptions,
                  ]}
                  questions={response.clarifying_questions}
                  onAnswer={refine}
                  refineBar={<RefineBar onRefine={refine} busy={isLoading} />}
                />
                {response.clarifying_questions.length > 0 && (
                  <p className="mb-4 text-sm text-primary/50">
                    Meanwhile, while you think that over — here's what I'd suggest based on what I assumed:
                  </p>
                )}
              </>
            )}
            {response.relaxations.map((note) => (
              <p key={note} className="mb-3 rounded-xl border border-gold-200 bg-gold-50 p-3 text-sm text-primary/70">
                {note}
              </p>
            ))}
            {response.groups.map((group) => (
              <ResultGroup key={group.label} group={group} />
            ))}
          </div>
        )}

        {/* Attribution footer */}
        <footer className="mt-16 border-t border-primary/10 pt-4 text-xs text-primary/30">
          Contains information from{" "}
          <a
            className="underline hover:text-primary/60 transition"
            href="https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products"
            target="_blank"
            rel="noreferrer"
          >
            Amazon India Products 2023
          </a>{" "}
          under the{" "}
          <a
            className="underline hover:text-primary/60 transition"
            href="https://opendatacommons.org/licenses/by/1-0/"
            target="_blank"
            rel="noreferrer"
          >
            ODC Attribution License
          </a>
          . Product titles and images belong to their respective rights holders.
        </footer>
      </main>
    </div>
  );
}
