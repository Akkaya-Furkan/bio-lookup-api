class LookupFailure(Exception):
    """Base class: carries which upstream failed."""

    def __init__(self, source: str, detail: str):
        super().__init__(detail)
        self.source, self.detail = source, detail


class NotFoundError(LookupFailure):
    """The upstream answered and has no such record."""


class UpstreamError(LookupFailure):
    """The upstream failed, timed out or throttled us; `timeout` picks 504 over 502."""

    def __init__(self, source: str, detail: str, timeout: bool = False):
        super().__init__(source, detail)
        self.timeout = timeout
