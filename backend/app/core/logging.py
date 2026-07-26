import json
import logging
import sys

_LOGGER = logging.getLogger("assistant")


class _StderrHandler(logging.StreamHandler):
    """A StreamHandler that resolves `sys.stderr` at emit time.

    `StreamHandler(sys.stderr)` captures the stream object once, at construction.
    Combined with `setup_logging()` being idempotent, that makes the first caller
    the permanent owner of where logs go: anything importing a module that
    configures logging binds the handler to whatever `sys.stderr` was then, and a
    later rebind (pytest's capture, a supervisor reopening streams) is silently
    ignored. Looking the stream up per record costs nothing and removes a class
    of bug whose symptom - logs vanishing - looks nothing like its cause.
    """

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        """Ignore the base class's assignment; the property is the source."""


def setup_logging() -> None:
    if _LOGGER.handlers:
        return
    handler = _StderrHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


def log_stage(request_id: str, stage: str, **fields) -> None:
    """One structured JSON line per pipeline stage."""
    _LOGGER.info(json.dumps({"request_id": request_id, "stage": stage, **fields}))
