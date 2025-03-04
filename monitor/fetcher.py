# monitor/fetcher.py
import asyncio
from typing import Optional
import aiohttp
from playwright.async_api import async_playwright

DYNAMIC_KEYWORDS = ["react", "angular", "vue", "svelte"]

async def fetch_static(url: str, timeout: int = 10) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    return None
    except Exception:
        return None

async def fetch_dynamic(url: str, timeout: int = 20) -> Optional[str]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=timeout * 1000)
            await page.wait_for_load_state("networkidle")
            content = await page.content()
            await browser.close()
            return content
    except Exception:
        return None

def is_dynamic(content: str) -> bool:
    lower_content = content.lower()
    return any(keyword in lower_content for keyword in DYNAMIC_KEYWORDS)

async def fetch_page(url: str) -> Optional[str]:
    content = await fetch_static(url)
    if content is None:
        return None
    if is_dynamic(content):
        dynamic_content = await fetch_dynamic(url)
        return dynamic_content if dynamic_content is not None else content
    return content
