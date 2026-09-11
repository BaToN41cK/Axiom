"""Web search and research tools for AXIOM."""

from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.config import config


class WebSearchTool:
    """Web search using DuckDuckGo."""

    def __init__(self):
        self._results: list[dict] = []

    @property
    def results(self) -> list[dict]:
        return self._results

    async def search(self, query: str, max_results: int = 0) -> list[dict]:
        """Search the web using DuckDuckGo."""
        if not config.web_enabled:
            return []

        max_results = max_results or config.web_search_results

        try:
            # Prefer the current `ddgs` package; fall back to the legacy
            # `duckduckgo_search` name if `ddgs` is not installed.
            try:
                from ddgs import DDGS  # type: ignore[import-untyped]
            except ImportError:
                from duckduckgo_search import DDGS  # type: ignore[import-untyped]

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            self._results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw_results
                if r.get("title") and r.get("href")
            ]

            return self._results

        except ImportError:
            return []
        except Exception:
            return []

    async def fetch_page(self, url: str, max_chars: int = 5000) -> dict:
        """Fetch and extract text content from a URL."""
        if not config.web_enabled:
            return {"url": url, "title": "", "text": "", "success": False}

        try:
            async with httpx.AsyncClient(
                timeout=config.web_fetch_timeout,
                follow_redirects=True,
                headers={"User-Agent": "AXIOM/0.1 (Local AI Terminal)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")

                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                title = ""
                if soup.title:
                    title = soup.title.get_text(strip=True)
                else:
                    h1 = soup.find("h1")
                    if h1:
                        title = h1.get_text(strip=True)

                text = soup.get_text(separator="\n", strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = "\n".join(lines)

                if len(text) > max_chars:
                    text = text[:max_chars] + "\n... [truncated]"

                return {"url": url, "title": title, "text": text, "success": True}

        except httpx.TimeoutException:
            return {"url": url, "title": "", "text": "", "success": False, "error": "timeout"}
        except httpx.HTTPStatusError as e:
            return {"url": url, "title": "", "text": "", "success": False, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            return {"url": url, "title": "", "text": "", "success": False, "error": str(e)}

    async def research(self, query: str, max_pages: int = 3) -> dict:
        """Perform web research: search + fetch top results."""
        search_results = await self.search(query)
        if not search_results:
            return {"query": query, "results": [], "pages": [], "sources": []}

        pages = []
        sources = []
        for result in search_results[:max_pages]:
            page = await self.fetch_page(result["url"])
            if page["success"]:
                pages.append(page)
                sources.append({
                    "title": page["title"] or result["title"],
                    "url": result["url"],
                    "snippet": result.get("snippet", ""),
                })

        return {"query": query, "results": search_results, "pages": pages, "sources": sources}


def get_tool_definitions() -> list[dict]:
    """Get tool definitions for Ollama function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for current information, news, documentation, or facts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch and extract text content from a specific URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch",
                        }
                    },
                    "required": ["url"],
                },
            },
        },
    ]


async def execute_tool(name: str, arguments: dict, web_tool: WebSearchTool) -> dict:
    """Execute a tool by name with given arguments."""
    if name == "web_search":
        query = arguments.get("query", "")
        results = await web_tool.search(query)
        return {"tool": "web_search", "query": query, "results": results, "count": len(results)}

    elif name == "web_fetch":
        url = arguments.get("url", "")
        page = await web_tool.fetch_page(url)
        return {"tool": "web_fetch", "url": url, "page": page, "success": page.get("success", False)}

    return {"tool": name, "error": f"Unknown tool: {name}"}
