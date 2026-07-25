import { AssumptionChips } from "./components/AssumptionChips";
import { InputPanel } from "./components/InputPanel";
import { RefineBar } from "./components/RefineBar";
import { ResultGroup } from "./components/ResultGroup";
import { useRecommendation } from "./hooks/useRecommendation";

export default function App() {
  const { status, response, error, submit, refine } = useRecommendation();

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold text-slate-900">Shopping Assistant</h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">
        Describe what you need. I'll work out the details.
      </p>

      <InputPanel onSubmit={submit} busy={status === "loading"} />

      {status === "error" && (
        <p className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          {error?.message}
        </p>
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
    </main>
  );
}
