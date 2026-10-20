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


_TITLE_CUT = re.compile(r"(?<=[，,！!？?。；;：:|｜、…~～])")


def shorten_title(title: str, limit: int = TITLE_MAX) -> str:
    """模型怎么都改不短时的最后一道兜底：按标点一段段留，留到不超过上限；第一段就超了才硬截。"""
    t = (title or "").strip()
    if text_len(t) <= limit:
        return t
    out = ""
    for seg in _TITLE_CUT.split(t):
        if text_len(out + seg) > limit:
            break
        out += seg
    out = out.strip().rstrip("，,、：:；;|｜ ")
    return out if len(out) >= 4 else t[:limit]


def hard_check(title: str, body: str, tags: list[str], image_prompts: list[str],
               rules: Iterable[str] = ()) -> list[str]:
    """平台硬限制 + 账号规则里能用代码判断的部分（目前是正文字数）。"""
    issues: list[str] = []
    rules = list(rules)
    if not title.strip():
        issues.append("标题为空")
    elif text_len(title) > TITLE_MAX:
        issues.append(f"标题 {text_len(title)} 字，超过小红书上限 {TITLE_MAX} 字")
    n = text_len(body)
    if (rule_len := length_issue(body, rules)):
        issues.append(rule_len)
    elif any(body_range(rules)):
        pass  # 账号自己定了字数，就不再套默认的「至少 150 字」
    elif n < BODY_MIN:
        issues.append(f"正文只有 {n} 字，太单薄（至少 {BODY_MIN} 字）")
    if n > BODY_MAX:
        issues.append(f"正文 {n} 字，超过小红书上限 {BODY_MAX} 字")
    lo = tags_min(rules)
    if not (lo <= len(tags) <= TAGS_MAX):
        issues.append(f"标签 {len(tags)} 个，应为 {lo}-{TAGS_MAX} 个")
    if not (IMAGES_MIN <= len(image_prompts) <= IMAGES_MAX):
        issues.append(f"配图 {len(image_prompts)} 张，应为 {IMAGES_MIN}-{IMAGES_MAX} 张")
    hits = sorted({w for w in RISKY_WORDS if w in title or w in body})
    if hits:
        issues.append("含有违规风险词：" + "、".join(hits))
    return issues


_FEW_TAGS = re.compile(r"单一|一个|1\s*个|一两个|1\s*[-~到至]\s*2|少量|少带|不堆砌")


def tags_min(rules: Iterable[str]) -> int:
    """账号规则要求少带标签（比如对标学来的「只带单一核心话题标签」）时，下限放到 1，不和规则打架。"""
    return 1 if any("标签" in r and _FEW_TAGS.search(r) for r in rules) else TAGS_MIN


def body_len(body: str) -> int:
    """正文字数：不算空格和换行（和小红书编辑器的直观感受接近）。"""
    return len(re.sub(r"\s", "", body or ""))


_RANGE = re.compile(r"(\d{2,4})\s*(?:到|至|~|～|-|－|—|–)\s*(\d{2,4})\s*字")
_MAX = re.compile(r"(?:不超过|不要超过|以内|控制在|最多|少于)\D{0,3}(\d{2,4})\s*字|(\d{2,4})\s*字(?:以内|之内)")
_MIN = re.compile(r"(?:至少|不少于|不低于)\D{0,3}(\d{2,4})\s*字|(\d{2,4})\s*字以上")


def body_range(rules: Iterable[str]) -> tuple[int | None, int | None]:
    """从账号规则里读出正文字数要求（如「正文150到250字」「正文控制在300字以内」），读不出返回 (None, None)。"""
    lo = hi = None
    for r in rules:
        if "正文" in r:
            seg = r[r.index("正文"):]
        elif "字数" in r and "标题" not in r:
            seg = r
        else:
            continue
        if m := _RANGE.search(seg):
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        if m := _MAX.search(seg):
            hi = int(m.group(1) or m.group(2))
        if m := _MIN.search(seg):
            lo = int(m.group(1) or m.group(2))
    return lo, hi


def length_issue(body: str, rules: Iterable[str]) -> str:
    """正文字数不符合账号规则时返回问题描述（允许 5% 的误差），否则空串。模型数不准字，这一条交给代码。"""
    lo, hi = body_range(rules)
    n = body_len(body)
    req = f"{lo}–{hi} 字" if lo and hi else f"不超过 {hi} 字" if hi else f"至少 {lo} 字" if lo else ""
    if hi and n > hi * 1.05:
        return f"正文 {n} 字，账号规则要求 {req}，需要删掉约 {n - hi} 字"
    if lo and n < lo * 0.95:
        return f"正文只有 {n} 字，账号规则要求 {req}，需要补约 {lo - n} 字"
    return ""


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
