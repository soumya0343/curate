"""Smoke-test every configured credential against the real provider.

Answers one question the test suite deliberately cannot: do these keys work?
The suite runs offline with stubs, so a typo, an expired key, a wrong base URL
or a renamed model all pass CI and fail at the first real request.

Each key is exercised INDIVIDUALLY rather than through its ring, because a ring
hides exactly what this script exists to find - with rotation, one working key
out of three looks identical to three working keys.

Prints a masked identifier only (last 4 characters). Never prints a credential.

    cd backend && python scripts/check_providers.py
    cd backend && python scripts/check_providers.py --embeddings   # costs a call
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.providers.embedding import GeminiEmbedding  # noqa: E402
from app.providers.generation import (CerebrasGeneration,  # noqa: E402
                                      GeminiGeneration, GitHubModelsGeneration,
                                      GroqGeneration)
from app.providers.keys import KeyRing, is_rate_limited  # noqa: E402

PROMPT = 'Reply with this JSON object exactly: {"ok": true}'

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def mask(key: str) -> str:
    return f"…{key[-4:]}"


def build(name: str, key: str, settings):
    timeout = settings.llm_timeout_seconds
    if name == "gemini":
        return GeminiGeneration(key, timeout=timeout)
    if name == "groq":
        return GroqGeneration(key, timeout=timeout)
    if name == "cerebras":
        return CerebrasGeneration(key, model=settings.cerebras_model,
                                  base_url=settings.cerebras_base_url, timeout=timeout)
    if name == "github":
        return GitHubModelsGeneration(key, model=settings.github_model,
                                      base_url=settings.github_base_url, timeout=timeout)
    raise SystemExit(f"unknown provider {name!r}")


async def check_key(name: str, key: str, settings) -> bool:
    provider = build(name, key, settings)
    try:
        payload = await provider.generate_json(PROMPT, request_id="check")
    except Exception as exc:  # noqa: BLE001 - reporting, not handling
        label = "RATE LIMITED" if is_rate_limited(exc) else "FAILED"
        colour = YELLOW if is_rate_limited(exc) else RED
        print(f"  {colour}{label:12s}{RESET} {mask(key)}  {type(exc).__name__}: "
              f"{str(exc)[:150]}")
        return is_rate_limited(exc)  # the credential is valid, the quota is not
    print(f"  {GREEN}OK{RESET}           {mask(key)}  -> {str(payload)[:60]}")
    return True


async def check_embeddings(settings) -> bool:
    keys = settings.keys_for("gemini")
    if not keys:
        print(f"  {DIM}no gemini credential{RESET}")
        return False
    print(f"\nembeddings  {DIM}{settings.embedding_model} @ {settings.embedding_dims}d"
          f"{RESET}")
    ok = False
    for key in KeyRing(keys)._keys:
        embedder = GeminiEmbedding(key, settings.embedding_model, settings.embedding_dims)
        try:
            matrix = await embedder.embed(["trekking backpack"])
        except Exception as exc:  # noqa: BLE001
            colour = YELLOW if is_rate_limited(exc) else RED
            print(f"  {colour}{'RATE LIMITED' if is_rate_limited(exc) else 'FAILED':12s}"
                  f"{RESET} {mask(key)}  {type(exc).__name__}: {str(exc)[:150]}")
            continue
        dims = matrix.shape[1]
        match = "matches manifest" if dims == settings.embedding_dims else (
            f"{RED}WRONG DIMS{RESET}")
        print(f"  {GREEN}OK{RESET}           {mask(key)}  {dims}d {match}")
        ok = True
    return ok


async def main(check_embed: bool) -> int:
    settings = get_settings()
    order = settings.generation_order()
    print(f"chain: {' -> '.join(order)}\n")

    healthy: list[str] = []
    for name in order:
        if name == "mock":
            print(f"{name}  {DIM}keyless rule-based provider, nothing to check{RESET}")
            healthy.append(name)
            continue

        keys = settings.keys_for(name)
        if not keys:
            print(f"{name}  {DIM}no credential configured, skipped in the chain{RESET}")
            continue

        ring = KeyRing(keys)
        print(f"{name}  {DIM}{len(ring)} credential(s){RESET}")
        results = [await check_key(name, key, settings) for key in ring._keys]
        if any(results):
            healthy.append(name)

    if check_embed:
        await check_embeddings(settings)

    print()
    if healthy:
        print(f"{GREEN}usable generation providers: {', '.join(healthy)}{RESET}")
        return 0
    print(f"{RED}no generation provider is usable{RESET}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", action="store_true",
                        help="also check the embedding credential (one extra call)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.embeddings)))
