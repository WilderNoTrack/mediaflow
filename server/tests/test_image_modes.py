"""配图不止 AI 画：代码排版卡片、网上找图叠字、AI 画面 + 代码排字；直接改字、换做法。"""

import io

import pytest
from PIL import Image
from sqlmodel import select

from mediaflow.agents.pipeline import write_draft
from mediaflow.config import get_settings
from mediaflow.domain.models import Draft, DraftImage, ImageStatus, Job, JobKind
from mediaflow.services import draft_edit, layout, webimg
from mediaflow.services import images as images_mod
from tests.fakes import FakeImages, evaluation, fake_fetch, post

pytestmark = pytest.mark.skipif(not layout.available(), reason="没有中文字体")


def _size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def _photo(color="teal", size=(900, 1200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def test_layout_kinds_render():
    cases = [
        {"kind": "cover", "tag": "干货", "title": "月薪5千也能存下钱的3个笨办法", "highlight": "存下钱", "subtitle": "亲测一年存了2万"},
        {"kind": "list", "title": "减脂外卖这样点", "items": ["主食选杂粮饭", "蛋白质优先", "酱汁单独放🍗"]},
        {"kind": "steps", "title": "3步做燕麦杯", "items": ["泡一晚", "铺酸奶", "放蓝莓"]},
        {"kind": "compare", "title": "通勤包怎么选", "left": {"title": "踩雷", "items": ["太重"]},
         "right": {"title": "推荐", "items": ["尼龙轻便"]}},
        {"kind": "quote", "title": "存钱是为了以后有底气说不。", "subtitle": "写给25岁的自己"},
    ]
    for lay, pal in zip(cases, layout.PALETTES):
        assert _size(layout.card(lay, pal)) == (1080, 1440)
        assert _size(layout.overlay(_photo(size=(1600, 900)), lay, pal)) == (1080, 1440)
    assert _size(layout.overlay(_photo(), {})) == (1080, 1440)  # 没字就只裁成 3:4


def test_caption_and_none_keep_photo():
    """纪实照片的小字标注只占一小块、不压暗；none 一个字都不加。"""
    base = _photo(color=(200, 180, 160))
    plain = Image.open(io.BytesIO(layout.overlay(base, {"kind": "none", "title": "不该出现"}))).convert("RGB")
    assert plain.getpixel((540, 720)) == Image.open(io.BytesIO(layout.overlay(base, {}))).convert("RGB").getpixel((540, 720))
    cap = Image.open(io.BytesIO(layout.overlay(base, {"kind": "caption", "title": "房租1800 采光一般",
                                                      "position": "top"}))).convert("RGB")
    assert cap.size == (1080, 1440)
    assert cap.getpixel((540, 1300)) == plain.getpixel((540, 1300))  # 下面的照片原样露着
    changed = sum(1 for x in range(0, 1080, 20) for y in range(0, 1440, 20) if cap.getpixel((x, y)) != plain.getpixel((x, y)))
    assert changed < 0.2 * (54 * 72)
    assert _size(layout.card({"kind": "caption", "title": "小标注"}, None)) == (1080, 1440)


def test_wrap_rules():
    f = layout.font(60)
    lines = layout.wrap("你好，世界！这是一个测试，看看标点会不会出现在行首。", f, 300)
    assert all(line[0] not in "，。！？、" for line in lines)
    assert "".join(lines) == "你好，世界！这是一个测试，看看标点会不会出现在行首。"
    assert layout.clean("好物🎉分享✨") == "好物分享"
    assert layout.clean("retain /rɪˈteɪn/ 保持") == "retain 保持"  # 音标画不出来就整段去掉，不剩半截
    assert layout.clean("3/4 的人") == "3/4 的人"
    f2, lines2, _ = layout.fit("一个很长很长的标题" * 6, 600, 300, max_size=120, min_size=40, max_lines=3)
    assert len(lines2) <= 3 and f2.size >= 40


def test_mode_options():
    assert images_mod.mode_options("", "ai", True) == ["ai"]
    assert images_mod.mode_options("", "ai", False) == []  # 账号就是 AI 画、又没配 Key：跳过
    assert images_mod.mode_options("", "mixed", False) == ["card"]
    assert images_mod.mode_options("", "auto", False) == ["card", "photo"]
    assert images_mod.mode_options("photo", "ai", False) == ["photo"]  # 这张指定了网上找图，不用 Key 也能出
    assert images_mod.mode_options("ai_text", "card", False) == []


async def _draft(session, llm, account, images=None):
    llm.push("writer", post(images=images or ["封面：标题「月薪5千存钱法」", "清单：「3个笨办法」「记账」「自动转存」「不囤货」"]))
    llm.push("eval", evaluation(8))
    return await write_draft(session, llm, account.id, fetch=fake_fetch)


def _imgs(session, d):
    session.expire_all()
    return session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()


async def test_card_mode_without_ai_key(session, llm, account):
    """账号设成排版卡片：没配生图 Key 也照样出图，字按模型给的 layout 排。"""
    account.image_mode = "card"
    session.add(account)
    session.commit()
    d = await _draft(session, llm, account)
    assert all(i.status == ImageStatus.pending for i in _imgs(session, d))  # 不再是 skipped
    llm.push("image", {"spec": "奶油底", "palette": "mint", "prompts": [
        {"idx": 1, "mode": "card", "layout": {"kind": "cover", "title": "月薪5千存钱法", "highlight": "存钱"}},
        {"idx": 2, "mode": "ai", "layout": {"kind": "list", "title": "3个笨办法", "items": ["记账", "自动转存", "不囤货"]}},
    ]})
    res = await images_mod.generate_images(session, llm, d.id)
    assert res["done"] == 2
    imgs = _imgs(session, d)
    assert [i.made_by for i in imgs] == ["card", "card"]  # 模型选了不允许的 ai，按允许的来
    assert imgs[1].layout["items"] == ["记账", "自动转存", "不囤货"] and imgs[1].layout["palette"] == "mint"
    assert _size((get_settings().images_dir / imgs[0].path).read_bytes()) == (1080, 1440)
    assert "card：纯代码排版" in llm.prompts_of("image")[-1]


async def test_photo_mode_and_fallback(session, llm, account, monkeypatch):
    account.image_mode = "photo"
    session.add(account)
    session.commit()
    d = await _draft(session, llm, account)
    seen = []

    async def find_photo(queries, want, *, vllm=None, avoid=None, tries=4):
        seen.append((queries, set(avoid or ())))
        if "失败" in queries[0]:
            raise webimg.WebImageError("网上没找到合适的图")
        return _photo(), {"url": "https://img.example.com/a.jpg", "link": "https://example.com/p", "site": "example.com",
                          "title": "便当", "query": queries[0], "engine": "360"}

    monkeypatch.setattr(webimg, "find_photo", find_photo)
    llm.push("image", {"spec": "实拍", "prompts": [
        {"idx": 1, "mode": "photo", "query": ["减脂便当 俯拍"], "layout": {"kind": "cover", "title": "一周便当不重样"}},
        {"idx": 2, "mode": "photo", "query": ["失败的词"], "layout": {"kind": "list", "title": "公式", "items": ["一拳主食"]}},
    ]})
    res = await images_mod.generate_images(session, llm, d.id)
    imgs = _imgs(session, d)
    assert res["done"] == 2 and [i.made_by for i in imgs] == ["photo", "card"]  # 第 2 张没找到图，改成卡片
    assert imgs[0].source["site"] == "example.com" and (get_settings().images_dir / imgs[0].source["base"]).exists()
    assert "fallback" in imgs[1].source

    # 直接改字：按原来的底图重排，不重新找图
    old = imgs[0].path
    draft = session.get(Draft, d.id)
    res = draft_edit.apply_ops(session, draft, [{"op": "text", "no": 1, "layout": {"title": "改过的标题"}}])
    assert res["retexted"] == [1] and res["changed"] == []
    imgs = _imgs(session, d)
    assert imgs[0].layout["title"] == "改过的标题" and imgs[0].path != old and len(seen) == 2


async def test_ai_text_mode_draws_without_text(session, llm, account, monkeypatch):
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    account.image_mode = "mixed"
    session.add(account)
    session.commit()
    d = await _draft(session, llm, account)
    llm.push("image", {"spec": "暖色", "palette": "cream", "prompts": [
        {"idx": 1, "mode": "ai_text", "prompt": "桌上一份便当，上方留白",
         "layout": {"kind": "cover", "title": "存钱便当", "position": "top"}},
        {"idx": 2, "mode": "card", "layout": {"kind": "list", "title": "3个笨办法", "items": ["记账"]}},
    ]})
    res = await images_mod.generate_images(session, llm, d.id)
    imgs = _imgs(session, d)
    assert res["done"] == 2 and [i.made_by for i in imgs] == ["ai_text", "card"]
    assert len(fake.prompts) == 1 and "不要出现任何文字" in fake.prompts[0]  # 卡片不调生图
    assert imgs[0].source["base"].endswith("-base.png")


async def test_mode_and_text_ops(session, llm, account, client, monkeypatch):
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    images_mod.set_provider_factory(lambda: FakeImages())
    d = await _draft(session, llm, account)
    await images_mod.generate_images(session, llm, d.id)
    imgs = _imgs(session, d)
    assert [i.made_by for i in imgs] == ["ai", "ai"]
    # AI 直接画的字改不了，提示换做法
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "text", "no": 1, "layout": {"title": "新"}}]})
    assert r.status_code == 400 and "AI 直接画" in r.json()["detail"]
    # 换成排版卡片：标待出图，派出图任务
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "mode", "no": 2, "mode": "card"}]})
    assert r.status_code == 200, r.text
    got = r.json()["images"]
    assert got[1]["mode"] == "card" and got[1]["status"] == "pending" and got[0]["status"] == "done"
    job = session.exec(select(Job).where(Job.kind == JobKind.generate_images)).one()
    session.delete(job)
    session.commit()
    llm.push("image", {"spec": "", "prompts": [{"idx": 2, "mode": "card", "layout": {"kind": "quote", "title": "存钱是底气"}}]})
    session.expire_all()
    await images_mod.generate_images(session, llm, d.id)
    r = client.get(f"/api/drafts/{d.id}")
    img = r.json()["images"][1]
    assert img["made_by"] == "card" and img["layout"]["kind"] == "quote" and img["url"]
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [
        {"op": "text", "no": 2, "layout": {"title": "存钱是为了有底气", "highlight": "底气"}}]})
    assert r.status_code == 200 and r.json()["images"][1]["layout"]["title"] == "存钱是为了有底气"
    assert not session.exec(select(Job).where(Job.kind == JobKind.generate_images)).all()  # 改字不派任务


def test_account_image_mode_api(client):
    a = client.post("/api/accounts", json={"name": "号"}).json()
    assert a["image_mode"] == "ai"
    r = client.patch(f"/api/accounts/{a['id']}", json={"image_mode": "photo"})
    assert r.status_code == 200 and r.json()["image_mode"] == "photo"
    assert client.patch(f"/api/accounts/{a['id']}", json={"image_mode": "xx"}).status_code == 422


def test_parse_search_results():
    got = webimg.parse_360({"list": [{"img": "https://a.com/1.jpg", "_thumb": "https://t.com/1.jpg", "title": "便当&amp;饭",
                                      "width": "1080", "height": "1440", "site": "a.com", "link": "https://a.com/p"}]})
    assert got[0]["width"] == 1080 and got[0]["title"] == "便当&饭"
    html = ('<a class="iusc" style="" m="{&quot;murl&quot;:&quot;https://b.com/2.jpg&quot;,'
            '&quot;turl&quot;:&quot;https://tse.bing/2&quot;,&quot;purl&quot;:&quot;https://b.com/post&quot;,&quot;t&quot;:&quot;标题&quot;}">')
    got = webimg.parse_bing(html)
    assert got[0]["url"] == "https://b.com/2.jpg" and got[0]["site"] == "b.com"


async def test_manager_sets_image_mode(session, llm, account):
    from mediaflow.agents.manager import Toolbox

    m = Toolbox(session, llm, account, None)
    out = await m.call("update_profile", {"image_mode": "card"})
    assert out["ok"] and "排版" in out["note"]
    session.refresh(account)
    assert account.image_mode == "card"
    out = await m.call("update_profile", {"image_mode": "nope"})
    assert not out["ok"]
