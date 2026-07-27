import { useCallback, useRef, useState } from "react";
import { ApiFailure, recommendStream } from "../lib/api";
import type { RecommendResponse } from "../types";

type Status = "idle" | "loading" | "ready" | "error";
type Stage = "idle" | "understanding" | "searching" | "ranking" | "ready" | "error";

export function useRecommendation() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [partial, setPartial] = useState<Partial<RecommendResponse> | null>(null);
  const [queries, setQueries] = useState<string[]>([]);
  const sessionId = useRef<string | undefined>(undefined);

  const submitStreaming = useCallback(async (query: string, useSession = false) => {
    setQueries((prev) => (useSession ? [...prev, query] : [query]));
    setStatus("loading");
    setStage("understanding");
    setError(null);
    setPartial(null);
    await recommendStream(query, useSession ? sessionId.current : undefined, {
      onUnderstood: (data) => {
        sessionId.current = data.session_id;
        setPartial({
          session_id: data.session_id,
          intent: data.intent,
          assumptions: data.assumptions,
          clarifying_questions: data.clarifying_questions,
          awaiting_clarification: data.awaiting_clarification ?? false,
        } as Partial<RecommendResponse>);
        setStage("searching");
      },
      onSearching: () => setStage("ranking"),
      onResults: (data) => {
        // Functional update: `partial` was set by onUnderstood earlier in this same
        // callback, so reading it from the closure would see the stale value.
        setPartial((current) => {
          setResponse({
            session_id: sessionId.current ?? "",
            intent: current?.intent ?? {},
            assumptions: current?.assumptions ?? [],
            clarifying_questions: current?.clarifying_questions ?? [],
            groups: data.groups,
            relaxations: data.relaxations ?? [],
            timings_ms: {},
          } as RecommendResponse);
          return current;
        });
        setStage("ready");
        setStatus("ready");
      },
      onError: (err) => { setError(err); setStage("error"); setStatus("error"); },
    });
  }, []);

  const submit = useCallback((query: string) => submitStreaming(query, false), [submitStreaming]);
  const refine = useCallback((query: string) => submitStreaming(query, true), [submitStreaming]);

  return { status, response, error, submit, refine, stage, partial, queries };
}
