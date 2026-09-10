"""Web tool entry points (search/fetch/download) used by the tool registry."""

from __future__ import annotations

from pathlib import Path

from axiom.core.types import ToolResult
from axiom.tools.registry import ToolContext
from axiom.tools.web import WebClient


def _client(ctx: ToolContext) -> WebClient:
    return WebClient((ctx.config or {}).get("web") or {})


async def web_fetch(url: str, _context: ToolContext) -> ToolResult:
    """Fetch a URL and return status + text body."""
    try:
        response = await _client(_context).fetch(url)
    except Exception as exc:
        return ToolResult(
            tool_call_id="", name="web_fetch", content=f"Error: {exc}", is_error=True
        )
    body = response.body
    if "html" in response.content_type:
        body = _strip_html(body)
    body = body[:20000]
    content = f"status: {response.status}\ncontent-type: {response.content_type}\n\n{body}"
    return ToolResult(tool_call_id="", name="web_fetch", content=content)


async def web_search(query: str, _context: ToolContext, max_results: int = 5) -> ToolResult:
    """Web search via DuckDuckGo lite endpoint (no API key required)."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.post(
                "https://lite.duckduckgo.com/lite/", data={"q": query}
            )
            response.raise_for_status()
            results = _parse_ddg(response.text, max_results)
    except Exception as exc:
        return ToolResult(
            tool_call_id="", name="web_search", content=f"Error: search failed: {exc}", is_error=True
        )
    if not results:
        return ToolResult(tool_call_id="", name="web_search", content="No results found.")
    return ToolResult(
        tool_call_id="", name="web_search", content="\n".join(f"{t}\n{u}" for t, u in results)
    )


async def web_download(url: str, path: str, _context: ToolContext) -> ToolResult:
    """Download a URL to a workspace file with size limits."""
    try:
        from axiom.permissions.sandbox import validate_workspace_path

        dest = validate_workspace_path(path, _context.workspace)
        await _client(_context).download(url, Path(dest))
    except Exception as exc:
        return ToolResult(
            tool_call_id="", name="web_download", content=f"Error: {exc}", is_error=True
        )
    return ToolResult(tool_call_id="", name="web_download", content=f"Downloaded {url} -> {path}")


def _strip_html(html: str) -> str:
    import re

    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def _parse_ddg(html: str, max_results: int) -> list[tuple[str, str]]:
    import re

    results: list[tuple[str, str]] = []
    links = re.findall(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
    for url, title in links[:max_results]:
        title = re.sub(r"<[^>]+>", "", title)
        results.append((title.strip(), url))
    if not results:
        links = re.findall(r'href="(https?://[^"]+)"[^>]*>(.*?)</a>', html)
        for url, title in links[:max_results]:
            title = re.sub(r"<[^>]+>", "", title).strip()
            if title and "duckduckgo" not in url:
                results.append((title, url))
    return results
