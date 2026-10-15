"""
小红书 MCP 搜索功能测试脚本（使用内置 urllib，无需安装 requests）
用法: python test_xhs_search.py [关键词]
"""
import sys
import json
import urllib.request
import urllib.error

XHS_MCP_URL = "http://localhost:18060"
KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "保山冰牛奶"


# 绕过系统代理（Clash/V2Ray 等代理软件会拦截 localhost 请求返回 502）
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(path, timeout=10):
    try:
        with _opener.open(f"{XHS_MCP_URL}{path}", timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return None, str(e)


def http_post(path, data: dict, timeout=60):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{XHS_MCP_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return None, str(e)


def check_health():
    import time
    print(f"[1] 检查 MCP 服务状态 ({XHS_MCP_URL}) ...")
    for attempt in range(40):  # 最长等 200 秒（Chrome 启动需要 2-3 分钟）
        code, text = http_get("/health")
        if code == 200:
            print(f"    HTTP {code}: {text[:200]}")
            return True
        if code is None:
            print(f"    连接失败: {text}")
        else:
            elapsed = attempt * 5
            print(f"    HTTP {code}，Chrome 启动中... 已等 {elapsed}s ({attempt+1}/40)")
        time.sleep(5)
    return False


def check_login():
    print("[2] 检查登录状态 ...")
    code, text = http_get("/api/v1/login/status", timeout=15)
    if code is None:
        print(f"    请求失败: {text}")
        return False
    print(f"    HTTP {code}: {text[:300]}")
    try:
        data = json.loads(text)
        logged_in = data.get("data", {}).get("is_logged_in") or data.get("data", {}).get("loggedIn")
        print(f"    已登录: {logged_in}")
        return bool(logged_in)
    except Exception:
        return False


def search(keyword: str):
    print(f"[3] 搜索关键词: 「{keyword}」(超时60秒，小红书需要中国网络)...")
    code, text = http_post("/api/v1/feeds/search", {"keyword": keyword}, timeout=60)
    if code is None:
        print(f"    请求异常: {text}")
        return
    print(f"    HTTP {code}  响应大小: {len(text)} bytes")
    if code != 200:
        print(f"    错误响应: {text[:500]}")
        return

    try:
        body = json.loads(text)
    except Exception as e:
        print(f"    JSON解析失败: {e}\n    原始响应: {text[:500]}")
        return

    print(f"    原始 JSON 顶层 keys: {list(body.keys())}")
    data = body.get("data", {})
    if isinstance(data, dict):
        print(f"    data 层 keys: {list(data.keys())}")

    feeds = (
        data.get("feeds")
        or data.get("notes")
        or (data if isinstance(data, list) else [])
    )
    if isinstance(feeds, dict):
        feeds = feeds.get("value") or feeds.get("_value") or []

    if not feeds:
        print("\n    [!] 未解析到 feeds，完整响应:")
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
        return

    print(f"\n    成功获取 {len(feeds)} 条结果:")
    for i, item in enumerate(feeds[:10], 1):
        card = item.get("noteCard", {})
        title = (
            card.get("displayTitle")
            or card.get("title")
            or item.get("display_title")
            or item.get("title", "(无标题)")
        )
        interact = card.get("interactInfo", {})
        liked = interact.get("likedCount") or interact.get("liked_count") or "-"
        note_id = item.get("id", "")
        url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
        print(f"    {i:2}. {title}")
        print(f"        点赞: {liked}  链接: {url}")


if __name__ == "__main__":
    print("=" * 60)
    print("小红书 MCP 搜索测试")
    print("=" * 60)

    if not check_health():
        print("\n[!] MCP 服务未运行，请先在另一个终端启动：")
        print('    .\\xiaohongshu-mcp.exe -port ":18060" -bin "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')
        sys.exit(1)

    logged_in = check_login()
    if not logged_in:
        print("\n[!] 未登录，请先运行登录工具：")
        print('    .\\xiaohongshu-login.exe -bin "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')
        print("    扫码登录后，cookies 保存至 ./data/cookies.json，再重新启动 MCP 服务\n")

    search(KEYWORD)
    print("\n" + "=" * 60)
