"""
多平台选题搜索 + AI 分析服务

数据来源：
- 小红书：通过 MCP search_feeds 真实搜索（关键词相关）
- 微博：ajax/side/hotSearch 接口（非官方，稳定）
- 百度：top.baidu.com/board 热搜榜（解析 HTML）
- 抖音：iesdouyin hotSearch 接口（非官方，可能不稳定）
- 所有平台失败时，自动降级为 AI 模拟
"""

import os
import re
import json
import time
import hashlib
import logging
import requests
from typing import List, Dict, Any, Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = os.getenv("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL    = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
XHS_MCP_URL       = os.getenv("XIAOHONGSHU_MCP_URL", "http://localhost:18060")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _call_deepseek(messages: list, temperature: float = 1.0) -> str:
    """走共享 LLM 层，带指数退避重试（选题搜索也在 Agent 工具链上）。"""
    from services.agent.llm import chat_text
    return chat_text(messages, temperature=temperature)


def _extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    for bracket in [("{", "}"), ("[", "]")]:
        start = text.find(bracket[0])
        end   = text.rfind(bracket[1]) + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except Exception:
                pass
    raise ValueError(f"无法解析 JSON: {text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# 小红书 — 通过 MCP 关键词搜索
# ─────────────────────────────────────────────────────────────────────────────

def search_xiaohongshu(keyword: str, limit: int = 10) -> List[Dict]:
    """通过 XHS MCP REST API (/api/v1/feeds/search) 搜索小红书真实笔记内容。"""
    import urllib.request as _urllib
    import urllib.error as _urlerr
    # 用 urllib + ProxyHandler({}) 完全绕过 Clash 等系统代理
    _opener = _urllib.build_opener(_urllib.ProxyHandler({}))
    try:
        body_bytes = json.dumps({"keyword": keyword}).encode()
        req = _urllib.Request(
            f"{XHS_MCP_URL}/api/v1/feeds/search",
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _opener.open(req, timeout=45) as r:
            resp_body = json.loads(r.read().decode())
            status = r.status

        if status == 200:
            feeds = (
                resp_body.get("data", {}).get("feeds")
                or resp_body.get("data", {}).get("notes")
                or resp_body.get("data", [])
                or []
            )
            if isinstance(feeds, dict):
                feeds = feeds.get("value") or feeds.get("_value") or []
            out = []
            for item in (feeds if isinstance(feeds, list) else [])[:limit]:
                card = item.get("noteCard", {})
                title = (card.get("displayTitle") or card.get("title")
                         or item.get("display_title") or item.get("title", ""))
                if not title:
                    continue
                interact = card.get("interactInfo", {})
                liked = interact.get("likedCount") or interact.get("liked_count") or ""
                note_id = item.get("id", "")
                xsec_token = item.get("xsecToken", "")
                out.append({
                    "title": title,
                    "hot_value": str(liked) if liked else "",
                    "source": "xiaohongshu",
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
                    "note_id": note_id,
                    "xsec_token": xsec_token,
                })
            if out:
                logger.info(f"[XHS搜索] 返回 {len(out)} 条")
                return out
        logger.warning(f"[XHS搜索] HTTP {status}")
    except Exception as e:
        logger.warning(f"[XHS搜索] 失败: {e}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 微博 — 关键词搜索（需要 Cookie）+ 热搜榜降级（无需登录）
# ─────────────────────────────────────────────────────────────────────────────

WEIBO_COOKIE = os.getenv("WEIBO_COOKIE", "")


def search_weibo(keyword: str, limit: int = 15) -> List[Dict]:
    """
    微博关键词搜索（.env 配置 WEIBO_COOKIE 后启用）。
    未配置时自动降级为热搜榜。
    """
    if not WEIBO_COOKIE:
        logger.info("[微博] 未配置 WEIBO_COOKIE，降级为热搜榜")
        return fetch_weibo_hot(limit)

    try:
        # s.weibo.com 搜索页（Cookie 后返回真实帖子 HTML）
        resp = requests.get(
            "https://s.weibo.com/weibo",
            params={"q": keyword, "typeall": "1", "suball": "1", "page": "1"},
            headers={
                "User-Agent": _DEFAULT_UA,
                "Referer": "https://weibo.com/",
                "Cookie": WEIBO_COOKIE,
            },
            timeout=12,
        )
        if resp.status_code == 200 and BS4_AVAILABLE:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("div.card-wrap[mid]")
            result = []
            for item in items[:limit]:
                text_el = item.select_one("p.txt") or item.select_one(".txt")
                if not text_el:
                    continue
                text = re.sub(r"<[^>]+>", "", text_el.get_text(separator=" ", strip=True))
                # 去掉"全文"等尾巴
                text = re.sub(r"\s*全文\s*$", "", text).strip()
                if not text:
                    continue
                # 点赞数
                like_el = item.select_one('[node-type="like_status"] em') or \
                          item.select_one(".woo-like-count")
                likes = like_el.get_text(strip=True) if like_el else "0"
                result.append({
                    "title": text[:80],
                    "hot_value": likes,
                    "source": "weibo",
                })
            if result:
                logger.info(f"[微博搜索] 关键词「{keyword}」返回 {len(result)} 条")
                return result
        elif resp.status_code == 302:
            logger.warning("[微博搜索] 被重定向 → Cookie 已失效，请重新获取")
    except Exception as e:
        logger.warning(f"[微博搜索] HTML 解析失败: {e}")

    return fetch_weibo_hot(limit)


def fetch_weibo_hot(limit: int = 15) -> List[Dict]:
    """微博实时热搜榜（无需登录，搜索失败时的降级方案）。"""
    try:
        resp = requests.get(
            "https://weibo.com/ajax/side/hotSearch",
            headers={
                "User-Agent": _MOBILE_UA,
                "Referer": "https://weibo.com/",
                "Accept": "application/json, text/plain, */*",
                "MWeibo-Pwa": "1",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("realtime", [])
            result = []
            for item in items:
                if item.get("is_ad") or item.get("category") == "广告":
                    continue
                title = item.get("note", "")
                if not title:
                    continue
                result.append({
                    "title": title,
                    "hot_value": str(item.get("num", "")),
                    "source": "weibo",
                    "url": f"https://s.weibo.com/weibo?q=%23{title}%23",
                })
                if len(result) >= limit:
                    break
            logger.info(f"[微博热搜] 抓取 {len(result)} 条")
            return result
    except Exception as e:
        logger.warning(f"[微博热搜] 失败: {e}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 百度 — 关键词内容搜索
# ─────────────────────────────────────────────────────────────────────────────

def search_baidu(keyword: str, limit: int = 15) -> List[Dict]:
    import html as _html
    try:
        resp = requests.get(
            "https://www.baidu.com/s",
            params={"ie": "utf-8", "wd": keyword, "cl": "3"},
            headers={"User-Agent": _DEFAULT_UA, "Accept-Language": "zh-CN,zh;q=0.9",
                     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                     "Referer": "https://www.baidu.com/"},
            timeout=12,
        )
        if resp.status_code == 200 and len(resp.text) > 50000:
            skip = ["淘宝", "京东", "拼多多", "广告", "百度图片", "百度百科",
                    "精选笔记", "视频大全", "百度知道", "天猫", "当当"]
            result: List[Dict] = []
            seen: set = set()

            if BS4_AVAILABLE:
                soup = BeautifulSoup(resp.text, "html.parser")
                for container in soup.select(".result.c-container, .result"):
                    h3 = container.select_one("h3")
                    if not h3: continue
                    a_tag = h3.find("a")
                    if not a_tag: continue
                    t = _html.unescape(re.sub(r"\s+", " ", a_tag.get_text())).strip(" -—·")
                    if len(t) < 6 or t in seen: continue
                    if any(k in t for k in skip): continue
                    seen.add(t)
                    url = a_tag.get("href", "") or f"https://www.baidu.com/s?wd={keyword}"
                    snippet_el = container.select_one(".c-abstract, [class*='abstract']")
                    snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""
                    result.append({"title": t, "hot_value": "", "source": "baidu",
                                   "url": url, "snippet": snippet})
                    if len(result) >= limit: break
            else:
                h3_pat = re.compile(r"<h3[^>]*>(.*?)</h3>", re.DOTALL)
                for m in h3_pat.finditer(resp.text):
                    h = m.group(1)
                    href_m = re.search(r'href="([^"]+)"', h)
                    url = href_m.group(1) if href_m else f"https://www.baidu.com/s?wd={keyword}"
                    t = _html.unescape(re.sub(r"<[^>]+>", "", h)).strip()
                    t = re.sub(r"[\s ]+", " ", t).strip(" -—·")
                    if len(t) < 6 or t in seen: continue
                    if any(k in t for k in skip): continue
                    seen.add(t)
                    result.append({"title": t, "hot_value": "", "source": "baidu",
                                   "url": url, "snippet": ""})
                    if len(result) >= limit: break

            if result:
                logger.info(f"[百度搜索] 抓取 {len(result)} 条")
                return result
    except Exception as e:
        logger.warning(f"[百度搜索] 失败: {e}")
    return []



def search_weixin(keyword: str, limit: int = 12) -> List[Dict]:
    import html as _html
    try:
        resp = requests.get(
            "https://weixin.sogou.com/weixin",
            params={"type": "2", "query": keyword, "ie": "utf8"},
            headers={"User-Agent": _DEFAULT_UA, "Accept-Language": "zh-CN,zh;q=0.9",
                     "Referer": "https://weixin.sogou.com/"},
            timeout=12,
        )
        if resp.status_code == 200 and len(resp.text) > 5000:
            result: List[Dict] = []
            seen: set = set()

            if BS4_AVAILABLE:
                soup = BeautifulSoup(resp.text, "html.parser")
                for txt_box in soup.select("div.txt-box"):
                    h3 = txt_box.select_one("h3 a")
                    if not h3: continue
                    t = _html.unescape(re.sub(r"\s+", " ", h3.get_text())).strip()
                    if len(t) < 6 or t in seen: continue
                    seen.add(t)
                    href = h3.get("href", "")
                    url = href if href.startswith("http") else "https://weixin.sogou.com" + href
                    snippet_el = txt_box.select_one("p.txt-info, .txt-info")
                    snippet = snippet_el.get_text(strip=True)[:200] if snippet_el else ""
                    account_el = txt_box.select_one("div.s-p, .s-p")
                    account = account_el.get_text(strip=True) if account_el else ""
                    result.append({
                        "title": t, "hot_value": "", "source": "weixin",
                        "url": url, "snippet": snippet, "author": account,
                    })
                    if len(result) >= limit: break
            else:
                pat = re.compile(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
                for m in pat.finditer(resp.text):
                    href, raw = m.group(1), m.group(2)
                    t = _html.unescape(re.sub(r"<[^>]+>", "", raw))
                    t = re.sub(r"\s+", " ", t).strip()
                    if len(t) < 6 or t in seen: continue
                    seen.add(t)
                    result.append({
                        "title": t, "hot_value": "", "source": "weixin",
                        "url": href if href.startswith("http") else "https://weixin.sogou.com" + href,
                        "snippet": "", "author": "",
                    })
                    if len(result) >= limit: break

            if result:
                logger.info(f"[微信文章搜索] 抓取 {len(result)} 条")
                return result
    except Exception as e:
        logger.warning(f"[微信文章搜索] 失败: {e}")
    return []



def fetch_baidu_hot(limit: int = 15) -> List[Dict]:
    return []  # 已废弃



# ─────────────────────────────────────────────────────────────────────────────
# 抖音 — 关键词搜索（a_bogus 签名 + Cookie）+ 热榜降级
# ─────────────────────────────────────────────────────────────────────────────

DOUYIN_COOKIE = os.getenv("DOUYIN_COOKIE", "")

# 懒加载 JS 签名上下文（进程内只初始化一次）
_douyin_js_ctx = None

def _get_douyin_ctx():
    global _douyin_js_ctx
    if _douyin_js_ctx is None:
        try:
            import execjs
            js_path = os.path.join(os.path.dirname(__file__), "douyin_sign.js")
            with open(js_path, "r", encoding="utf-8") as f:
                _douyin_js_ctx = execjs.compile(f.read())
            logger.info("[抖音签名] JS 上下文初始化成功")
        except Exception as e:
            logger.warning(f"[抖音签名] 初始化失败: {e}")
    return _douyin_js_ctx


def _douyin_sign(params_str: str, ua: str) -> str:
    """调用 JS 生成 a_bogus 签名。"""
    ctx = _get_douyin_ctx()
    if ctx is None:
        return ""
    try:
        return ctx.call("sign_datail", params_str, ua)
    except Exception as e:
        logger.warning(f"[抖音签名] sign_datail 失败: {e}")
        return ""


_DOUYIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)


def _random_ms_token(length: int = 120) -> str:
    """生成随机 msToken（erma0/douyin 验证：120 字符，无需从浏览器获取）。"""
    import random, string
    chars = string.ascii_letters + string.digits + "="
    return "".join(random.choices(chars, k=length))


def _random_webid() -> str:
    """生成随机 webId（19 位数字）。"""
    import random
    return str(random.randint(1_000_000_000_000_000_000, 9_999_999_999_999_999_999))


# 通用基础参数（参考 erma0/douyin）
_DOUYIN_BASE_PARAMS: Dict[str, Any] = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "190600",
    "version_name": "19.6.0",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "132.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": "8",
    "device_memory": "8",
    "platform": "PC",
    "effective_type": "4g",
    "round_trip_time": "200",
}


def search_douyin(
    keyword: str,
    limit: int = 15,
    sort_type: int = 1,      # 0=综合 1=最多点赞 2=最新
    publish_time: int = 0,   # 0=不限 1=24h 7=一周 180=半年
) -> List[Dict]:
    """
    抖音关键词搜索（需要 .env 配置 DOUYIN_COOKIE）。
    未配置时自动降级为热搜榜。
    """
    if not DOUYIN_COOKIE:
        logger.info("[抖音] 未配置 DOUYIN_COOKIE，降级为热搜榜")
        return fetch_douyin_hot(limit)

    ctx = _get_douyin_ctx()
    if ctx is None:
        logger.warning("[抖音] JS 签名不可用，降级为热搜榜")
        return fetch_douyin_hot(limit)

    try:
        import urllib.parse

        filter_selected = json.dumps({
            "sort_type": str(sort_type),
            "publish_time": str(publish_time),
        })

        params: Dict[str, Any] = {
            **_DOUYIN_BASE_PARAMS,
            "keyword": keyword,
            "search_channel": "aweme_general",
            "filter_selected": filter_selected,
            "enable_history": "1",
            "search_id": "",
            "query_correct_type": "1",
            "is_filter_search": "0",
            "offset": "0",
            "count": str(limit),
            "from_group_id": "",
            "msToken": _random_ms_token(),
            "webid": _random_webid(),
        }

        # 构造 query string 用于签名
        qs = "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='')}"
            for k, v in params.items()
        )
        a_bogus = _douyin_sign(qs, _DOUYIN_UA)
        if a_bogus:
            params["a_bogus"] = a_bogus

        resp = requests.get(
            "https://www.douyin.com/aweme/v1/web/general/search/single/",
            params=params,
            headers={
                "User-Agent": _DOUYIN_UA,
                "Referer": "https://www.douyin.com/",
                "Cookie": DOUYIN_COOKIE,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            timeout=15,
        )

        if resp.status_code == 200:
            data = resp.json()
            # 综合搜索返回多种类型，视频在 data 字段
            raw_list = (
                data.get("data", [])
                or data.get("aweme_list", [])
                or []
            )
            result = []
            for item in raw_list:
                # 综合搜索每项结构：{"type": 1, "aweme": {...}}
                aweme = item.get("aweme") or item
                desc = aweme.get("desc", "")
                if not desc:
                    continue
                stats = aweme.get("statistics", {})
                result.append({
                    "title": desc[:80],
                    "hot_value": str(stats.get("digg_count", 0)),
                    "source": "douyin",
                    "url": f"https://www.douyin.com/video/{aweme.get('aweme_id', '')}",
                    "play": stats.get("play_count", 0),
                    "like": stats.get("digg_count", 0),
                })
                if len(result) >= limit:
                    break

            if result:
                logger.info(f"[抖音搜索] 关键词「{keyword}」返回 {len(result)} 条")
                return result

            logger.warning(f"[抖音搜索] 返回空结果，status={data.get('status_code')}")
        else:
            logger.warning(f"[抖音搜索] HTTP {resp.status_code}")

    except Exception as e:
        logger.warning(f"[抖音搜索] 失败: {e}")

    logger.info("[抖音搜索] 降级为热搜榜")
    return fetch_douyin_hot(limit)


def fetch_douyin_hot(limit: int = 15) -> List[Dict]:
    """
    抓取抖音热搜榜（非官方接口）。
    主接口失败时尝试备用接口，再失败则返回空列表。
    """
    # 主接口
    endpoints = [
        "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/",
        "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/aweme/",
    ]
    headers = {
        "User-Agent": _MOBILE_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
    }

    for url in endpoints:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # 格式：{"word_list": [{"word": "xxx", "hot_value": 123, ...}]}
                items = data.get("word_list") or data.get("aweme_list") or []
                result = [
                    {
                        "title": item.get("word") or item.get("aweme_info", {}).get("desc", ""),
                        "hot_value": str(item.get("hot_value", "")),
                        "source": "douyin",
                        "url": f"https://www.douyin.com/search/{item.get('word', '')}",
                    }
                    for item in items[:limit]
                    if item.get("word") or item.get("aweme_info", {}).get("desc")
                ]
                if result:
                    logger.info(f"[抖音热榜] 抓取 {len(result)} 条 via {url}")
                    return result
        except Exception as e:
            logger.warning(f"[抖音热榜] {url} 失败: {e}")
            continue

    logger.warning("[抖音热榜] 所有接口失败，返回空列表")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# B站 — 关键词搜索（WBI 签名，无需登录）
# ─────────────────────────────────────────────────────────────────────────────

_bili_mixin_key_cache: Dict[str, Any] = {}  # {key, expires_at}

_WBI_ENC = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,
            33,9,42,19,29,28,14,39,12,38,41,13]

def _get_bili_mixin_key() -> str:
    """获取并缓存 B站 WBI 混淆密钥（5 分钟有效）。"""
    now = time.time()
    if _bili_mixin_key_cache.get("expires_at", 0) > now:
        return _bili_mixin_key_cache["key"]
    resp = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": _DEFAULT_UA},
        timeout=10,
    )
    wbi = resp.json()["data"]["wbi_img"]
    img_key = wbi["img_url"].rsplit("/", 1)[1].split(".")[0]
    sub_key = wbi["sub_url"].rsplit("/", 1)[1].split(".")[0]
    raw = img_key + sub_key
    mixin_key = "".join(raw[i] for i in _WBI_ENC)[:32]
    _bili_mixin_key_cache.update({"key": mixin_key, "expires_at": now + 300})
    return mixin_key


def search_bilibili(keyword: str, limit: int = 10) -> List[Dict]:
    """B站关键词搜索（按播放量排序），返回最热门视频信息。"""
    try:
        mixin_key = _get_bili_mixin_key()
        params: Dict[str, Any] = {
            "search_type": "video",
            "keyword": keyword,
            "order": "click",   # 按播放量排序
            "duration": 0,
            "page": 1,
            "wts": int(time.time()),
        }
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        params["w_rid"] = hashlib.md5((qs + mixin_key).encode()).hexdigest()

        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params=params,
            headers={"User-Agent": _DEFAULT_UA, "Referer": "https://www.bilibili.com"},
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("result", [])
            result = []
            for item in items[:limit]:
                title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                if not title:
                    continue
                bvid = item.get("bvid", "")
                result.append({
                    "title": title,
                    "hot_value": str(item.get("play", 0)),
                    "source": "bilibili",
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "bvid": bvid,
                    "author": item.get("author", ""),
                    "cover": item.get("pic", ""),
                })
            logger.info(f"[B站搜索] 关键词「{keyword}」返回 {len(result)} 条")
            return result
    except Exception as e:
        logger.warning(f"[B站搜索] 失败: {e}")
    return []


# 是否启用抖音关键词搜索的 Playwright 方案（较慢，默认关闭）
DOUYIN_USE_PLAYWRIGHT = os.getenv("DOUYIN_USE_PLAYWRIGHT", "false").lower() == "true"


def _search_douyin_with_fallback(keyword: str, limit: int = 15) -> List[Dict]:
    """
    抖音关键词搜索。抖音 Web 有 verify_check 设备指纹验证，
    纯 HTTP 请求难以稳定绕过，因此默认降级到热搜榜。
    如需关键词搜索，设置 DOUYIN_USE_PLAYWRIGHT=true（较慢）。
    """
    if DOUYIN_USE_PLAYWRIGHT:
        try:
            from services.douyin_search_playwright import search_douyin_playwright
            results = search_douyin_playwright(keyword, limit)
            if results:
                return results
        except Exception as e:
            logger.warning(f"[抖音] Playwright 失败: {e}")

    # 默认：直接用热搜榜（稳定、快速）
    return fetch_douyin_hot(limit)


# ─────────────────────────────────────────────────────────────────────────────
# 降级：AI 模拟单平台趋势（任何平台抓取失败时调用）
# ─────────────────────────────────────────────────────────────────────────────

def _simulate_platform_trends(keyword: str, platform: str, theme: str) -> List[Dict]:
    """当真实抓取失败时，用 AI 模拟该平台的趋势话题。"""
    desc = {
        "weibo":    "微博（社交热点，娱乐/情感/社会事件居多）",
        "baidu":    "百度（搜索引擎，用户在搜索实用攻略和解答）",
        "douyin":   "抖音（短视频，猎奇/情绪化/反转内容更受欢迎）",
    }.get(platform, platform)

    prompt = f"""账号主题：{theme}
关键词：{keyword}
目标平台：{desc}

模拟该平台当前与关键词相关的 5 个热点话题方向。
返回 JSON 数组，每项：{{"title": "话题", "hot_value": "热度描述", "source": "{platform}"}}"""

    try:
        raw = _call_deepseek([{"role": "user", "content": prompt}], temperature=1.1)
        items = _extract_json(raw)
        if isinstance(items, list):
            return items[:5]
    except Exception as e:
        logger.warning(f"[AI模拟-{platform}] 失败: {e}")
    return []


# ─────────────────────────────────────────────────────────────────────────────
# AI 综合分析 → 生成选题建议
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_and_suggest_topics(
    keyword: str,
    theme: str,
    target_audience: str,
    requirements: List[str],
    platforms_data: Dict[str, List[Dict]],
) -> List[Dict]:
    """
    把多平台热搜数据交给 AI，针对账号主题生成 8 个可执行的选题建议。
    """
    # 组装各平台数据摘要
    summary_parts = []
    for platform, items in platforms_data.items():
        if not items:
            continue
        titles = [item.get("title", "") for item in items if item.get("title")][:8]
        if titles:
            platform_label = {
                "xiaohongshu": "小红书",
                "bilibili":    "B站视频",
                "weibo":       "微博热搜",
                "baidu":       "百度热搜",
                "douyin":      "抖音热榜",
            }.get(platform, platform)
            summary_parts.append(f"【{platform_label}】" + " | ".join(titles))

    platforms_summary = "\n".join(summary_parts) if summary_parts else "（暂无平台数据）"

    req_str = ""
    if requirements:
        req_str = "\n\n【账号内容要求（必须遵守）】\n" + "\n".join(f"- {r}" for r in requirements)

    prompt = f"""你是专业的小红书内容策划师。

账号主题：{theme}
目标受众：{target_audience or "未指定"}
搜索关键词：{keyword}{req_str}

以下是今天各平台的热点数据：
{platforms_summary}

任务：结合账号主题和平台热点，生成 8 个可以直接去做的选题建议。

要求：
1. 每个选题必须与账号主题强相关，不能偏题
2. 标题要像真实会爆的小红书帖子标题（具体、有吸引力）
3. 切入角度一句话，说清楚这篇帖子从哪个视角来写
4. hot_score 是 1-5 的整数（结合平台热度和主题契合度综合评分）
5. 标注选题灵感来自哪个平台（没有对应平台热点的写 "ai"）

返回严格 JSON 数组：
[
  {{
    "title": "选题标题（像真实帖子标题）",
    "angle": "内容切入角度（一句话）",
    "source": "xiaohongshu 或 weibo 或 baidu 或 douyin 或 ai",
    "hot_score": 4
  }}
]"""

    raw = _call_deepseek([{"role": "user", "content": prompt}], temperature=1.0)
    items = _extract_json(raw)
    if isinstance(items, list):
        return items[:10]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────────────────

def search_topics(
    keyword: str,
    theme: str,
    target_audience: str = "",
    requirements: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    meta: Optional[Dict] = None,
) -> List[Dict]:
    """
    多平台搜索热点 + AI 综合分析，返回选题建议列表。

    参数：
        keyword    -- 搜索关键词（用于 XHS 精确搜索，以及在 AI 分析中的主题锚点）
        theme      -- 账号主题（AI 据此筛选相关选题）
        platforms  -- 要搜索的平台，默认全部
        meta       -- 可选出参 dict：调用方传入空 dict，函数会写入
                      meta["simulated"]（真实抓取失败、降级为 AI 模拟的平台列表）和
                      meta["unavailable"]（连 AI 模拟也失败、完全无数据的平台列表），
                      供调用方向用户说明兜底情况
    """
    if platforms is None:
        platforms = ["xiaohongshu", "bilibili", "weibo", "baidu", "douyin"]

    requirements = requirements or []
    platforms_data: Dict[str, List[Dict]] = {}

    fetch_map = {
        "xiaohongshu": lambda: search_xiaohongshu(keyword, limit=8),
        "bilibili":    lambda: search_bilibili(keyword, limit=10),
        "weibo":       lambda: search_weibo(keyword, limit=15),
        "baidu":       lambda: fetch_baidu_hot(limit=15),
        "douyin":      lambda: _search_douyin_with_fallback(keyword, limit=15),
    }

    for platform in platforms:
        fetcher = fetch_map.get(platform)
        if fetcher is None:
            continue
        data = fetcher()
        if data:
            platforms_data[platform] = data
        else:
            # 真实抓取失败 → AI 模拟降级
            logger.info(f"[TopicSearch] {platform} 真实抓取为空，降级为 AI 模拟")
            simulated = _simulate_platform_trends(keyword, platform, theme)
            if simulated:
                platforms_data[platform] = simulated
                if meta is not None:
                    meta.setdefault("simulated", []).append(platform)
            else:
                if meta is not None:
                    meta.setdefault("unavailable", []).append(platform)

    return _analyze_and_suggest_topics(
        keyword=keyword,
        theme=theme,
        target_audience=target_audience,
        requirements=requirements,
        platforms_data=platforms_data,
    )
