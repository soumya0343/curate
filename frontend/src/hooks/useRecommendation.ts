import { useCallback, useRef, useState } from "react";
import { ApiFailure, recommend, recommendStream } from "../lib/api";
import type { RecommendResponse } from "../types";

type Status = "idle" | "loading" | "ready" | "error";
type Stage = "idle" | "understanding" | "searching" | "ranking" | "ready" | "error";

export function useRecommendation() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [partial, setPartial] = useState<Partial<RecommendResponse> | null>(null);
  const sessionId = useRef<string | undefined>(undefined);

  const run = useCallback(async (query: string, useSession: boolean) => {
    setStatus("loading");
    setError(null);
    try {
      const result = await recommend(query, useSession ? sessionId.current : undefined);
      sessionId.current = result.session_id;
      setResponse(result);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiFailure
        ? err
        : new ApiFailure("INTERNAL", "Something went wrong.", false));
      setStatus("error");
    }
  }, []);

  const submit = useCallback((query: string) => run(query, false), [run]);
  const refine = useCallback((query: string) => run(query, true), [run]);

  const submitStreaming = useCallback(async (query: string, useSession = false) => {
    setStatus("loading");
    setStage("understanding");
    setError(null);
    setResponse(null);
    await recommendStream(query, useSession ? sessionId.current : undefined, {
      onUnderstood: (data) => {
        sessionId.current = data.session_id;
        setPartial({
          session_id: data.session_id,
          assumptions: data.assumptions,
          clarifying_question: data.clarifying_question,
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
            intent: {},
            assumptions: current?.assumptions ?? [],
            clarifying_question: current?.clarifying_question ?? null,
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

  return { status, response, error, submit, refine, stage, partial, submitStreaming };
}
