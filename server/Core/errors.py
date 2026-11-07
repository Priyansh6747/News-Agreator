class NewsError(Exception):
    """Base error for the compute backend."""


class BackendNotConfigured(NewsError):
    def __init__(self, backend: str):
        super().__init__(f"backend not configured: {backend}")
        self.backend = backend


class BackendTimeout(NewsError):
    def __init__(self, backend: str):
        super().__init__(f"backend timed out: {backend}")
        self.backend = backend


class FetchBlocked(NewsError):
    def __init__(self, url: str, reason: str):
        super().__init__(f"fetch blocked: {url} ({reason})")
        self.url = url
        self.reason = reason


class HttpTimeout(NewsError):
    def __init__(self, url: str):
        super().__init__(f"http timeout: {url}")
        self.url = url


class HttpError(NewsError):
    def __init__(self, url: str, reason: str):
        super().__init__(f"http error: {url} ({reason})")
        self.url = url
        self.reason = reason


class HttpBodyTooLarge(HttpError):
    def __init__(self, url: str, limit_bytes: int):
        super().__init__(url, f"body exceeds {limit_bytes} bytes")


class BackendRateLimited(NewsError):
    def __init__(self, backend: str):
        super().__init__(f"backend rate limited: {backend}")
        self.backend = backend


class BackendCoolingDown(NewsError):
    def __init__(self, backend: str):
        super().__init__(f"backend cooling down: {backend}")
        self.backend = backend


class FeedParseError(NewsError):
    def __init__(self, reason: str):
        super().__init__(f"feed parse failed: {reason}")
        self.reason = reason


class ExtractionFailed(NewsError):
    pass


class GeneratorNotConfigured(NewsError):
    def __init__(self):
        super().__init__("generator is not configured")


class GeneratorError(NewsError):
    pass
