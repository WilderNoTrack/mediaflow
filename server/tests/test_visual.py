"""账号配图模板（看对标的图学出来）+ 出图后看图自检。"""

import io
import json

import pytest
from PIL import Image
from sqlmodel import select

from mediaflow.config import get_settings
from mediaflow.domain.models import Account, Benchmark, BenchmarkStatus, Draft, DraftImage, Job, JobKind
from mediaflow.llm import client as llm_client
from mediaflow.services import images as images_mod
from mediaflow.services import refs as refs_mod
from mediaflow.services import visual
from tests.fakes import FakeImages, FakeLLM, say, tool_call


@pytest.fixture
def vision():
    f = FakeLLM()
    llm_client.set_vision_llm(f)
    return f


@pytest.fixture
def downloads(monkeypatch):
    got = []

    class Resp:
        def __init__(self, color):
            buf = io.BytesIO()
            Image.new("RGB", (60, 80), color).save(buf, "PNG")
            self.content = buf.getvalue()

        def raise_for_status(self):
            pass

    async def fake_get(self, url, **kw):
        got.append(url)
        return Resp((len(got) * 37 % 255, 80, 120))

    monkeypatch.setattr(refs_mod.httpx.AsyncClient, "get", fake_get)
    return got


def _bench(session, account):
    session.add(Benchmark(user_id=account.user_id, account_id=account.id, target="x", status=BenchmarkStatus.ready,
                          creator_name="程十安an", samples=[
                              {"title": "爆款一", "likes": "3万", "kind": "图文", "url": "https://x/1",
                               "images": ["https://ci/p1a", "https://ci/p1b", "https://ci/p1c"]},
                              {"title": "爆款二", "likes": "1万", "kind": "图文", "url": "https://x/2",
                               "images": ["https://ci/p2a", "https://ci/p2b"]},
                              {"title": "只有封面", "likes": "5万", "kind": "图文", "cover": "https://ci/p3a"},
                              {"title": "视频", "likes": "9万", "kind": "视频", "cover": "https://ci/va"}]))
    session.commit()


TEMPLATE = {"spec": "奶油白底、圆润粗黑体、关键词黄色底块、同一个短发女生", "tips": ["封面大字三行内"], "pages": [
    {"type": "清单页", "desc": "白底，左侧序号右侧要点", "when": "干货清单", "examples": [3]},
    {"type": "封面", "desc": "人物半身+三行大字", "when": "每篇第一张", "examples": [1, 6]},
    {"type": "对比页", "desc": "左右两格前后对比", "when": "前后对比", "examples": [2]}]}


async def test_learn_from_benchmarks(session, account, vision, downloads):
    """看对标爆款的图：有全套图的先看封面+内页，再补其他封面；视频不看。模板存进账号，图号换成本地样例图。"""
    _bench(session, account)
    vision.push("visual_learn", TEMPLATE)
    out = await visual.learn(session, account.id)
    assert out["pages"] == ["封面", "清单页", "对比页"]  # 封面排第一
    msg = vision.prompts_of("visual_learn")[0]
    imgs = [x for x in msg if x["type"] == "image_url"]
    text = msg[0]["text"]
    assert len(imgs) == 6 and "图 1：「爆款一」封面" in text and "图 4：「爆款二」封面" in text and "图 6：「只有封面」封面" in text
    assert "https://ci/va" not in downloads
    session.refresh(account)
    v = account.visual
    assert v["spec"].startswith("奶油白底") and v["source"]["names"] == ["程十安an"] and v["source"]["images"] == 6
    cover = v["pages"][0]
    assert len(cover["examples"]) == 2 and all((get_settings().images_dir / e).exists() for e in cover["examples"])
    assert v["pages"][1]["examples"][0] != cover["examples"][0]


async def test_learn_needs_vision(session, account):
    with pytest.raises(visual.VisualError, match="看不了图"):
        await visual.learn(session, account.id)
    await visual.learn_quietly(session, account.id)  # 看不了图：学对标后顺手学模板这步直接跳过，不报错


def _template_on(session, account):
    d = get_settings().images_dir / "_refs"
    d.mkdir(parents=True, exist_ok=True)
    for n in ("cov", "list", "post1", "post2"):
        buf = io.BytesIO()
        Image.new("RGB", (30, 40), "red").save(buf, "JPEG")
        (d / f"{n}.jpg").write_bytes(buf.getvalue())
    account.visual = {"spec": "奶油白底、圆润粗黑体", "pages": [
        {"type": "封面", "desc": "三行大字", "when": "第一张", "examples": ["_refs/cov.jpg"]},
        {"type": "清单页", "desc": "序号+要点", "when": "清单", "examples": ["_refs/list.jpg"]},
        {"type": "实拍细节", "desc": "近景实拍", "when": "细节", "examples": ["_refs/gone.jpg"]}]}
    session.add(account)
    session.commit()


def _draft(session, account, source="benchmark", n=3):
    d = Draft(user_id="local", account_id=account.id, title="t", body="b", original_title="t", original_body="b",
              reference={"title": "原帖", "source": source, "local": ["_refs/post1.jpg", "_refs/post2.jpg"]})
    session.add(d)
    session.commit()
    session.add_all([DraftImage(draft_id=d.id, idx=k, prompt=f"第{k + 1}张") for k in range(n)])
    session.commit()
    return d


async def test_template_drives_images(session, llm, account, monkeypatch):
    """有模板：每张选页型、照该页型的样例做版式（自动挑的参考帖只管文案），先出封面再带封面出其余；写稿也知道有哪几种页。"""
    from mediaflow.agents.context import load_context

    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    _template_on(session, account)
    assert "页型：封面（第一张）；清单页（清单）" in load_context(session, account.id).profile_text()
    d = _draft(session, account)
    llm.push("image", {"spec": "", "prompts": [{"idx": 1, "prompt": "封面p", "type": "封面"},
                                               {"idx": 2, "prompt": "清单p", "type": "清单"},
                                               {"idx": 3, "prompt": "细节p", "type": "实拍细节"}]})
    await images_mod.generate_images(session, llm, d.id)
    p = llm.prompts_of("image")[0]
    assert "账号配图模板" in p and "- 清单页：序号+要点（适合：清单）" in p and '"type": "页型"' in p
    session.refresh(d)
    assert d.image_mold == "template" and d.image_spec == "奶油白底、圆润粗黑体"  # 没给规范就用模板的整体视觉
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    assert [i.page_type for i in imgs] == ["封面", "清单页", "实拍细节"]
    assert [i.ref_path for i in imgs] == ["_refs/cov.jpg", "_refs/list.jpg", ""]  # 样例图没了就不带版式图
    assert len(fake.refs[0]) == 1 and len(fake.refs[1]) == 2 and len(fake.refs[2]) == 1  # 封面先出，其余带上封面

    # 用户自己给的参考帖：配图照它，不用模板
    d2 = _draft(session, account, source="user", n=2)
    await images_mod.generate_images(session, llm, d2.id)
    session.refresh(d2)
    imgs2 = session.exec(select(DraftImage).where(DraftImage.draft_id == d2.id).order_by(DraftImage.idx)).all()
    assert d2.image_mold == "post" and [i.ref_path for i in imgs2] == ["_refs/post1.jpg", "_refs/post2.jpg"]
    assert "账号配图模板" not in llm.prompts_of("image")[-1]


async def test_review_redoes_bad_image(session, llm, account, vision, monkeypatch, client):
    """出图后看一眼：有错字就带着修改要求重出一次，结果记在图上；关掉自检就不看。"""
    from mediaflow import credentials

    monkeypatch.setenv("IMAGE_API_KEY", "x")
    get_settings.cache_clear()
    fake = FakeImages()
    images_mod.set_provider_factory(lambda: fake)
    d = _draft(session, account, n=1)
    d.reference = {}
    session.add(d)
    session.commit()
    vision.push("image_check", {"ok": False, "problems": ["标题「3套」写成了「3奎」"], "fix": "标题文字改成「3套」"},
                {"ok": True, "problems": []})
    await images_mod.generate_images(session, llm, d.id)
    assert fake.n == 2 and "【上一版的问题，这次一定要改掉】标题文字改成「3套」" in fake.prompts[1]
    checks = vision.prompts_of("image_check")
    assert len(checks) == 2 and checks[0][1]["type"] == "image_url"
    img = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id)).one()
    session.refresh(img)
    assert img.review["ok"] and img.review["redone"] and img.review["before"] == ["标题「3套」写成了「3奎」"]
    body = client.get(f"/api/drafts/{d.id}").json()
    assert body["images"][0]["review"]["redone"] is True

    credentials.update({"image_check": "off"})
    await images_mod.generate_images(session, llm, d.id, only_idx=0)
    assert fake.n == 3 and len(vision.prompts_of("image_check")) == 2
    credentials.update({"image_check": ""})


async def test_visual_api(client, session, account, vision, downloads):
    """接口：没对标学不了；学是后台任务；手动改页型（改名沿用样例）、删页型、清空。"""
    r = client.post(f"/api/accounts/{account.id}/visual/learn", json={})
    assert r.status_code == 400 and "对标" in r.json()["detail"]
    _bench(session, account)
    r = client.post(f"/api/accounts/{account.id}/visual/learn", json={})
    assert r.status_code == 202 and r.json()["kind"] == "learn_visual"
    from mediaflow.jobs.queue import run_job

    vision.push("visual_learn", TEMPLATE)
    await run_job(r.json()["id"])
    acc = client.get(f"/api/accounts/{account.id}").json()
    assert [p["type"] for p in acc["visual"]["pages"]] == ["封面", "清单页", "对比页"]
    ex = acc["visual"]["pages"][1]["examples"]
    r = client.patch(f"/api/accounts/{account.id}/visual", json={"spec": "莫兰迪蓝", "pages": [
        {"type": "封面", "desc": "大字"}, {"type": "要点清单", "from": "清单页", "desc": "序号"}]})
    assert r.status_code == 200
    v = r.json()["visual"]
    assert v["spec"] == "莫兰迪蓝" and [p["type"] for p in v["pages"]] == ["封面", "要点清单"] and v["pages"][1]["examples"] == ex
    assert client.patch(f"/api/accounts/{account.id}/visual", json={"pages": []}).status_code == 400
    assert client.delete(f"/api/accounts/{account.id}/visual").json()["visual"] == {}
    assert client.get("/api/system").json()["vision_available"] is True


async def test_manager_visual_tools(client, session, llm, account, vision):
    """小媒：「封面别放人」改模板（样例按页型名沿用）；「照这几篇的图来」学模板。"""
    _template_on(session, account)
    llm.push("manager", tool_call("update_visual", instruction="封面别放人，换成纯大字"), say("改好了"))
    llm.push("visual_update", {"spec": "奶油白底、圆润粗黑体、不出现人物", "changed": "封面去掉人物",
                               "pages": [{"type": "封面", "desc": "纯大字三行"}, {"type": "清单页", "desc": "序号+要点"}]})
    r = client.post(f"/api/accounts/{account.id}/chat", json={"text": "封面别放人了"})
    assert r.status_code == 200
    sys_prompt = llm.calls[0][1][0]["content"]
    assert "清单页：清单" in sys_prompt  # 账号状态里有模板
    session.refresh(account)
    assert account.visual["spec"].endswith("不出现人物")
    assert account.visual["pages"][0]["examples"] == ["_refs/cov.jpg"] and len(account.visual["pages"]) == 2

    llm.push("manager", tool_call("learn_visual", links="https://www.xiaohongshu.com/explore/abc 看这篇"), say("在学了"))
    r = client.post(f"/api/accounts/{account.id}/chat", json={"text": "照这篇的图来 https://www.xiaohongshu.com/explore/abc"})
    job = session.exec(select(Job).where(Job.kind == JobKind.learn_visual)).one()
    assert job.payload["links"] == ["https://www.xiaohongshu.com/explore/abc"]


def test_image_note_tells_reviewer_images_follow_reference():
    from mediaflow.agents.pipeline import _image_note

    assert _image_note({}) == ""
    assert _image_note({"title": "没拿到图的参考帖"}) == ""
    note = _image_note({"title": "x", "local": ["a", "b"], "look": {"pages": [{"kind": "illustration"}, {"kind": "illustration"}]}})
    assert "2 张原图" in note and "漫画" in note and "不算问题" in note
    assert "样板帖" in _image_note({"title": "样板", "source": "exemplar", "plan": [{}, {}, {}]})
