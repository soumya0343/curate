import { AssumptionChips } from "./components/AssumptionChips";
import { InputPanel } from "./components/InputPanel";
import { RefineBar } from "./components/RefineBar";
import { ResultGroup } from "./components/ResultGroup";
import { SideNavBar } from "./components/SideNavBar";
import { TopNavBar } from "./components/TopNavBar";
import { useRecommendation } from "./hooks/useRecommendation";

export default function App() {
  const { status, response, error, submitStreaming, refine, stage, partial } = useRecommendation();

  const assumptions =
    response?.assumptions ?? partial?.assumptions ?? [];

  const isActive = stage !== "idle";

  return (
    <div className="min-h-screen bg-surface font-sans">
      <TopNavBar />

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
            <InputPanel onSubmit={submitStreaming} busy={status === "loading"} />
          </div>

          {/* Error */}
          {status === "error" && (
            <div className="mb-6 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
              {error?.message}
            </div>
          )}

          {/* Streaming progress — assumptions visible before results land */}
          {partial && stage !== "ready" && (
            <div className="mt-2">
              <AssumptionChips
                assumptions={partial.assumptions ?? []}
                question={partial.clarifying_question ?? null}
                onAnswer={refine}
              />
              <div className="flex items-center gap-2 text-sm text-primary/40">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-gold-400" />
                {stage === "searching" ? "Searching the catalogue…" : "Choosing the best matches…"}
              </div>
            </div>
          )}

          {/* Results */}
          {status === "ready" && response && (
            <div>
              <AssumptionChips
                assumptions={response.assumptions}
                question={response.clarifying_question}
                onAnswer={refine}
              />
              {response.relaxations.map((note) => (
                <p key={note} className="mb-3 rounded-xl border border-gold-200 bg-gold-50 p-3 text-sm text-primary/70">
                  {note}
                </p>
              ))}
              {response.groups.map((group) => (
                <ResultGroup key={group.label} group={group} />
              ))}
              <RefineBar onRefine={refine} busy={false} />
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
    </div>
  );
}
