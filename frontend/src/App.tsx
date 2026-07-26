import { AssumptionChips } from "./components/AssumptionChips";
import { InputPanel } from "./components/InputPanel";
import { RefineBar } from "./components/RefineBar";
import { ResultGroup } from "./components/ResultGroup";
import { useRecommendation } from "./hooks/useRecommendation";

export default function App() {
  const { status, response, error, submitStreaming, refine, stage, partial } = useRecommendation();

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold text-slate-900">Shopping Assistant</h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">
        Describe what you need. I'll work out the details.
      </p>

      <InputPanel onSubmit={submitStreaming} busy={status === "loading"} />

      {status === "error" && (
        <p className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          {error?.message}
        </p>
      )}

      {partial && stage !== "ready" && (
        <div className="mt-8">
          <AssumptionChips
            assumptions={partial.assumptions ?? []}
            question={partial.clarifying_question ?? null}
            onAnswer={refine}
          />
          <p className="text-sm text-slate-500">
            {stage === "searching" ? "Searching the catalogue…" : "Choosing the best matches…"}
          </p>
        </div>
      )}

      {status === "ready" && response && (
        <div className="mt-8">
          <AssumptionChips
            assumptions={response.assumptions}
            question={response.clarifying_question}
            onAnswer={refine}
          />
          {response.relaxations.map((note) => (
            <p key={note} className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              {note}
            </p>
          ))}
          {response.groups.map((group) => (
            <ResultGroup key={group.label} group={group} />
          ))}
          <RefineBar onRefine={refine} busy={false} />
        </div>
      )}

      {/* ODC-By 4.3: results are a Produced Work, so the source is named
          wherever they are shown publicly, not only in the repository. */}
      <footer className="mt-16 border-t border-slate-200 pt-4 text-xs text-slate-400">
        Contains information from{" "}
        <a
          className="underline hover:text-slate-600"
          href="https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products"
          target="_blank"
          rel="noreferrer"
        >
          Amazon India Products 2023
        </a>{" "}
        which is made available under the{" "}
        <a
          className="underline hover:text-slate-600"
          href="https://opendatacommons.org/licenses/by/1-0/"
          target="_blank"
          rel="noreferrer"
        >
          ODC Attribution License
        </a>
        . Product titles and images belong to their respective rights holders.
      </footer>
    </main>
  );
}
