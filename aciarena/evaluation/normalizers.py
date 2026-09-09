"""Deterministic normalization at the MAS-to-verifier boundary.

The normalizer deliberately preserves the response body.  Math and Code
extraction remain the responsibility of their versioned verifiers, while the
unaltered model output is retained separately as ``raw_response``.
"""


NORMALIZER_VERSION = "text-envelope-v1"


class NormalizationError(ValueError):
    """Raised when an Agent response cannot satisfy the output contract."""


def normalize_response(raw_response: str) -> str:
    """Return stable verifier input without extracting or rewriting content.

    Only transport-level variation is removed: UTF-8 BOM, CRLF/CR line
    endings, and leading/trailing whitespace.  Internal whitespace, Markdown
    fences, explanations, and attack evidence are preserved.
    """
    if not isinstance(raw_response, str):
        raise NormalizationError("raw_response must be a string")

    response = raw_response.replace("\r\n", "\n").replace("\r", "\n").strip()
    if response.startswith("\ufeff"):
        response = response[1:].strip()
    return response
