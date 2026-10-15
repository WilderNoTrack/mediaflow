"""
测试小红书笔记详情解析（先搜索获取 xsec_token，再查详情）
用法: python test_xhs_detail.py [关键词]
"""
import sys
import json
import urllib.request
import urllib.error

XHS_MCP_URL = "http://localhost:18060"
KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "贵州冰浆"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def post(path, data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{XHS_MCP_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
    except Exception as e:
        return None, str(e)

# ── Step 1: 搜索，拿第一条结果的 note_id + xsec_token ──
print(f"[1] 搜索「{KEYWORD}」...")
code, body = post("/api/v1/feeds/search", {"keyword": KEYWORD})
print(f"    HTTP {code}")
if code != 200:
    print(f"    错误: {body}")
    exit(1)

feeds = body.get("data", {}).get("feeds", [])
if not feeds:
    print("    没有搜索结果")
    exit(1)

first = feeds[0]
note_id    = first.get("id", "")
xsec_token = first.get("xsecToken", "")
title      = first.get("noteCard", {}).get("displayTitle", "")
print(f"    第一条: {title}")
print(f"    note_id={note_id}")
print(f"    xsec_token={xsec_token[:30] if xsec_token else '(空！)'}")

if not xsec_token:
    print("\n[!] xsec_token 为空，打印原始第一条 feed 结构：")
    print(json.dumps(first, ensure_ascii=False, indent=2)[:1000])
    exit(1)

# ── Step 2: 查详情 ──
print(f"\n[2] 查询详情（note_id={note_id}）...")
code, body = post("/api/v1/feeds/detail", {
    "feed_id": note_id,
    "xsec_token": xsec_token,
    "load_all_comments": False,
})
print(f"    HTTP {code}")

if code != 200:
    print(f"    错误: {json.dumps(body, ensure_ascii=False)[:300]}")
    exit(1)

data = body.get("data", {})
note = data.get("note", {})
print(f"\n=== note keys: {list(note.keys())}")
print(f"标题:     {note.get('title','(无)')}")
print(f"正文长度: {len(note.get('desc',''))}")
print(f"正文:     {note.get('desc','(无)')[:300]}")
print(f"作者:     {note.get('user',{}).get('nickname','(无)')}")
print(f"图片数:   {len(note.get('imageList',[]))}")
comments = data.get("comments", {})
clist = comments.get("list", []) if isinstance(comments, dict) else []
print(f"评论数:   {len(clist)}")
if clist:
    print(f"第一条评论: {clist[0].get('content','')}")

print("\n=== 完整原始 data（前3000字）===")
print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
