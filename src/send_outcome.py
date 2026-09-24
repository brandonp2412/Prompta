from __future__ import annotations


class SendOutcomeUnknownError(RuntimeError):
    """A user-send mutation may have been applied and must not be replayed blindly."""

    code = "send_outcome_unknown"
    retry_safe = False
    reconciliation_safe = True

    def __init__(
        self,
        message: str,
        *,
        stage: str = "send_mutation",
    ) -> None:
        super().__init__(message)
        self.stage = stage
