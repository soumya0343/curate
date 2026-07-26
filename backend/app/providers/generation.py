import json
import re
from typing import Protocol

from app.core.errors import ProviderUnavailable
from app.core.logging import log_stage


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


class GeminiGeneration:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 timeout: float = 30.0) -> None:
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.aio.models.generate_content(
            model=self._model, contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        return json.loads(resp.text)


class GroqGeneration:
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile",
                 timeout: float = 30.0) -> None:
        from groq import AsyncGroq
        self._client = AsyncGroq(api_key=api_key, timeout=timeout)
        self._model = model

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)


class FallbackChain:
    """Primary -> one fallback -> ProviderUnavailable.

    Deliberately two providers, not three: each additional provider multiplies
    prompt-compatibility testing across differing structured-output support and
    error semantics (spec 3.2).
    """

    name = "chain"

    def __init__(self, primary: GenerationProvider,
                 fallback: GenerationProvider | None) -> None:
        self.primary = primary
        self.fallback = fallback

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        try:
            return await self.primary.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - any provider failure triggers fallback
            log_stage(request_id, "provider_failover",
                      provider=self.primary.name, error=str(exc)[:200])
            if self.fallback is None:
                raise ProviderUnavailable(f"{self.primary.name} failed: {exc}") from exc

        try:
            return await self.fallback.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"both {self.primary.name} and {self.fallback.name} failed: {exc}") from exc
