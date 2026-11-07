from __future__ import annotations

from tool.link_resolve import GoogleNewsLinkResolver

GOOGLE = "https://news.google.com/rss/articles/CBMiGold"


async def test_direct_url_passes_through() -> None:
    calls: list[str] = []

    def decoder(url: str, timeout: float = 10.0):
        calls.append(url)
        return {"success": True, "decoded_url": "https://example.com"}

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    url = "https://www.reuters.com/markets/gold"
    assert await resolver.resolve(url) == url
    assert calls == []


async def test_decodes_google_dict_result() -> None:
    def decoder(url: str, timeout: float = 10.0):
        return {"success": True, "decoded_url": "https://www.bbc.com/news/gold"}

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    assert await resolver.resolve(GOOGLE) == "https://www.bbc.com/news/gold"


async def test_decodes_google_string_result() -> None:
    def decoder(url: str, timeout: float = 10.0):
        return "https://www.cnbc.com/gold"

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    assert await resolver.resolve(GOOGLE) == "https://www.cnbc.com/gold"


async def test_failed_decode_returns_none() -> None:
    def decoder(url: str, timeout: float = 10.0):
        return {"success": False, "message": "not found"}

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    assert await resolver.resolve(GOOGLE) is None


async def test_decoder_exception_returns_none() -> None:
    def decoder(url: str, timeout: float = 10.0):
        raise RuntimeError("network")

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    assert await resolver.resolve(GOOGLE) is None


async def test_invalid_decoded_url_returns_none() -> None:
    def decoder(url: str, timeout: float = 10.0):
        return {"success": True, "decoded_url": "javascript:alert(1)"}

    resolver = GoogleNewsLinkResolver(decoder=decoder)
    assert await resolver.resolve(GOOGLE) is None
