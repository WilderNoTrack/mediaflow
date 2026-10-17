"""代码层面的硬检查与选题去重。

这些规则不靠模型自觉：小红书平台限制（标题 20 字、正文 1000 字）和
违规风险词，交给代码判断，结果直接决定要不要重写。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

TITLE_MAX = 20
BODY_MIN = 150
BODY_MAX = 1000
TAGS_MIN = 3
TAGS_MAX = 10
IMAGES_MIN = 1
IMAGES_MAX = 9

# 广告法极限词 / 夸大功效 / 站外导流：小红书容易限流或判违规
RISKY_WORDS = (
    "全网第一", "全网最低", "史上最", "国家级", "世界级", "顶级", "万能",
    "100%有效", "百分百有效", "绝对有效", "根治", "无副作用", "药到病除",
    "微信", "vx", "VX", "加我", "私信我领", "淘宝链接", "拼多多链接",
)


def text_len(s: str) -> int:
    return len((s or "").strip())


def hard_check(title: str, body: str, tags: list[str], image_prompts: list[str]) -> list[str]:
    issues: list[str] = []
    if not title.strip():
        issues.append("标题为空")
    elif text_len(title) > TITLE_MAX:
        issues.append(f"标题 {text_len(title)} 字，超过小红书上限 {TITLE_MAX} 字")
    n = text_len(body)
    if n < BODY_MIN:
        issues.append(f"正文只有 {n} 字，太单薄（至少 {BODY_MIN} 字）")
    elif n > BODY_MAX:
        issues.append(f"正文 {n} 字，超过小红书上限 {BODY_MAX} 字")
    if not (TAGS_MIN <= len(tags) <= TAGS_MAX):
        issues.append(f"标签 {len(tags)} 个，应为 {TAGS_MIN}-{TAGS_MAX} 个")
    if not (IMAGES_MIN <= len(image_prompts) <= IMAGES_MAX):
        issues.append(f"配图 {len(image_prompts)} 张，应为 {IMAGES_MIN}-{IMAGES_MAX} 张")
    hits = sorted({w for w in RISKY_WORDS if w in title or w in body})
    if hits:
        issues.append("含有违规风险词：" + "、".join(hits))
    return issues


def clean_tags(tags: Iterable[str]) -> list[str]:
    out: list[str] = []
    for t in tags:
        t = str(t).strip().lstrip("#").strip()
        if t and t not in out:
            out.append(t[:20])
    return out


# ─── 去重 ────────────────────────────────────────────────────────────────────

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(s: str) -> str:
    return _NON_WORD.sub("", s.lower())


def _bigrams(s: str) -> set[str]:
    s = _normalize(s)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def similarity(a: str, b: str) -> float:
    """字符二元组 Jaccard：对中文换个说法的同一选题足够敏感，且无需额外依赖。"""
    x, y = _bigrams(a), _bigrams(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


DUPLICATE_THRESHOLD = 0.5


def is_duplicate(title: str, existing: Iterable[str], threshold: float = DUPLICATE_THRESHOLD) -> bool:
    n = _normalize(title)
    for e in existing:
        ne = _normalize(e)
        if not ne:
            continue
        if n == ne or (len(n) >= 4 and (n in ne or ne in n)):
            return True
        if similarity(title, e) >= threshold:
            return True
    return False
