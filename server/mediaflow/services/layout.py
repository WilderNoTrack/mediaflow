"""代码排版出图：文字卡片，以及给照片 / AI 画面叠字。字是代码排上去的，一个字都不会错，改字也不用重新生图。

- 出 1080×1440（小红书 3:4）PNG；中文字体自动找系统里的（思源黑体 / Noto Sans CJK / 苹方 / 微软雅黑），
  也可以用环境变量 MEDIAFLOW_FONT（粗体）/ MEDIAFLOW_FONT_REGULAR 指定字体文件
- 卡片 card(layout)：kind = cover 封面大字 / list 清单 / steps 步骤 / compare 对比 / quote 金句
- 叠字 overlay(底图, layout)：封面大字放上/中/下，自动压暗渐变保证看得清；清单、步骤、对比、金句放在半透明面板里
- 配色 PALETTES 里选一个名字，整套图用同一个

layout 字段：kind, title, subtitle, tag（左上角小标签）, items（清单/步骤每条）, left/right（对比两栏 {title, items}）,
highlight（标题里要高亮的词）, position（叠字位置 top/center/bottom）, footer（底部小字）, palette
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

W, H = 1080, 1440
M = 92  # 左右留白
KINDS = ("cover", "list", "steps", "compare", "quote", "caption")


class LayoutError(RuntimeError):
    pass


# ─── 配色 ──────────────────────────────────────────────────────────────────────
# bg 底色 / panel 卡片底 / fg 正文 / sub 次要文字 / accent 强调色 / on_accent 强调色上的字 / marker 高亮笔
PALETTES: dict[str, dict[str, str]] = {
    "cream": {"label": "奶油暖橙", "bg": "#FFF7EC", "panel": "#FFFFFF", "fg": "#2E2A26", "sub": "#8C8073",
              "accent": "#FF7A45", "on_accent": "#FFFFFF", "marker": "#FFD666"},
    "mint": {"label": "薄荷绿", "bg": "#EAF7F0", "panel": "#FFFFFF", "fg": "#1F3B2F", "sub": "#5F7D6E",
             "accent": "#25A06B", "on_accent": "#FFFFFF", "marker": "#B7EB8F"},
    "pink": {"label": "樱花粉", "bg": "#FFF0F4", "panel": "#FFFFFF", "fg": "#3A2230", "sub": "#9A7584",
             "accent": "#F2557F", "on_accent": "#FFFFFF", "marker": "#FFC6D6"},
    "blue": {"label": "雾霾蓝", "bg": "#EEF3FC", "panel": "#FFFFFF", "fg": "#1D2B4F", "sub": "#66789C",
             "accent": "#3B66F5", "on_accent": "#FFFFFF", "marker": "#BCD0FF"},
    "yellow": {"label": "亮黄", "bg": "#FFE14D", "panel": "#FFFBE6", "fg": "#1A1A1A", "sub": "#5C5320",
               "accent": "#1A1A1A", "on_accent": "#FFE14D", "marker": "#FFFFFF"},
    "dark": {"label": "黑金", "bg": "#1C1C1E", "panel": "#2C2C2F", "fg": "#FFFFFF", "sub": "#A6A6AD",
             "accent": "#FFD23F", "on_accent": "#1C1C1E", "marker": "#6B5A12"},
    "morandi": {"label": "莫兰迪", "bg": "#ECE6DF", "panel": "#F8F5F1", "fg": "#4A4440", "sub": "#8C837B",
                "accent": "#9C7F6E", "on_accent": "#FFFFFF", "marker": "#DCC9BB"},
    "kraft": {"label": "牛皮纸", "bg": "#EBDDC3", "panel": "#F7EFE1", "fg": "#3B2F22", "sub": "#7A6650",
              "accent": "#C0502E", "on_accent": "#FFFFFF", "marker": "#F2C14E"},
}
DEFAULT_PALETTE = "cream"


def palette(name: str | None) -> dict[str, tuple[int, int, int]]:
    p = PALETTES.get(str(name or "").strip().lower()) or PALETTES[DEFAULT_PALETTE]
    return {k: _rgb(v) for k, v in p.items() if k != "label"}


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ─── 字体 ──────────────────────────────────────────────────────────────────────
# (粗体, 常规)；ttc 里会自动挑简体中文那一款
_CANDIDATES: list[tuple[str, str]] = [
    ("/usr/share/fonts/google-noto-cjk/NotoSansSC-Bold.otf", "/usr/share/fonts/google-noto-cjk/NotoSansSC-Regular.otf"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc", "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/PingFang.ttc"),
    ("/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/STHeiti Light.ttc"),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"),
    ("C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simhei.ttf"),
]
_BOLD_STYLES = ("bold", "semibold", "heavy", "black", "medium", "粗")
_SC_HINTS = ("sc", "gb", "简", "sans cjk sc", "pingfang sc", "microsoft yahei", "微软雅黑", "heiti sc", "simhei")


def _fc_list() -> list[str]:
    if not shutil.which("fc-list"):
        return []
    try:
        out = subprocess.run(["fc-list", ":lang=zh", "file"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.split(":")[0].strip() for line in out.splitlines() if line.strip()]


@lru_cache(maxsize=1)
def font_files() -> tuple[str, str]:
    """找中文字体：(粗体文件, 常规文件)。找不到抛 LayoutError。"""
    env_b, env_r = os.environ.get("MEDIAFLOW_FONT", ""), os.environ.get("MEDIAFLOW_FONT_REGULAR", "")
    if env_b and Path(env_b).exists():
        return env_b, env_r if env_r and Path(env_r).exists() else env_b
    for b, r in _CANDIDATES:
        if Path(b).exists():
            return b, r if Path(r).exists() else b
    files = [f for f in _fc_list() if f.lower().endswith((".ttf", ".otf", ".ttc"))]
    sans = [f for f in files if "serif" not in f.lower()] or files
    if sans:
        bold = next((f for f in sans if any(s in f.lower() for s in ("bold", "black", "heavy", "medium"))), sans[0])
        reg = next((f for f in sans if "regular" in f.lower()), bold)
        return bold, reg
    raise LayoutError("没找到中文字体：装一个（Linux：apt install fonts-noto-cjk），或者用 MEDIAFLOW_FONT 指定字体文件")


def available() -> bool:
    try:
        font_files()
    except LayoutError:
        return False
    return True


@lru_cache(maxsize=8)
def _face_index(path: str, bold: bool) -> int:
    """ttc 里有好几款（日/韩/简/繁、不同粗细），挑简体中文、粗细合适的那款。"""
    if not path.lower().endswith(".ttc"):
        return 0
    best, best_score = 0, -1
    for i in range(40):
        try:
            f = ImageFont.truetype(path, 20, index=i)
        except OSError:
            break
        family, style = (x.lower() for x in f.getname())
        score = (3 if any(h in family for h in _SC_HINTS) else 0)
        is_bold = any(s in style for s in _BOLD_STYLES) or any(s in family for s in ("bold", "semibold", "medium"))
        score += 2 if is_bold == bold else 0
        score += 1 if not bold and style in ("regular", "normal", "light") else 0
        if score > best_score:
            best, best_score = i, score
    return best


@lru_cache(maxsize=256)
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    b, r = font_files()
    path = b if bold else r
    return ImageFont.truetype(path, max(8, int(size)), index=_face_index(path, bold))


# ─── 文字处理 ──────────────────────────────────────────────────────────────────
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\U0000200D\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF]")
_NO_START = set("，。！？、；：,.!?;:）)」』》】〉”’…%·~～")
_NO_END = set("（(「『《【〈“‘")
# 英文单词、数字连同后面的单位（5天、133元、150g）不拆开
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.%+\-/:'&]*[\u4e00-\u9fff]?|\s+|.", re.S)


_PHONETIC = re.compile(r"\s?[/\[][^/\[\]\n]{1,40}[/\]]")


@lru_cache(maxsize=4096)
def _supported(ch: str) -> bool:
    """字体里有没有这个字（没有的话画出来是方框）：和一个肯定没有的字画出来比一比。"""
    # 拉丁字母（到 Latin Extended-B）、中日韩、全角肯定有；音标（ɪ ə ˈ）、特殊符号这些中文字体常常没有，要实际比一比
    if ord(ch) < 0x250 or 0x3000 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF:
        return True
    f = font(40)
    try:
        return f.getmask(ch).tobytes() != f.getmask("\U0010FFFD").tobytes()
    except Exception:  # noqa: BLE001
        return False


def clean(text: object, limit: int = 120) -> str:
    """去掉表情符号和字体里没有的字，压掉多余空白（保留换行）。"""
    s = _EMOJI.sub("", str(text or ""))
    # 音标里有字体没有的字（/rɪˈteɪn/）：整段音标去掉，免得剩下半截「/rten/」
    s = _PHONETIC.sub(lambda m: "" if any(not _supported(c) for c in m.group(0)) else m.group(0), s)
    s = "\n".join(" ".join(line.split()) for line in s.replace("\r", "").split("\n"))
    s = "".join(ch for ch in s if ch == "\n" or _supported(ch))
    return s.strip()[:limit]


def wrap(text: str, f: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """中文按字换行、英文单词不拆；标点不放行首、开括号不放行尾。"""
    lines: list[str] = []
    for para in text.split("\n"):
        cur, para_start = "", len(lines)
        for tok in _TOKEN.findall(para):
            if tok.isspace() and not cur:
                continue
            if f.getlength(cur + tok) <= width:
                cur += tok
                continue
            if tok in _NO_START and cur:  # 标点挤在上一行末尾
                cur += tok
                continue
            carry = ""
            while cur and cur[-1] in _NO_END:  # 开括号跟着下一行走
                carry, cur = cur[-1] + carry, cur[:-1]
            if cur.strip():
                lines.append(cur.rstrip())
            cur = carry + tok.lstrip()
            while f.getlength(cur) > width and len(cur) > 1:  # 超长的英文串硬拆
                k = len(cur)
                while k > 1 and f.getlength(cur[:k]) > width:
                    k -= 1
                lines.append(cur[:k])
                cur = cur[k:]
        if cur.strip():
            lines.append(cur.rstrip())
        _no_orphan(lines, para_start)
    return lines or [""]


def _no_orphan(lines: list[str], start: int) -> None:
    """最后一行只剩一两个字（「防/水」）时，从上一行挪几个字下来，读起来不断气（按词挪，不拆「5天」「150g」）。"""
    if len(lines) - start < 2:
        return
    prev, last = lines[-2], lines[-1]
    if len(last) > 2 or len(prev) < 5:
        return
    toks = _TOKEN.findall(prev)
    while len(last) < 3 and len(toks) > 1 and len("".join(toks)) > 4:
        last = toks.pop() + last
        while toks and len(toks) > 1 and last[0] in _NO_START:
            last = toks.pop() + last
    lines[-2], lines[-1] = "".join(toks).rstrip(), last.lstrip()


def fit(text: str, width: float, height: float, *, bold: bool = True, max_size: int = 120, min_size: int = 28,
        max_lines: int = 4, spacing: float = 1.28) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """找能放进框里的最大字号：返回 (字体, 分好的行, 行高)。放不下就用最小字号、截掉多的行。"""
    size = max_size
    while True:
        f = font(size, bold)
        lines = wrap(text, f, width)
        lh = int(size * spacing)
        if (len(lines) <= max_lines and lh * len(lines) <= height) or size <= min_size:
            if len(lines) > max_lines or lh * len(lines) > height:
                keep = max(1, min(max_lines, int(height // lh)))
                lines = lines[:keep]
                lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else lines[-1]
            return f, lines, lh
        size = max(min_size, size - (4 if size > 60 else 2))


def _ink(f: ImageFont.FreeTypeFont) -> int:
    """字的视觉顶部偏移：Pillow 的 y 是从字身顶部算，中文字形上面有一点空。"""
    return f.getbbox("国")[1]


def draw_lines(d: ImageDraw.ImageDraw, lines: list[str], f: ImageFont.FreeTypeFont, lh: int, x: float, y: float,
               color, *, align: str = "left", width: float = 0, highlight: str = "", marker=None, hl_color=None) -> float:
    """一行行画字，返回画完后的 y。highlight 里的词：marker 给了就在字下半截画高亮笔，hl_color 给了就换字色。"""
    joined = "".join(lines)
    spans: list[tuple[int, int]] = []
    hl = "".join(clean(highlight, 30).split())
    if hl:  # 不管空格找高亮词（模型常写「133元」而标题是「133 元」）
        pos = [k for k, ch in enumerate(joined) if not ch.isspace()]
        compact = "".join(joined[k] for k in pos)
        start = compact.find(hl)
        while start >= 0:
            spans.append((pos[start], pos[start + len(hl) - 1] + 1))
            start = compact.find(hl, start + len(hl))
    off = 0
    top = _ink(f)
    for line in lines:
        lw = f.getlength(line)
        lx = x + (width - lw) / 2 if align == "center" and width else (x + width - lw if align == "right" and width else x)
        ly = y + (lh - f.size) / 2 - top * 0.6
        for a, b in spans:
            a2, b2 = max(a, off), min(b, off + len(line))
            if a2 < b2 and marker is not None:
                x1 = lx + f.getlength(line[: a2 - off])
                x2 = lx + f.getlength(line[: b2 - off])
                d.rounded_rectangle([x1 - 6, ly + top + f.size * 0.48, x2 + 6, ly + top + f.size * 1.02],
                                    radius=10, fill=marker)
        if spans and hl_color is not None:
            cx = lx
            for k, ch in enumerate(line):
                inside = any(a <= off + k < b for a, b in spans)
                d.text((cx, ly), ch, font=f, fill=hl_color if inside else color)
                cx += f.getlength(ch)
        else:
            d.text((lx, ly), line, font=f, fill=color)
        off += len(line)
        y += lh
    return y


def _pill(d: ImageDraw.ImageDraw, text: str, x: float, y: float, size: int, bg, fg, *, pad: int = 22) -> float:
    f = font(size)
    tw = f.getlength(text)
    h = int(size * 1.7)
    d.rounded_rectangle([x, y, x + tw + pad * 2, y + h], radius=h // 2, fill=bg)
    d.text((x + pad, y + (h - size) / 2 - _ink(f) * 0.6), text, font=f, fill=fg)
    return x + tw + pad * 2


def _items(lay: dict, key: str = "items", n: int = 8) -> list[str]:
    raw = lay.get(key) or []
    if isinstance(raw, str):
        raw = [x for x in re.split(r"\n|；|;", raw)]
    out = []
    for x in raw:
        s = clean(x if not isinstance(x, dict) else (x.get("text") or x.get("title") or ""), 80)
        s = re.sub(r"^\s*(\d+[.、)）]|[-*•·])\s*", "", s)  # 去掉模型自己写的编号
        if s:
            out.append(s)
    return out[:n]


# ─── 各种页 ────────────────────────────────────────────────────────────────────
def _decor(img: Image.Image, p: dict) -> None:
    """卡片底：淡淡的点阵 + 右下角一个强调色大圆，像手账本，不抢字。"""
    d = ImageDraw.Draw(img, "RGBA")
    bg = p["bg"]
    dark = sum(bg) < 300
    dot = (255, 255, 255, 22) if dark else (0, 0, 0, 16)
    for yy in range(60, H, 44):
        for xx in range(60, W, 44):
            d.ellipse([xx - 2, yy - 2, xx + 2, yy + 2], fill=dot)
    a = p["accent"]
    d.ellipse([W - 330, H - 300, W + 170, H + 200], fill=(*a, 34))
    d.ellipse([-160, -140, 220, 240], fill=(*a, 22))


def _cover(img: Image.Image, lay: dict, p: dict, box: tuple[int, int, int, int], *, on_photo: bool = False) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = box
    width = x1 - x0
    tag = clean(lay.get("tag"), 14)
    title = clean(lay.get("title"), 60) or " "
    sub = clean(lay.get("subtitle"), 80)
    footer = clean(lay.get("footer"), 30)
    y = y0
    if tag:
        _pill(d, tag, x0, y, 40, p["accent"], p["on_accent"])
        y += 110
    sub_h = 0
    if sub:
        fs, sub_lines, slh = fit(sub, width, 220, bold=False, max_size=52 if not on_photo else 44, min_size=32, max_lines=3)
        sub_h = slh * len(sub_lines) + 50
    title_h = (y1 - y) - sub_h - (90 if footer else 0)
    if on_photo:  # 照片上的字别太大，把画面主体盖住
        title_h = min(title_h, int(H * 0.3))
    f, lines, lh = fit(title, width, title_h, max_size=118 if on_photo else 168, min_size=56, max_lines=3 if on_photo else 4,
                       spacing=1.2)
    th = lh * len(lines)
    if not on_photo:  # 卡片：标题块在剩下的空间里竖着居中偏上
        y = y + max(0, ((y1 - y) - th - sub_h - (90 if footer else 0)) * 0.48)
    else:
        y = y if lay.get("position") == "top" else (y1 - th - sub_h - (60 if footer else 0) if lay.get("position") != "center"
                                                     else y0 + ((y1 - y0) - th - sub_h) / 2)
    fg = (255, 255, 255) if on_photo else p["fg"]
    y = draw_lines(d, lines, f, lh, x0, y, fg, width=width, highlight=lay.get("highlight", ""),
                   marker=None if on_photo else (*p["marker"], 255), hl_color=(255, 214, 64) if on_photo else None)
    if not on_photo:
        d.rounded_rectangle([x0, y + 18, x0 + 120, y + 30], radius=6, fill=p["accent"])
    if sub:
        y = draw_lines(d, sub_lines, fs, slh, x0, y + 50, (245, 245, 245) if on_photo else p["fg"], width=width)
    if footer:
        _footer(d, lay, p, x0, y1, (235, 235, 235) if on_photo else None)


def _title_block(d: ImageDraw.ImageDraw, lay: dict, p: dict, x0: float, y: float, width: float, *,
                 max_size: int = 96, measure: bool = False) -> float:
    """清单/步骤/对比页顶上的标题 + 小标签 + 强调短线，返回下面内容从哪开始。measure=True 只量高度不画。"""
    tag = clean(lay.get("tag"), 14)
    title = clean(lay.get("title"), 40)
    if tag:
        if not measure:
            _pill(d, tag, x0, y, 36, p["accent"], p["on_accent"])
        y += 92
    if title:
        f, lines, lh = fit(title, width, 270, max_size=max_size, min_size=52, max_lines=2, spacing=1.2)
        if measure:
            y += lh * len(lines)
        else:
            y = draw_lines(d, lines, f, lh, x0, y, p["fg"], width=width, highlight=lay.get("highlight", ""),
                           marker=(*p["marker"], 255))
            d.rounded_rectangle([x0, y + 16, x0 + 100, y + 28], radius=6, fill=p["accent"])
        y += 70
    return y


def _footer(d: ImageDraw.ImageDraw, lay: dict, p: dict, x0: float, y1: float, color=None) -> int:
    footer = clean(lay.get("footer"), 30)
    if footer:
        d.text((x0, y1 - 46), footer, font=font(34, bold=False), fill=color or p["sub"])
    return 76 if footer else 0


def _list(img: Image.Image, lay: dict, p: dict, box: tuple[int, int, int, int], *, steps: bool = False,
          compact: bool = False) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = box
    width = x1 - x0
    items = _items(lay) or [clean(lay.get("subtitle"), 80) or " "]
    n = len(items)
    bottom = y1 - _footer(d, lay, p, x0, y1)
    head = _title_block(d, lay, p, x0, y0, width, measure=True) - y0
    avail = bottom - y0 - head
    num_d = 68
    # 字号挑放得下的最大（所有条目同一个字号）；放下以后多出来的地方，加大条目内边距和间距，最后整体竖着居中
    pad, gap = 30, 26
    size, wrapped, lh = 58, [], 0
    for size in range(58, 27, -2):
        f = font(size, bold=False)
        lh = int(size * 1.4)
        wrapped = [wrap(t, f, width - pad * 2 - num_d - 36)[:3] for t in items]
        if sum(max(num_d, len(ls) * lh) + pad * 2 for ls in wrapped) + gap * (n - 1) <= avail:
            break
    f = font(size, bold=False)
    content = lambda pd, gp: sum(max(num_d, len(ls) * lh) + pd * 2 for ls in wrapped) + gp * (n - 1)  # noqa: E731
    while not compact and content(pad + 4, gap) <= avail * 0.86 and pad < 48:
        pad += 4
    while not compact and content(pad, gap + 6) <= avail * 0.86 and gap < (60 if steps else 44):
        gap += 6
    total = content(pad, gap)
    y = y0 if compact else y0 + max(0, (avail - total) * 0.45)  # 标题跟着内容一起居中，不会上面挤下面空
    y = _title_block(d, lay, p, x0, y, width)
    fb = font(int(num_d * 0.5))
    centers = []
    for k, ls in enumerate(wrapped):
        h = max(num_d, len(ls) * lh) + pad * 2
        if not steps:
            d.rounded_rectangle([x0, y, x1, y + h], radius=30, fill=(*p["panel"], 255))
        cx, cy = x0 + (pad if not steps else 0) + num_d / 2, y + h / 2
        centers.append((cx, cy))
        d.ellipse([cx - num_d / 2, cy - num_d / 2, cx + num_d / 2, cy + num_d / 2], fill=p["accent"])
        num = str(k + 1)
        d.text((cx - fb.getlength(num) / 2, cy - fb.size / 2 - _ink(fb) * 0.6), num, font=fb, fill=p["on_accent"])
        draw_lines(d, ls, f, lh, cx + num_d / 2 + 36, y + (h - len(ls) * lh) / 2, p["fg"])
        y += h + gap
    if steps and len(centers) > 1:  # 步骤：圆点之间连一条线
        for (ax, ay), (bx, by) in zip(centers, centers[1:]):
            d.line([ax, ay + num_d / 2 + 8, bx, by - num_d / 2 - 8], fill=(*p["accent"], 110), width=6)


def _compare(img: Image.Image, lay: dict, p: dict, box: tuple[int, int, int, int], *, compact: bool = False) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = box
    width = x1 - x0
    cols = []
    for side in ("left", "right"):
        c = lay.get(side) if isinstance(lay.get(side), dict) else {}
        cols.append((clean(c.get("title"), 12) or ("before" if side == "left" else "after"), _items(c, n=6)))
    gap, head_h = 28, 108
    cw = (width - gap) / 2
    bottom = y1 - _footer(d, lay, p, x0, y1)
    head = _title_block(d, lay, p, x0, y0, width, max_size=92, measure=True) - y0
    avail = bottom - y0 - head
    size, lh, item_gap = 50, 0, 30

    def col_h(sz: int, ig: int) -> int:
        fo = font(sz, bold=False)
        ln = int(sz * 1.4)
        return max(sum(len(wrap(t, fo, cw - 76)[:4]) * ln + ig for t in its) for _, its in cols) + head_h + 70

    for size in range(50, 25, -2):
        if col_h(size, item_gap) <= avail:
            break
    while not compact and col_h(size, item_gap + 8) <= avail * 0.8 and item_gap < 70:
        item_gap += 8
    f = font(size, bold=False)
    lh = int(size * 1.4)
    ph = min(avail, col_h(size, item_gap) if compact else max(col_h(size, item_gap), int(avail * 0.6)))
    y = y0 if compact else y0 + max(0, (avail - ph) * 0.45)
    y = _title_block(d, lay, p, x0, y, width, max_size=92)
    colors = [(p["sub"], (255, 255, 255)), (p["accent"], p["on_accent"])]
    for k, (headtxt, its) in enumerate(cols):
        cx = x0 + k * (cw + gap)
        d.rounded_rectangle([cx, y, cx + cw, y + ph], radius=30, fill=(*p["panel"], 255))
        d.rounded_rectangle([cx, y, cx + cw, y + head_h], radius=30, fill=colors[k][0])
        d.rectangle([cx, y + head_h - 30, cx + cw, y + head_h], fill=colors[k][0])
        hf, hl, hlh = fit(headtxt, cw - 40, head_h - 20, max_size=52, min_size=30, max_lines=1)
        draw_lines(d, hl, hf, hlh, cx + 20, y + (head_h - hlh) / 2, colors[k][1], align="center", width=cw - 40)
        ty = y + head_h + 36
        for t in its:
            ls = wrap(t, f, cw - 76)[:4]
            d.ellipse([cx + 28, ty + lh / 2 - 7, cx + 42, ty + lh / 2 + 7], fill=colors[k][0])
            ty = draw_lines(d, ls, f, lh, cx + 58, ty, p["fg"]) + item_gap


def _quote(img: Image.Image, lay: dict, p: dict, box: tuple[int, int, int, int], *, compact: bool = False) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = box
    width = x1 - x0
    text = clean(lay.get("title"), 90) or " "
    sub = clean(lay.get("subtitle"), 60)
    bottom = y1 - _footer(d, lay, p, x0, y1)
    f, lines, lh = fit(text, width, (bottom - y0) - 330, max_size=80 if compact else 92, min_size=44, max_lines=6,
                       spacing=1.4)
    th = lh * len(lines) + 200 + (110 if sub else 0)  # 引号 + 正文 + 署名
    y = y0 + 40 if compact else y0 + max(0, ((bottom - y0) - th) * 0.45)
    d.text((x0 - 12, y - 70), "“", font=font(300), fill=(*p["accent"], 210))
    y = draw_lines(d, lines, f, lh, x0, y + 200, p["fg"], width=width, highlight=lay.get("highlight", ""),
                   marker=(*p["marker"], 255))
    if sub:
        d.rounded_rectangle([x0, y + 62, x0 + 64, y + 70], radius=4, fill=p["accent"])
        sf = font(40, bold=False)
        d.text((x0 + 84, y + 66 - sf.size / 2 - _ink(sf) * 0.6), sub, font=sf, fill=p["sub"])


def _render_kind(img: Image.Image, lay: dict, p: dict, box: tuple[int, int, int, int], *, on_photo: bool = False,
                 compact: bool = False) -> None:
    kind = str(lay.get("kind") or "cover").strip().lower()
    if kind in ("list", "steps"):
        _list(img, lay, p, box, steps=kind == "steps", compact=compact)
    elif kind == "compare":
        _compare(img, lay, p, box, compact=compact)
    elif kind == "quote":
        _quote(img, lay, p, box, compact=compact)
    else:
        _cover(img, lay, p, box, on_photo=on_photo)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def card(lay: dict, palette_name: str | None = None) -> bytes:
    """纯代码排版的一张卡片（不用生图额度）。"""
    p = palette(palette_name or lay.get("palette"))
    img = Image.new("RGB", (W, H), p["bg"])
    _decor(img, p)
    _render_kind(img, {**lay, "kind": "cover"} if lay.get("kind") in ("caption", "none") else lay, p, (M, 120, W - M, H - 110))
    return _png(img)


def cover_fit(data: bytes | Image.Image, w: int = W, h: int = H) -> Image.Image:
    """把图裁成 3:4 铺满（居中偏上裁，人脸/主体一般在上半部分）。"""
    img = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    nw, nh = max(w, round(img.width * s)), max(h, round(img.height * s))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = int((nh - h) * 0.4)
    return img.crop((left, top, left + w, top + h))


def _gradient(img: Image.Image, position: str, strength: int = 190) -> None:
    """叠字那一侧压暗，白字在什么底图上都看得清。"""
    grad = Image.new("L", (1, H), 0)
    for yy in range(H):
        if position == "top":
            t = max(0.0, 1 - yy / (H * 0.62))
        elif position == "center":
            t = max(0.0, 1 - abs(yy - H / 2) / (H * 0.42)) * 0.8
        else:
            t = max(0.0, (yy - H * 0.36) / (H * 0.64))
        grad.putpixel((0, yy), int(strength * min(1.0, t) ** 1.2))
    mask = grad.resize((W, H))
    img.paste(Image.new("RGB", (W, H), (12, 12, 14)), (0, 0), mask)


def _caption(img: Image.Image, lay: dict, p: dict) -> Image.Image:
    """纪实照片上的小字标注：一块浅色圆角小标签，一两行短句，不压暗照片（像博主随手在图上打的字）。"""
    text = "\n".join(x for x in (clean(lay.get("title"), 60), clean(lay.get("subtitle"), 60)) if x)
    if not text:
        return img
    f, lines, lh = fit(text.replace("\n", " "), W * 0.58, 220, max_size=46, min_size=32, max_lines=3, spacing=1.36)
    if lay.get("subtitle") and len(lines) < 3:  # 两句分两行
        f2, l1, _ = fit(clean(lay.get("title"), 60), W * 0.58, 120, max_size=f.size, min_size=32, max_lines=2)
        _, l2, _ = fit(clean(lay.get("subtitle"), 60), W * 0.58, 120, max_size=f.size, min_size=32, max_lines=2)
        if len(l1) + len(l2) <= 3:
            f, lines = f2, l1 + l2
    pad_x, pad_y = 30, 22
    tw = max(f.getlength(x) for x in lines)
    bw, bh = int(tw + pad_x * 2), int(lh * len(lines) + pad_y * 2 - (lh - f.size) * 0.6)
    pos = str(lay.get("position") or "top").lower()
    y0 = {"top": int(H * 0.12), "center": (H - bh) // 2}.get(pos, int(H * 0.86) - bh)
    x0 = M if lay.get("align") != "right" else W - M - bw
    layer = img.convert("RGBA")
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 6, x0 + bw, y0 + bh + 6], radius=14, fill=(0, 0, 0, 60))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(8)))
    box = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(box)
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=14, fill=(*p["panel"], 238))
    y = y0 + pad_y - _ink(f) * 0.6
    for line in lines:
        d.text((x0 + pad_x, y), line, font=f, fill=p["fg"])
        y += lh
    return Image.alpha_composite(layer, box)


def overlay(base: bytes | Image.Image, lay: dict, palette_name: str | None = None) -> bytes:
    """给照片 / AI 画面叠字：封面大字用渐变压暗 + 白字；清单/步骤/对比/金句放在半透明面板里。没字就只裁成 3:4。"""
    p = palette(palette_name or lay.get("palette"))
    img = cover_fit(base)
    kind = str(lay.get("kind") or "cover").strip().lower()
    has_text = any(clean(lay.get(k)) for k in ("title", "subtitle", "tag")) or _items(lay) \
        or isinstance(lay.get("left"), dict)
    if not has_text or kind == "none":
        return _png(img)
    if kind == "caption":
        return _png(_caption(img, lay, p))
    pos = str(lay.get("position") or ("top" if kind == "cover" else "bottom")).lower()
    pos = pos if pos in ("top", "center", "bottom") else "bottom"
    if kind not in ("list", "steps", "compare", "quote"):
        _gradient(img, pos)
        layer = img.convert("RGBA")
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        box = (M, 110, W - M, H - 110) if pos != "top" else (M, 110, W - M, int(H * 0.6))
        # 先在阴影层画一遍字（模糊后当阴影），再画正文
        tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _cover(tmp, {**lay, "position": pos}, p, box, on_photo=True)
        alpha = tmp.split()[3]
        shadow.paste((0, 0, 0, 140), (0, 4), alpha)
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        layer = Image.alpha_composite(layer, shadow)
        layer = Image.alpha_composite(layer, tmp)
        return _png(layer)
    # 面板：先把字排在透明层上量出多高，面板刚好包住字，照片尽量多露出来
    txt = Image.new("RGBA", img.size, (0, 0, 0, 0))
    _render_kind(txt, {**lay, "footer": ""}, p, (100, 0, W - 100, int(H * 0.66)), compact=True)
    bbox = txt.split()[3].getbbox() or (0, 0, W, 200)
    pad = 56
    ph = min(H - 120, bbox[3] - bbox[1] + pad * 2)
    py0 = {"top": 60, "center": (H - ph) // 2}.get(pos, H - ph - 60)
    layer = img.convert("RGBA")
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([50, py0 + 10, W - 50, py0 + ph + 10], radius=44, fill=(0, 0, 0, 70))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(18)))
    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([50, py0, W - 50, py0 + ph], radius=44, fill=(*p["bg"], 246))
    layer = Image.alpha_composite(layer, panel)
    moved = Image.new("RGBA", img.size, (0, 0, 0, 0))
    moved.paste(txt, (0, py0 + pad - bbox[1]), txt)
    return _png(Image.alpha_composite(layer, moved))


def render(mode: str, lay: dict, base: bytes | None = None, palette_name: str | None = None) -> bytes:
    """按做法出成品：card 直接排版；photo / ai_text 在底图上叠字。"""
    if mode == "card" or base is None:
        return card(lay, palette_name)
    return overlay(base, lay, palette_name)
