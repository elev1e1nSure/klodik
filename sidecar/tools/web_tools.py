"""Web scraping and search tools."""

from .base import tool, ToolError
from .registry import registry

try:
    import requests
    from bs4 import BeautifulSoup
    from requests.exceptions import RequestException
except ImportError:
    requests = None  # type: ignore[assignment]
    BeautifulSoup = None  # type: ignore[assignment,misc]
    RequestException = Exception  # type: ignore[misc]


@tool(
    "google",
    "Search Google and return top 5 result titles+urls",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
)
def google(*, query: str) -> str:
    if requests is None:
        raise ToolError("requests not installed")
    if BeautifulSoup is None:
        raise ToolError("beautifulsoup4 not installed")

    try:
        response = requests.get(
            "https://www.google.com/search",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[str] = []
        for g in soup.select("div.g")[:5]:
            title = g.select_one("h3")
            link = g.select_one("a")
            if title and link:
                results.append(f"{title.get_text()}: {link.get('href', '')}")
        return "\n".join(results) if results else "No results"
    except RequestException as e:
        raise ToolError(f"Network error: {e}")
    except Exception as e:
        raise ToolError(f"Search failed: {e}")


@tool(
    "read_url",
    "Fetch a webpage and return readable text",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
        "required": ["url"],
    },
)
def read_url(*, url: str) -> str:
    if requests is None:
        raise ToolError("requests not installed")
    if BeautifulSoup is None:
        raise ToolError("beautifulsoup4 not installed")

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:3000]
    except RequestException as e:
        raise ToolError(f"Network error: {e}")
    except Exception as e:
        raise ToolError(f"Fetch failed: {e}")


# Auto-register on import
registry.register(google)
registry.register(read_url)
