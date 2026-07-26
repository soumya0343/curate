import json
import re
from typing import Protocol

from app.core.errors import ProviderUnavailable, RateLimited
from app.core.logging import log_stage
from app.providers.keys import KeyRing, call_with_rotation, is_rate_limited


class GenerationProvider(Protocol):
    name: str

    async def generate_json(self, prompt: str, *, request_id: str) -> dict: ...


class StubGenerationProvider:
    """Deterministic provider for tests. Makes the whole pipeline testable with
    no network and no API keys, so CI needs no secrets."""

    name = "stub"

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.prompts.append(prompt)
        if not self._responses:
            raise RuntimeError("StubGenerationProvider exhausted")
        return self._responses.pop(0)


class MockGeneration:
    """Keyless rule-based stand-in for the generation model.

    Purpose: run the whole application - intent, sub-needs, assumptions, grouped
    results, streaming - with no API key, against the synthetic catalogue in
    `data/mock/`. Set `GENERATION_PRIMARY=mock`.

    It is a demonstration harness, not a small language model. It matches
    keywords, it does not understand; an unrecognised request falls back to one
    sub-need holding the query verbatim.

    The one rule it does keep, because breaking it would make the demo
    misleading: **every explanation is assembled from fields the candidate
    actually carries** - its group, price, price tier, rating, review count, and
    title-verified attributes. It never asserts a specification, and it cannot,
    because it has no source for one. That is the same grounding constraint the
    real rerank prompt imposes (spec 5, Stage 5).
    """

    name = "mock"

    _BUDGET = re.compile(
        r"(?:under|below|within|upto|up to|max|budget of|less than)\s*"
        r"(?:rs\.?|inr|₹)?\s*([\d][\d,]*)|(?:rs\.?|inr|₹)\s*([\d][\d,]*)",
        re.I)

    _GENDER = [
        ("women", r"\b(women|woman|women's|womens|female|girls?|ladies|wife|mother|mom|"
                  r"daughter|sister)\b"),
        ("men", r"\b(men|man|men's|mens|male|boys?|husband|father|dad|son|brother)\b"),
        ("unisex", r"\bunisex\b"),
    ]

    # keyword -> (intent field, value)
    _INTENT_TERMS = [
        (r"\btrek(king)?\b|\bhik(e|ing)\b|\bcamping\b", "activity", "trekking"),
        (r"\brunning\b|\bjogging\b", "activity", "running"),
        (r"\bgym\b|\bworkout\b|\bfitness\b", "activity", "fitness"),
        (r"\btravel(ling)?\b|\btrip\b|\bvacation\b", "activity", "travel"),
        (r"\boffice\b|\bwork from home\b|\bwfh\b|\bdesk\b", "activity", "work"),
        (r"\bbadminton\b", "activity", "badminton"),
        (r"\bwedding\b|\bmarriage\b|\bshaadi\b", "occasion", "wedding"),
        (r"\banniversar\w*\b", "occasion", "anniversary"),
        (r"\bgift\w*\b|\bhamper\b|\bpresent\b", "occasion", "gifting"),
        (r"\bwinter\b|\bcold\b|\bsnow\b", "season", "winter"),
        (r"\bsummer\b|\bhot weather\b", "season", "summer"),
        (r"\bmonsoon\b|\brain\w*\b", "season", "monsoon"),
    ]

    # keyword -> (group label, search query). Order decides group order.
    _SUB_NEEDS = [
        (r"\btrek(king)?\b|\bhik(e|ing)\b|\brucksack\b|\bbackpack\b",
         "Backpacks", "trekking backpack rucksack"),
        (r"\btrek(king)?\b|\bhik(e|ing)\b|\bshoes?\b|\bfootwear\b|\bwalking\b",
         "Footwear", "walking shoes footwear"),
        (r"\btrek(king)?\b|\bwinter\b|\bcold\b|\bclothing\b|\bjacket\b|\bthermal\b",
         "Warm clothing", "fleece jacket thermal winter wear"),
        (r"\btrek(king)?\b|\bcamping\b|\btorch\b|\bheadlamp\b",
         "Camping gear", "camping headlamp torch water bottle"),
        (r"\bwedding\b|\btraditional\b|\bethnic\b|\bkurta\b|\bsaree\b|\bsherwani\b",
         "Ethnic wear", "ethnic wear kurta saree traditional"),
        (r"\bgift\w*\b|\bhamper\b|\banniversar\w*\b|\bpresent\b",
         "Gifting", "premium gift set hamper"),
        (r"\bheadphone\w*\b|\bearbud\w*\b|\bearphone\w*\b|\baudio\b",
         "Audio", "wireless bluetooth headphones"),
        (r"\bworkout\b|\bgym\b|\bfitness\b|\bexercise\b|\bdumbbell\b|\byoga\b",
         "Fitness equipment", "home workout dumbbell yoga mat"),
        (r"\bkitchen\b|\bhome\b|\bapartment\b|\bhousewarming\b",
         "Home and kitchen", "kitchen home essentials"),
        (r"\bdesk\b|\boffice\b|\bwfh\b|\bwork from home\b",
         "Desk and office", "desk organiser office accessories"),
        (r"\bbadminton\b|\bracquet\b|\bracket\b|\bshuttle\b",
         "Badminton", "badminton racquet shuttlecock"),
        (r"\btravel(ling)?\b|\btrip\b|\bluggage\b|\bsuitcase\b|\btrolley\b",
         "Travel", "travel luggage trolley bag organiser"),
    ]

    def __init__(self, max_sub_needs: int = 4, picks_per_group: int = 3) -> None:
        self.max_sub_needs = max_sub_needs
        self.picks_per_group = picks_per_group

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        if "Candidate products" in prompt:
            return self._rerank(prompt)
        return self._intent(prompt)

    # -- stage 1 ----------------------------------------------------------
    @staticmethod
    def _extract_query(prompt: str) -> str:
        match = re.search(r"Customer request:\n(.*?)\n(?:Break the request|This is a "
                          r"follow-up)", prompt, re.S)
        return (match.group(1) if match else prompt).strip()

    def _intent(self, prompt: str) -> dict:
        query = self._extract_query(prompt)
        low = query.lower()

        intent: dict = {}
        assumptions: list[dict] = []

        budget = self._BUDGET.search(low)
        if budget:
            raw = budget.group(1) or budget.group(2)
            intent["budget_max"] = float(raw.replace(",", ""))

        for value, pattern in self._GENDER:
            if re.search(pattern, low):
                intent["gender"] = value
                break

        for pattern, field, value in self._INTENT_TERMS:
            if field not in intent and re.search(pattern, low):
                intent[field] = value

        sub_needs: list[dict] = []
        seen: set[str] = set()
        for pattern, label, search in self._SUB_NEEDS:
            if len(sub_needs) >= self.max_sub_needs:
                break
            if label in seen or not re.search(pattern, low):
                continue
            seen.add(label)
            sub_needs.append({"label": label, "query": search})

        if not sub_needs:
            # Nothing matched. Search the request as written rather than
            # inventing a category for it.
            sub_needs = [{"label": "Recommendations", "query": query}]

        if intent.get("season"):
            assumptions.append({
                "field": "season", "value": intent["season"],
                "reason": "inferred from wording in the request; not stated outright",
                "confidence": "medium"})
        if "budget_max" not in intent:
            assumptions.append({
                "field": "budget", "value": "no budget applied",
                "reason": "none stated, so nothing was filtered out on price",
                "confidence": "high"})

        clarifying = None
        if intent.get("occasion") == "gifting" and "budget_max" not in intent:
            clarifying = "What budget did you have in mind for the gift?"

        return {"intent": intent, "sub_needs": sub_needs, "assumptions": assumptions,
                "clarifying_question": clarifying, "confidence": 0.5}

    # -- stage 5 ----------------------------------------------------------
    _FIELD = re.compile(r"(\w+)=(.*)")

    @classmethod
    def _parse_candidates(cls, prompt: str) -> list[dict]:
        parsed: list[dict] = []
        for line in prompt.splitlines():
            if not line.startswith("id="):
                continue
            fields: dict[str, str] = {}
            for part in line.split(" | "):
                match = cls._FIELD.match(part.strip())
                if match:
                    fields[match.group(1)] = match.group(2).strip()
            parsed.append(fields)
        return parsed

    def _rerank(self, prompt: str) -> dict:
        by_group: dict[str, list[dict]] = {}
        for candidate in self._parse_candidates(prompt):
            by_group.setdefault(candidate.get("group", ""), []).append(candidate)

        groups = []
        for label, candidates in by_group.items():
            picks = [{"product_id": c["id"], "reason": self._reason(label, c)}
                     for c in candidates[: self.picks_per_group]]
            groups.append({"label": label, "picks": picks})
        return {"groups": groups}

    @staticmethod
    def _reason(label: str, candidate: dict) -> str:
        """Assemble a sentence from fields the candidate carries. Nothing else."""
        bits = [f"Matches the {label.lower()} need"]
        if candidate.get("price"):
            tier = f" in the {candidate['tier']} tier" if candidate.get("tier") else ""
            bits.append(f"at {candidate['price']}{tier}")
        if candidate.get("rating"):
            bits.append(f"rated {candidate['rating']}")
        sentence = ", ".join(bits) + "."

        verified = candidate.get("verified")
        if verified:
            try:
                facts = json.loads(verified)
            except json.JSONDecodeError:
                return sentence
            readable = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items())
            sentence += f" Stated in the listing title - {readable}."
        return sentence


def parse_json_response(text: str) -> dict:
    """Parse a model's JSON reply, tolerating the wrappers models add.

    Every provider here is asked for JSON and most honour it exactly. Some
    OpenAI-compatible endpoints still return it inside ``` fences or with a
    sentence in front. Failing the whole request on a stray backtick would be a
    worse outcome than slicing to the outermost braces.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


class GeminiGeneration:
    name = "gemini"

    def __init__(self, api_keys: str | list[str], model: str = "gemini-2.5-flash",
                 timeout: float = 30.0) -> None:
        self._ring = KeyRing(api_keys)
        self._model = model
        self._timeout = timeout
        self._clients: dict[str, object] = {}

    def _client(self, api_key: str):
        # Built per key and cached: the SDK binds its credential at construction,
        # so rotating means a different client, not a mutated one.
        if api_key not in self._clients:
            from google import genai
            self._clients[api_key] = genai.Client(api_key=api_key)
        return self._clients[api_key]

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        async def call(api_key: str) -> dict:
            resp = await self._client(api_key).aio.models.generate_content(
                model=self._model, contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            return parse_json_response(resp.text)

        return await call_with_rotation(self._ring, call, request_id=request_id,
                                        provider=self.name)


class GroqGeneration:
    name = "groq"

    def __init__(self, api_keys: str | list[str],
                 model: str = "llama-3.3-70b-versatile",
                 timeout: float = 30.0) -> None:
        self._ring = KeyRing(api_keys)
        self._model = model
        self._timeout = timeout
        self._clients: dict[str, object] = {}

    def _client(self, api_key: str):
        if api_key not in self._clients:
            from groq import AsyncGroq
            self._clients[api_key] = AsyncGroq(api_key=api_key, timeout=self._timeout)
        return self._clients[api_key]

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        async def call(api_key: str) -> dict:
            resp = await self._client(api_key).chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            return parse_json_response(resp.choices[0].message.content)

        return await call_with_rotation(self._ring, call, request_id=request_id,
                                        provider=self.name)


class CerebrasGeneration:
    """Cerebras Inference, over its OpenAI-compatible HTTP API.

    Called with httpx rather than the vendor SDK: the endpoint is a plain
    `POST /chat/completions`, httpx is already a dependency, and one less SDK is
    one less place for a client-construction difference to hide. `base_url` and
    `model` stay configurable so a model rename does not require a code change.
    """

    name = "cerebras"

    def __init__(self, api_keys: str | list[str], model: str = "llama-3.3-70b",
                 base_url: str = "https://api.cerebras.ai/v1",
                 timeout: float = 30.0) -> None:
        self._ring = KeyRing(api_keys)
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        import httpx

        async def call(api_key: str) -> dict:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2,
                    },
                )
                # raise_for_status carries the 429 the rotation logic looks for.
                resp.raise_for_status()
                payload = resp.json()
            return parse_json_response(payload["choices"][0]["message"]["content"])

        return await call_with_rotation(self._ring, call, request_id=request_id,
                                        provider=self.name)


class FallbackChain:
    """Try each provider in order; raise when all of them have failed.

    The original design capped this at two providers, because every extra one
    multiplies prompt-compatibility testing across differing structured-output
    support and error semantics (spec 3.2). That cost is real and has not gone
    away - the JSON-wrapper tolerance in `parse_json_response` exists because of
    it. The chain is open-ended now because free-tier rate limits, not provider
    outages, are what actually stops this application, and a third provider is
    the cheapest answer to that.

    Rate limits are distinguished from failures: if every provider refused on
    quota, the caller gets `RateLimited` (429, retryable) rather than
    `ProviderUnavailable` (503). "Come back shortly" and "this is broken" are
    different messages and a client can act on the difference.
    """

    name = "chain"

    def __init__(self, *providers: GenerationProvider | None) -> None:
        self.providers = [p for p in providers if p is not None]
        if not self.providers:
            raise ValueError("FallbackChain needs at least one provider")

    @property
    def primary(self) -> GenerationProvider:
        return self.providers[0]

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        errors: list[str] = []
        all_rate_limited = True

        for provider in self.providers:
            try:
                return await provider.generate_json(prompt, request_id=request_id)
            except Exception as exc:  # noqa: BLE001 - any failure moves to the next
                if not is_rate_limited(exc):
                    all_rate_limited = False
                errors.append(f"{provider.name}: {str(exc)[:120]}")
                log_stage(request_id, "provider_failover", provider=provider.name,
                          rate_limited=is_rate_limited(exc), error=str(exc)[:200])

        summary = "; ".join(errors)
        if all_rate_limited:
            raise RateLimited(f"every provider is rate limited ({summary})")
        raise ProviderUnavailable(f"all {len(self.providers)} providers failed: {summary}")
