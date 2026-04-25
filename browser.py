import re
import urllib.parse
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, Browser as PwBrowser, Playwright


class Browser:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: PwBrowser | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_page(self):
        assert self._browser, "Browser not started"
        ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        return await ctx.new_page()

    async def search_web(self, query: str) -> str:
        encoded = urllib.parse.quote_plus(query)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with httpx.AsyncClient(
                timeout=12, headers=headers, follow_redirects=True
            ) as client:
                resp = await client.get(
                    f"https://html.duckduckgo.com/html/?q={encoded}"
                )
            html = resp.text

            # 제목: <a class="result__a" ...>Title</a>
            titles = re.findall(
                r'class="result__a"[^>]*>([^<]{3,200})</a>', html
            )
            # 스니펫: class 에 result__snippet 이 포함된 태그 내용
            snippets = re.findall(
                r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
                html, re.DOTALL
            )

            output: list[str] = []
            for title, snippet in zip(titles[:3], snippets[:3]):
                title = re.sub(r"<[^>]+>", "", title).strip()
                snippet = re.sub(r"<[^>]+>", "", snippet).strip()
                if title:
                    output.append(f"- {title}: {snippet}")

            return "\n".join(output)[:800] if output else "No results found."
        except Exception as exc:
            return f"Search failed: {exc}"

    async def visit_url(self, url: str) -> str:
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await page.evaluate(
                "document.querySelectorAll('script,style,nav,footer,header').forEach(e=>e.remove())"
            )
            text = await page.inner_text("body")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            return text[:1000]
        except Exception as exc:
            return f"Could not visit URL: {exc}"
        finally:
            await page.context.close()

    async def take_screenshot(self, url: str) -> str:
        page = await self._new_page()
        path = "data/screenshot.png"
        Path("data").mkdir(exist_ok=True)
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await page.screenshot(path=path, full_page=False)
            return str(Path(path).resolve())
        except Exception as exc:
            return f"Screenshot failed: {exc}"
        finally:
            await page.context.close()
