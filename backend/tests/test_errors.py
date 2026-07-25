import json

from app.core.errors import NoResults, ProviderUnavailable, RateLimited


def test_envelope_shape():
    e = RateLimited("slow down")
    assert e.envelope() == {
        "error": {"code": "RATE_LIMITED", "message": "slow down", "retryable": True}}


def test_provider_unavailable_is_not_retryable_by_client():
    assert ProviderUnavailable("all providers failed").retryable is False


def test_no_results_is_a_client_visible_200_level_concern():
    assert NoResults("nothing matched").http_status == 200


def test_log_stage_emits_single_json_line(capsys):
    from app.core.logging import log_stage, setup_logging
    setup_logging()
    log_stage("req-1", "intent", duration_ms=812.5, provider="gemini")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["request_id"] == "req-1"
    assert payload["stage"] == "intent"
    assert payload["provider"] == "gemini"
