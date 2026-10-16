from __future__ import annotations

from dataclasses import dataclass, field


class Unsupported(RuntimeError):
    """平台不支持这个能力（或当前没配置凭据），message 里写清原因给模型看。"""


@dataclass
class Creator:
    platform: str
    name: str
    native: str            # 平台内部定位串（如 user_id|xsec_token），由 service 换成短句柄
    fans: str = ""
    desc: str = ""
    posts: str = ""        # 作品数
    url: str = ""
    extra: dict = field(default_factory=dict)  # 获赞、标签等补充信息


@dataclass
class Post:
    platform: str
    title: str
    native: str
    url: str = ""
    author: str = ""
    likes: str = ""
    comments: str = ""
    collects: str = ""
    shares: str = ""
    published: str = ""    # YYYY-MM-DD
    kind: str = ""         # 图文 / 视频 / 文章


@dataclass
class PostDetail(Post):
    content: str = ""
    tags: list[str] = field(default_factory=list)
    top_comments: list[str] = field(default_factory=list)  # 「点赞数｜内容」


def count_num(v) -> float:
    """「1.3万」「2387」「10万+」→ 数字，用于按互动排序。"""
    s = str(v or "").replace("+", "").replace(",", "").strip()
    try:
        if s.endswith("万"):
            return float(s[:-1]) * 1e4
        if s.endswith("亿"):
            return float(s[:-1]) * 1e8
        return float(s or 0)
    except ValueError:
        return 0.0


def fmt_count(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n or "")
    return f"{n / 1e4:.1f}万".replace(".0万", "万") if n >= 10000 else str(n)


def ms_date(ts) -> str:
    import time
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return ""
    if ts > 1e12:
        ts //= 1000
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts > 0 else ""
