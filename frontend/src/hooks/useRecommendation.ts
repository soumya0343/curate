import { useCallback, useRef, useState } from "react";
import { ApiFailure, recommend } from "../lib/api";
import type { RecommendResponse } from "../types";

type Status = "idle" | "loading" | "ready" | "error";

export function useRecommendation() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
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

  return { status, response, error, submit, refine };
}
