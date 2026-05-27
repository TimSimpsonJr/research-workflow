"""fetch_playwright.py — JS-heavy page extraction fallback.

Used by fetch_and_clean.fetch_url() as a fallback when Jina and Wayback both fail.
Returns (content, title) — same shape as fetch_via_jina and fetch_via_wayback.
"""

def fetch_via_playwright(url: str, timeout_ms: int = 15000) -> tuple[str, str]:
    """Fetch a URL with Playwright. Returns (content, title).

    Raises RuntimeError if Playwright isn't installed or the page fails to load.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright not available") from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            content = page.content()
            title = page.title() or ""
            browser.close()
            return content, title
    except Exception as e:
        raise RuntimeError(f"playwright fetch failed: {e}") from e
