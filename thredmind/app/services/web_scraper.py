import httpx
from bs4 import BeautifulSoup


def fetch_and_extract(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ThredMind/1.0; +https://thredmind.dev)"
    }
    try:
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
    except Exception as e:
        raise ValueError(f"Failed to fetch URL: {e}")

    html = response.text
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body")
    if not main:
        raise ValueError("Could not extract content from page")

    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    cleaned = "\n".join(lines)

    if len(cleaned) < 100:
        raise ValueError("Page content too short to analyze")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    return cleaned, title
