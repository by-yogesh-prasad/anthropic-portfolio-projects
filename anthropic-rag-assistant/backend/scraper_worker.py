"""Playwright scraper worker — executed as a subprocess per page.

Running Chromium in a separate process means an OOM kill only terminates
this child, leaving the uvicorn server process alive and healthy.

Usage:
    python scraper_worker.py <url>

Success: writes {"title": "...", "text": "..."} JSON to stdout, exits 0.
Failure: writes error message to stderr, exits 1.
"""

import json
import sys

from playwright.sync_api import sync_playwright

_BROWSER_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--no-first-run",
    "--mute-audio",
]


def scrape(url: str) -> dict:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=_BROWSER_ARGS)
        context = browser.new_context()
        try:
            page = context.new_page()

            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font", "stylesheet")
                else route.continue_(),
            )

            page.goto(url, wait_until="networkidle", timeout=60_000)

            try:
                page.wait_for_selector("h1", timeout=15_000)
            except Exception:
                pass

            title = page.title().split("|")[0].strip() or url

            content_text = ""
            for selector in ("main", "article", "[role='main']", "body"):
                try:
                    content_text = page.locator(selector).first.inner_text(timeout=5_000)
                    if content_text.strip():
                        break
                except Exception:
                    continue
        finally:
            context.close()
            browser.close()

    lines = [line.strip() for line in content_text.splitlines()]
    return {"title": title, "text": "\n".join(line for line in lines if line)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: scraper_worker.py <url>", file=sys.stderr)
        sys.exit(1)

    try:
        result = scrape(sys.argv[1])
        print(json.dumps(result))
    except Exception as exc:
        print(f"Scraper failed: {exc}", file=sys.stderr)
        sys.exit(1)
