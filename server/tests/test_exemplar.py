"""样板帖：起号时先打磨好一篇，之后每篇都以它为主参考（写法 + 配图的做法、版式、配色）；对标爆款只当内容参考。"""

import io

import pytest
from PIL import Image
from sqlmodel import select

from mediaflow.agents.manager import Toolbox
from mediaflow.agents.pipeline import write_draft
from mediaflow.config import get_settings
from mediaflow.domain.models import Benchmark, BenchmarkStatus, Draft, DraftImage, ImageStatus, Topic
from mediaflow.research import service as research
from mediaflow.services import benchmark as bench
from mediaflow.services import exemplar, layout, refpost
from mediaflow.services import images as images_mod
from tests.fakes import FakeImages, FakeLLM, evaluation, fake_fetch, post


def _png(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), color).save(buf, "PNG")
    return buf.getvalue()


def _polished(session, account) -> Draft:
    """用户打磨好的一篇：封面排版卡片、第 2 张 AI 画、第 3 张清单卡片，薄荷绿配色。"""
    d = Draft(user_id=account.user_id, account_id=account.id, title="通勤穿搭公式｜3件搞定一周",
              body="姐妹们！上班穿什么不用愁了👇\n1️⃣ 西装外套\n2️⃣ 直筒裤\n3️⃣ 乐福鞋", tags=["通勤穿搭", "穿搭公式"],
              original_title="t", original_body="b", image_spec="薄荷绿底、圆润黑体、同一个短发女生")
    session.add(d)
    session.flush()
    out = get_settings().images_dir / d.id
    out.mkdir(parents=True, exist_ok=True)
    specs = [("card", {"kind": "cover", "title": "3件搞定一周", "palette": "mint", "position": "top"}),
             ("ai", {}), ("card", {"kind": "list", "title": "公式", "items": ["西装", "直筒裤"], "palette": "mint"})]
    for i, (made_by, lay) in enumerate(specs):
        (out / f"{i:02d}.png").write_bytes(_png(["white", "teal", "pink"][i]))
        session.add(DraftImage(draft_id=d.id, idx=i, prompt=f"样板第{i + 1}张", status=ImageStatus.done,
                               path=f"{d.id}/{i:02d}.png", made_by=made_by, layout=lay))
    session.commit()
    return d


def _imgs(session, d):
    session.expire_all()
    return session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()


@pytest.mark.skipif(not layout.available(), reason="没有中文字体")
async def test_exemplar_drives_writing_and_images(session, llm, account, client, monkeypatch):
    ex = _polished(session, account)
    r = client.put(f"/api/accounts/{account.id}/exemplar", json={"draft_id": ex.id})
    assert r.status_code == 200 and r.json()["exemplar"]["images"] == 3 and r.json()["exemplar"]["title"] == ex.title
    session.add(Topic(user_id=account.user_id, account_id=account.id, title="一周通勤不重样", source="benchmark",
                      reference={"title": "原爆款：7天通勤穿搭", "content": "原文内容", "creator": "某博主", "likes": "1万"}))
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    session.refresh(account)
    account.image_mode = "auto"
    session.add(account)
    session.commit()

    llm.push("writer", post(images=["封面：标题「一周不重样」", "上身图", "清单：「周一」「周二」"]))
    llm.push("eval", evaluation(8))
    d = await write_draft(session, llm, account.id, fetch=fake_fetch)
    prompt = llm.prompts_of("writer")[0]
    assert "【样板帖" in prompt and "通勤穿搭公式｜3件搞定一周" in prompt and "样板帖有 3 张图" in prompt
    assert "原爆款：7天通勤穿搭" in prompt.split("【其他参考帖")[1]  # 原爆款只当内容参考
    assert d.reference["source"] == "exemplar" and d.reference["extra"][0]["title"] == "原爆款：7天通勤穿搭"

    # 模型想换别的做法、别的配色也不行：每张照样板对应那张
    llm.push("image", {"spec": "别的风格", "palette": "pink", "prompts": [
        {"idx": 1, "mode": "photo", "layout": {"title": "一周不重样"}},
        {"idx": 2, "mode": "card", "prompt": "上身全身照", "layout": {"title": "x"}},
        {"idx": 3, "mode": "ai", "layout": {"title": "清单", "items": ["周一", "周二"]}},
    ]})
    res = await images_mod.generate_images(session, llm, d.id)
    imgs = _imgs(session, d)
    assert res["done"] == 3 and [i.made_by for i in imgs] == ["card", "ai", "card"]
    assert imgs[0].layout["kind"] == "cover" and imgs[0].layout["position"] == "top" and imgs[2].layout["kind"] == "list"
    assert {imgs[0].layout["palette"], imgs[2].layout["palette"]} == {"mint"}
    assert session.get(Draft, d.id).image_spec == "薄荷绿底、圆润黑体、同一个短发女生"  # 视觉规范沿用样板的
    assert len(fake.prompts) == 1 and fake.refs[0] and "严格照着参考图的版式" in fake.prompts[0]  # 只有第 2 张调生图
    assert imgs[1].ref_path.startswith("_refs/own-")  # 样板那张转成了版式模板
    assert "照样板帖做" in llm.prompts_of("image")[-1]


def test_exemplar_images_refreshed_at_image_time(session, account):
    """写这篇时样板的图还没出好（或后来改过）：出图前按样板现在的图来。"""
    ex = _polished(session, account)
    stale = {"title": ex.title, "source": "exemplar", "draft_id": ex.id, "local": [], "plan": [], "image_spec": ""}
    fresh = exemplar.refresh(session, stale)
    assert len(fresh["local"]) == 3 and [p["made_by"] for p in fresh["plan"]] == ["card", "ai", "card"]
    assert fresh["image_spec"] == "薄荷绿底、圆润黑体、同一个短发女生"
    assert exemplar.refresh(session, {**stale, "draft_id": "gone"})["local"] == []  # 样板删了：保持原样
    assert exemplar.refresh(session, {"source": "user", "local": []}) == {"source": "user", "local": []}


async def test_reference_only_write_takes_topic_from_post(session, llm, account, monkeypatch):
    got = {"title": "别人的爆款：小个子通勤", "url": "https://www.xiaohongshu.com/explore/abc", "content": "原文",
           "source": "user", "why": "你指定的参考帖", "extra": []}

    async def from_links(text):
        return dict(got)

    monkeypatch.setattr(refpost, "from_links", from_links)
    llm.push("writer", post())
    llm.push("eval", evaluation(8))
    d = await write_draft(session, llm, account.id, reference_url=got["url"], fetch=fake_fetch)
    t = session.get(Topic, d.topic_id)
    assert t.title == got["title"] and t.source == "reference"
    assert d.reference["title"] == got["title"] and "别人的爆款：小个子通勤" in llm.prompts_of("writer")[0]

    # 有样板帖后：给的链接只当文案参考；明说不照样板帖就不照
    ex = _polished(session, account)
    exemplar.set_(session, account, ex)
    llm.push("writer", post(), post())
    llm.push("eval", evaluation(8), evaluation(8))
    d2 = await write_draft(session, llm, account.id, reference_url=got["url"], fetch=fake_fetch)
    assert d2.reference["source"] == "exemplar" and d2.reference["extra"][0]["title"] == got["title"]
    d3 = await write_draft(session, llm, account.id, hint="试个新风格", use_exemplar=False, fetch=fake_fetch)
    assert (d3.reference or {}).get("source") != "exemplar"


@pytest.mark.skipif(not layout.available(), reason="没有中文字体")
async def test_reference_images_are_read_and_followed(session, llm, account, monkeypatch):
    """照别人的帖子写：先看懂每张原图怎么做的（漫画 / 没字的实拍 / 文字卡片），写稿和出图都照着挑做法。"""
    from mediaflow.llm import client as llm_client

    root = get_settings().images_dir / "_refs"
    root.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(["purple", "green", "white"]):
        (root / f"o{i}.jpg").write_bytes(_png(c))
    got = {"title": "会接话的重要性", "url": "https://www.xiaohongshu.com/explore/abc", "content": "原文", "source": "user",
           "why": "你指定的参考帖", "extra": [], "local": [f"_refs/o{i}.jpg" for i in range(3)]}

    async def from_links(text):
        return dict(got)

    monkeypatch.setattr(refpost, "from_links", from_links)
    vision = FakeLLM()
    llm_client.set_vision_llm(vision)
    vision.push("look", {"spec": "淡紫底、橙色袈裟的Q版小和尚、黑色粗体字", "pages": [
        {"no": 1, "kind": "illustration", "text": "few", "desc": "上下两格漫画，每格顶部一行黑字"},
        {"no": 2, "kind": "photo", "text": "none", "desc": "窗边实拍，没有字"},
        {"no": 3, "kind": "card", "text": "many", "desc": "白底清单卡片"},
        {"no": 9, "kind": "x"}]})
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    account.image_mode = "auto"
    session.add(account)
    session.commit()

    llm.push("writer", post(images=["两格漫画：「同事夸你」", "窗边实拍", "清单：「三句话」"]))
    llm.push("eval", evaluation(8))
    d = await write_draft(session, llm, account.id, reference_url=got["url"], fetch=fake_fetch)
    look = d.reference["look"]
    assert [p["kind"] for p in look["pages"]] == ["illustration", "photo", "card"] and "小和尚" in look["spec"]
    w = llm.prompts_of("writer")[0]
    assert "原帖每张图是这样做的" in w and "第 1 张：插画/漫画，字少：上下两格漫画" in w and "第 2 张：实拍照片，没字" in w

    llm_client.set_vision_llm(None)  # 出图这步不测自检
    # 模型想把漫画做成卡片、实拍用 AI 画面排字：漫画只能 AI 画整张，实拍只能找图 / AI 画，给 none 就不排字
    llm.push("image", {"spec": "淡紫底小和尚", "palette": "cream", "prompts": [
        {"idx": 1, "mode": "card", "prompt": "两格漫画", "layout": {"title": "同事夸你"}},
        {"idx": 2, "mode": "ai_text", "prompt": "窗边实拍", "layout": {"kind": "none"}},
        {"idx": 3, "mode": "card", "layout": {"kind": "list", "title": "三句话", "items": ["一", "二", "三"]}},
    ]})
    res = await images_mod.generate_images(session, llm, d.id)
    imgs = _imgs(session, d)
    assert res["done"] == 3 and [i.made_by for i in imgs] == ["ai", "photo", "card"]  # 实拍不给 ai_text：找真实照片
    assert imgs[1].layout["kind"] == "none" and imgs[2].layout["kind"] == "list"
    p = llm.prompts_of("image")[-1]
    assert "原帖的图是这样做的" in p and "上下两格漫画" in p and "淡紫底" in p
    assert "第 1 张 ai；" in p  # 漫画那张只给 AI 画整张

    # 定为样板帖后：样板每张带上原型的做法
    ex_ref = exemplar.refresh(session, {"source": "exemplar", "draft_id": d.id, "local": []})
    assert ex_ref["plan"][0]["look"].startswith("插画/漫画")


async def test_manager_exemplar_tools(session, llm, account, client, monkeypatch):
    ex = _polished(session, account)
    tb = Toolbox(session, llm, account, None, draft_id=ex.id)
    assert "还没有样板帖" in str(tb.snapshot()["exemplar"])
    r = await tb.call("set_exemplar", {})
    assert r["ok"] and r["exemplar"]["draft_id"] == ex.id and r["exemplar"]["images"] == 3
    assert tb.snapshot()["exemplar"]["title"] == ex.title

    async def hot(platform, keyword):
        assert platform == "xiaohongshu" and keyword == "通勤穿搭"
        return [{"title": "视频不要", "url": "u0", "likes": "9万", "kind": "视频"},
                {"title": "赞少的", "url": "u1", "likes": "300", "kind": "图文", "name": "A", "cover": "c1"},
                {"title": "赞多的", "url": "u2", "likes": "1.2万", "kind": "图文", "name": "B", "cover": "c2"},
                {"title": "赞多的", "url": "u2", "likes": "1.2万", "kind": "图文", "name": "B"}]

    monkeypatch.setattr(research, "hot_authors_raw", hot)
    r = await tb.call("find_posts", {"query": "通勤穿搭"})
    assert [p["title"] for p in r["posts"]] == ["赞多的", "赞少的"] and r["posts"][0]["url"] == "u2"

    # 删了样板帖那篇草稿，账号就没有样板帖了
    assert client.delete(f"/api/drafts/{ex.id}").status_code == 204
    session.expire_all()
    assert exemplar.info(session, session.get(type(account), account.id)) == {}
    assert (await tb.call("set_exemplar", {"clear": True}))["cleared"]


def test_benchmark_topics_and_hits_alternate(session, account):
    """对标了好几个号：复刻选题轮流照每个人的爆款排，参考帖候选也轮流取，不会全是赞最多那个人的。"""
    a = Benchmark(user_id=account.user_id, account_id=account.id, creator_name="大号A", status=BenchmarkStatus.ready,
                  samples=[{"title": f"A爆款{i}", "likes": f"{9 - i}万", "cover": "c", "kind": "图文"} for i in range(5)])
    b = Benchmark(user_id=account.user_id, account_id=account.id, creator_name="小号B", status=BenchmarkStatus.ready,
                  samples=[{"title": f"B爆款{i}", "likes": str(500 - i), "cover": "c", "kind": "图文"} for i in range(3)])
    session.add(a)
    session.add(b)
    session.commit()
    plan = {"topics": [{"title": "选题甲", "ref": "A1"}, {"title": "选题乙", "ref": "A2"}, {"title": "选题丙", "ref": "A3"},
                       {"title": "选题丁", "ref": "B1"}, {"title": "选题戊", "ref": "B2"}]}
    applied = bench._apply(session, [a, b], account, plan, "通勤穿搭")
    assert applied["topics"] == ["选题甲", "选题丁", "选题乙", "选题戊", "选题丙"]
    names = [x["creator"] for x in refpost._samples(session, account.id)[:4]]
    assert names == ["大号A", "小号B", "大号A", "小号B"]


def test_lone_bullet_before_question_is_dropped():
    from mediaflow.agents.manager import _unbullet

    assert _unbullet("看了几个号。\n\n- 你更想做成哪种？") == "看了几个号。\n\n你更想做成哪种？"
    keep = "两个方向：\n- 日常\n- 干货\n\n选哪个？"
    assert _unbullet(keep) == keep
