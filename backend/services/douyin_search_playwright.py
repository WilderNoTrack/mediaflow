"""
抖音关键词搜索（Playwright 方案）

通过真实浏览器访问搜索页，注入用户 Cookie，
让 Douyin JS 自动生成 msToken，绕过 verify_check。
"""
import os
import json
import asyncio
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

DOUYIN_COOKIE = os.getenv("DOUYIN_COOKIE", "")


def cookie_str_to_list(cookie_str: str) -> List[Dict]:
    """把 Cookie 字符串转成 Playwright 需要的格式。"""
    cookies = []
    for part in cookie_str.split("; "):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".douyin.com",
            "path": "/",
        })
    return cookies


async def _search_async(keyword: str, limit: int = 15) -> List[Dict]:
    from playwright.async_api import async_playwright

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        # 注入 Cookie
        if DOUYIN_COOKIE:
            await context.add_cookies(cookie_str_to_list(DOUYIN_COOKIE))

        # 反检测
        await context.add_init_script(
            "Object.defineProperties(navigator, {webdriver: {get: () => false}});"
        )

        page = await context.new_page()

        # 监听网络请求，捕获搜索 API 响应
        captured = []

        async def handle_response(response):
            if "search" in response.url and "douyin.com" in response.url:
                try:
                    body = await response.text()
                    data = json.loads(body)
                    if data.get("status_code") == 0 and data.get("data"):
                        captured.extend(data["data"])
                except Exception:
                    pass

        page.on("response", handle_response)

        import urllib.parse
        search_url = f"https://www.douyin.com/search/{urllib.parse.quote(keyword)}"
        logger.info(f"[抖音搜索-PW] 访问 {search_url}")
        await page.goto(search_url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(3000)

        # 解析捕获到的数据
        for item in captured[:limit]:
            aweme = item.get("aweme") or item
            if not isinstance(aweme, dict):
                continue
            desc = aweme.get("desc", "")
            if not desc:
                continue
            stats = aweme.get("statistics", {})
            results.append({
                "title": desc[:80],
                "hot_value": str(stats.get("digg_count", 0)),
                "source": "douyin",
                "play": stats.get("play_count", 0),
                "like": stats.get("digg_count", 0),
            })

        # 如果 API 拦截失败，尝试从 DOM 提取
        if not results:
            try:
                items = await page.query_selector_all("[data-e2e='search-video-card']")
                for item in items[:limit]:
                    title_el = await item.query_selector("[data-e2e='search-video-desc']")
                    if title_el:
                        title = await title_el.inner_text()
                        if title:
                            results.append({"title": title[:80], "hot_value": "0", "source": "douyin"})
            except Exception as e:
                logger.warning(f"[抖音搜索-PW] DOM 提取失败: {e}")

        await browser.close()

    logger.info(f"[抖音搜索-PW] 关键词「{keyword}」返回 {len(results)} 条")
    return results


def search_douyin_playwright(keyword: str, limit: int = 15) -> List[Dict]:
    """同步接口：用 Playwright 搜索抖音。"""
    if not DOUYIN_COOKIE:
        logger.info("[抖音搜索-PW] 未配置 DOUYIN_COOKIE")
        return []
    try:
        return asyncio.run(_search_async(keyword, limit))
    except Exception as e:
        logger.warning(f"[抖音搜索-PW] 失败: {e}")
        return []
