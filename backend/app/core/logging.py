import json
import logging
import sys

_LOGGER = logging.getLogger("assistant")


def setup_logging() -> None:
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


def log_stage(request_id: str, stage: str, **fields) -> None:
    """One structured JSON line per pipeline stage."""
    _LOGGER.info(json.dumps({"request_id": request_id, "stage": stage, **fields}))
