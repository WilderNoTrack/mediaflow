"""各平台搜索凭据：环境变量打底，界面里填的值存在数据目录 credentials.json，优先级更高。

只存在本机；接口只返回「配没配」，从不把值回传给前端。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from mediaflow.config import get_settings


@dataclass(frozen=True)
class CredSpec:
    key: str          # 存储键，同时也是 Settings 字段名
    platform: str     # 对应的来源 name
    label: str
    kind: str         # "key" | "cookie"
    help: str
    url: str
    hidden: bool = False  # 内部维护的值（如刷新口令），不在界面上展示


SPECS: list[CredSpec] = [
    CredSpec("xhs_cookie", "xiaohongshu", "小红书登录", "cookie",
             "小红书搜索必须登录。推荐点「扫码登录」，用小红书 App 扫码（建议用小号，主号频繁搜索可能被限流）；"
             "如果扫码后弹「安全验证」或登不上，就在已登录的浏览器里 F12 → 网络 → 任一 edith.xiaohongshu.com 请求，"
             "复制请求头里的整段 Cookie 粘贴进来（需包含 a1 和 web_session）。",
             "https://www.xiaohongshu.com/"),
    CredSpec("zhihu_access_secret", "zhihu", "知乎开放平台 Access Secret", "key",
             "知乎官方搜索接口。到知乎数据开放平台登录 → 创建应用 → 复制 Access Secret。",
             "https://developer.zhihu.com/"),
    CredSpec("qianfan_api_key", "baidu", "百度千帆 API Key", "key",
             "百度官方 AI 搜索接口（百度搜索结果）。到千帆控制台 → API Key → 创建，复制 bce-v3 开头的 Key。",
             "https://console.bce.baidu.com/iam/#/iam/apikey/list"),
    CredSpec("douyin_cookie", "douyin", "抖音 Cookie", "cookie",
             "抖音网页版搜索需要登录。在浏览器登录 douyin.com 后复制整段 Cookie。",
             "https://www.douyin.com/"),
    CredSpec("bilibili_cookie", "bilibili", "B站 Cookie（可选）", "cookie",
             "不填也能搜（游客身份），登录后更稳。推荐点「扫码登录」，会自动续期长期有效；也可以手动粘贴 Cookie。",
             "https://www.bilibili.com/"),
    CredSpec("bilibili_refresh_token", "bilibili", "B站刷新口令", "key", "扫码登录时自动保存，用于续期", "", hidden=True),
    CredSpec("bilibili_refreshed_at", "bilibili", "B站上次续期时间", "key", "", "", hidden=True),
    CredSpec("deepseek_api_key", "llm", "DeepSeek API Key", "key", "写稿、对话用的模型 Key", "https://platform.deepseek.com/api_keys",
             hidden=True),  # 在首页「开始之前」里单独填
    CredSpec("image_api_key", "image", "AI 配图 API Key", "key", "grsai 的 API Key", "https://grsai.ai/zh/dashboard/api-keys",
             hidden=True),  # 配图在单独的「AI 配图」设置里填，不出现在数据来源列表
    CredSpec("image_model", "image", "配图模型", "key", "", "", hidden=True),
    CredSpec("image_refs", "image", "参考对标原图", "key", "", "", hidden=True),  # "off" 表示不参考
    CredSpec("weibo_cookie", "weibo", "微博 Cookie", "cookie",
             "微博按关键词搜索需要登录。登录 weibo.com 后复制 Cookie（需包含 SUB）。",
             "https://weibo.com/"),
]
_BY_KEY = {s.key: s for s in SPECS}
_lock = threading.Lock()


def _path():
    return get_settings().data_dir / "credentials.json"


def _load() -> dict[str, str]:
    try:
        return json.loads(_path().read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def get(key: str) -> str:
    if key not in _BY_KEY:
        raise KeyError(key)
    v = _load().get(key)
    if v is None:
        v = getattr(get_settings(), key, "") or ""
    return (v or "").strip()


def update(values: dict[str, str | None]) -> None:
    """None 表示不改；空字符串表示清除（回落到环境变量）。"""
    with _lock:
        data = _load()
        for k, v in values.items():
            if k not in _BY_KEY or v is None:
                continue
            v = v.strip()
            if v:
                data[k] = v
            else:
                data.pop(k, None)
        p = _path()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        try:
            p.chmod(0o600)
        except OSError:
            pass
