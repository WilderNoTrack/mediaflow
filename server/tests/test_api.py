import io
import zipfile

from sqlmodel import select

from mediaflow.domain.models import Draft, DraftStatus, Job, Rule
from tests.fakes import evaluation, post, say, tool_call


def make_account(client, **kw):
    r = client.post("/api/accounts", json={"name": "小鹿穿搭", "theme": "学生党平价穿搭", **kw})
    assert r.status_code == 201
    return r.json()


def test_account_crud_and_rules(client):
    a = make_account(client)
    r = client.patch(f"/api/accounts/{a['id']}", json={"image_style": "胶片感", "auto_enabled": True})
    assert r.json()["image_style"] == "胶片感" and r.json()["auto_enabled"]
    rule = client.post(f"/api/accounts/{a['id']}/rules", json={"text": "不用感叹号"}).json()
    assert client.get(f"/api/accounts/{a['id']}").json()["rules"][0]["text"] == "不用感叹号"
    assert client.delete(f"/api/accounts/{a['id']}/rules/{rule['id']}").status_code == 204
    assert client.get(f"/api/accounts/{a['id']}").json()["rules"] == []
    from mediaflow.db import get_engine
    from mediaflow.domain.models import Note
    from sqlmodel import Session
    with Session(get_engine()) as s:
        n = Note(user_id="local", account_id=a["id"], title="对标：某博主", content="标题爱用数字")
        s.add(n)
        s.commit()
        nid = n.id
    assert client.get(f"/api/accounts/{a['id']}").json()["notes"][0]["title"] == "对标：某博主"
    assert client.delete(f"/api/accounts/{a['id']}/notes/{nid}").status_code == 204
    assert client.get(f"/api/accounts/{a['id']}").json()["notes"] == []
    assert client.get("/api/accounts").json()[0]["pending_review"] == 0
    assert client.delete(f"/api/accounts/{a['id']}").status_code == 204
    assert client.get(f"/api/accounts/{a['id']}").status_code == 404


def test_write_conflict_returns_409(client):
    a = make_account(client)
    assert client.post(f"/api/accounts/{a['id']}/write", json={}).status_code == 202
    r = client.post(f"/api/accounts/{a['id']}/write", json={})
    assert r.status_code == 409 and r.json()["job_id"]


async def _make_draft(session, llm, account_id):
    from mediaflow.agents.pipeline import write_draft
    from tests.fakes import fake_fetch

    llm.push("writer", post()).push("eval", evaluation(8))
    return await write_draft(session, llm, account_id, fetch=fake_fetch)


async def test_draft_edit_feedback_learn_export(client, session, llm):
    a = make_account(client)
    session.add(Rule(user_id="local", account_id=a["id"], text="已有规则"))
    session.commit()
    d = await _make_draft(session, llm, a["id"])

    r = client.patch(f"/api/drafts/{d.id}", json={"title": "这" * 25, "tags": ["#穿搭", "穿搭", "通勤", "平价"]})
    body = r.json()
    assert body["edited"] and body["tags"] == ["穿搭", "通勤", "平价"]
    assert any("标题 25 字" in i for i in body["check_issues"])  # 改完重新检查
    assert body["original_title"] == "通勤穿搭3个小心机"

    client.post(f"/api/drafts/{d.id}/feedback", json={"rating": "good", "comment": "开头更口语就好了"})
    assert client.get(f"/api/drafts/{d.id}").json()["status"] == "approved"

    llm.push("learn", {"rules": ["已有规则", "开头用一句口语化的感叹"], "summary": "喜欢口语化开头"})
    learned = client.post(f"/api/drafts/{d.id}/learn").json()
    assert learned["rules"] == ["开头用一句口语化的感叹"]  # 去掉已存在的
    assert "喜欢口语化开头" in learned["summary"]

    text = client.get(f"/api/drafts/{d.id}/text").json()["text"]
    assert "#穿搭" in text
    r = client.get(f"/api/drafts/{d.id}/export")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "文案.txt" in names
    session.expire_all()
    assert session.get(Draft, d.id).status == DraftStatus.exported
    assert client.get(f"/api/accounts/{a['id']}/drafts?status=exported").json()[0]["id"] == d.id


def test_chat_endpoint_and_history(client, llm, session):
    a = make_account(client)
    llm.push("manager", tool_call("write_post"), say("在写了"))
    msgs = client.post(f"/api/accounts/{a['id']}/chat", json={"text": "来一篇"}).json()
    assert [m["role"] for m in msgs] == ["user", "tool", "assistant"]
    assert len(client.get(f"/api/accounts/{a['id']}/chat").json()) == 3
    job = session.exec(select(Job)).one()
    assert client.get(f"/api/jobs/{job.id}").json()["kind"] == "write_draft"
    assert client.get(f"/api/jobs?account_id={a['id']}&active=true").json()[0]["id"] == job.id


def test_topic_search_endpoint(client, llm):
    a = make_account(client)
    r = client.post(f"/api/accounts/{a['id']}/topics/search", json={"direction": "秋季"}).json()
    assert r["topics"] and any(not s["ok"] for s in r["sources"]) and r["note"]
    t = r["topics"][0]
    assert client.patch(f"/api/accounts/{a['id']}/topics/{t['id']}", json={"status": "dismissed"}).json()["status"] == "dismissed"


def test_system_status(client):
    s = client.get("/api/system").json()
    assert s["llm_configured"] and not s["image_configured"]


def test_image_settings_saved_from_ui(client):
    r = client.get("/api/settings/image").json()
    assert not r["configured"] and r["model"] == "gpt-image-2.5" and {m["id"] for m in r["models"]} >= {"gpt-image-2.5", "nano-banana-2.1"}
    assert client.put("/api/settings/image", json={"model": "dall-e"}).status_code == 400
    r = client.put("/api/settings/image", json={"api_key": "sk-test", "model": "nano-banana-2.1"}).json()
    assert r["configured"] and r["origin"] == "ui" and r["model"] == "nano-banana-2.1"
    assert client.get("/api/system").json()["image_configured"]
    assert all(c["key"] != "image_api_key" for c in client.get("/api/settings/credentials").json())
    r = client.put("/api/settings/image", json={"api_key": "", "model": ""}).json()
    assert not r["configured"] and r["model"] == "gpt-image-2.5"


async def test_images_not_generated_twice_and_recovered_after_restart(client, session, llm):
    from mediaflow.domain.models import DraftImage, ImageStatus
    from mediaflow.jobs.queue import recover_interrupted

    a = make_account(client)
    d = await _make_draft(session, llm, a["id"])
    out = client.get(f"/api/drafts/{d.id}").json()
    assert out["images_total"] == 2 and out["images_busy"] == 0  # 没配 Key：skipped
    j1 = client.post(f"/api/drafts/{d.id}/images").json()
    j2 = client.post(f"/api/drafts/{d.id}/images").json()
    assert j1["id"] == j2["id"]  # 正在出就不再派第二个任务
    assert client.get(f"/api/accounts/{a['id']}/drafts").json()[0]["images_busy"] == 2

    session.expire_all()
    img = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id, DraftImage.idx == 0)).one()
    img.status = ImageStatus.running
    session.add(img)
    session.commit()
    recover_interrupted()  # 任务还在排队：pending 的留给它，running 的标失败
    session.expire_all()
    st = {i.idx: i.status for i in session.exec(select(DraftImage).where(DraftImage.draft_id == d.id)).all()}
    assert st == {0: ImageStatus.failed, 1: ImageStatus.pending}


def test_write_from_chat_is_logged_in_chat(client):
    a = client.post("/api/accounts", json={"name": "宝妈省钱", "theme": "带娃省钱"}).json()
    j = client.post(f"/api/accounts/{a['id']}/write", json={"from_chat": True}).json()
    msgs = client.get(f"/api/accounts/{a['id']}/chat").json()
    assert msgs[-1]["role"] == "tool" and msgs[-1]["tool_name"] == "write_post"
    assert msgs[-1]["payload"]["result"]["job_id"] == j["id"]
    b = client.post("/api/accounts", json={"name": "b", "theme": "t"}).json()
    client.post(f"/api/accounts/{b['id']}/write", json={})
    assert client.get(f"/api/accounts/{b['id']}/chat").json() == []


def test_llm_key_from_ui(client, monkeypatch):
    from mediaflow.llm import client as llm_client
    from mediaflow.llm.client import LLMError

    seen = []

    async def fake_complete(self, messages, **kw):
        seen.append(self.client.api_key)
        if self.client.api_key != "sk-good":
            raise LLMError("DeepSeek 调用失败：Error code: 401 - Authentication Fails")
        return llm_client.LLMResponse(content="好")

    monkeypatch.setattr(llm_client.DeepSeekLLM, "complete", fake_complete)
    from mediaflow.config import get_settings

    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/api/settings/llm").json()["configured"] is False
    r = client.put("/api/settings/llm", json={"api_key": "sk-bad"})
    assert r.status_code == 400 and "Key 不对" in r.json()["detail"]
    assert client.get("/api/settings/llm").json()["configured"] is False
    out = client.put("/api/settings/llm", json={"api_key": " sk-good "}).json()
    assert out["configured"] is True and out["origin"] == "ui" and out["order"] == ["deepseek"]
    assert llm_client.llm_key() == "sk-good" and client.get("/api/system").json()["llm_configured"] is True
    assert client.post("/api/settings/llm/test", json={"api_key": ""}).json()["ok"] is True  # 不传就测已保存的
    assert seen == ["sk-bad", "sk-good", "sk-good"]
    assert client.put("/api/settings/llm", json={"api_key": ""}).json()["configured"] is False


async def test_set_reference_and_user_links(client, session, llm, monkeypatch):
    """用户给好几篇链接：第一篇图文当主参考帖（配图照它），其余（视频也行）只给文案参考；读不到的那篇直接报原因。
    草稿页换配图参考：只换主参考帖、清掉统一规范，文案参考不动。"""
    from mediaflow.agents.pipeline import write_draft
    from mediaflow.domain.models import Topic
    from mediaflow.services import refpost

    async def detail(url, need_images=True):
        if "bad" in url:
            raise refpost.RefError("这不是小红书笔记链接（要笔记页的链接，不是主页）")
        if "vid" in url:
            if need_images:
                raise refpost.RefError("这篇是视频笔记，没有图可以照着做，换一篇图文笔记")
            return {"title": "视频爆款讲通勤", "url": url, "creator": "小B", "likes": "9万", "content": "视频文案",
                    "tags": [], "images": [], "cover": "https://ci/v", "kind": "视频"}
        name = url.rsplit("/", 1)[-1]
        return {"title": f"图文{name}", "url": url, "creator": "小A", "likes": "2.3万", "content": "正文",
                "tags": ["通勤"], "images": ["https://ci/1", "https://ci/2"], "cover": "https://ci/1", "kind": "图文"}

    async def cache(urls):
        return [f"_refs/{u[-1]}.jpg" for u in urls]

    monkeypatch.setattr(refpost, "_detail", detail)
    monkeypatch.setattr(refpost, "cache_local", cache)
    a = make_account(client)
    t1, t2, t3 = (Topic(user_id="local", account_id=a["id"], title=x) for x in ("早八5分钟通勤妆", "周末约会穿搭", "秋冬叠穿"))
    session.add_all([t1, t2, t3])
    session.commit()

    llm.push("writer", post()).push("eval", evaluation(8.5))
    share = ("先看这篇视频 https://www.xiaohongshu.com/explore/vid?xsec_token=1 复制本条信息，打开【小红书】App查看！\n"
             "配图照这篇 http://xhslink.com/a/xyz，还有 https://www.xiaohongshu.com/explore/abc")
    d = await write_draft(session, llm, a["id"], topic_id=t1.id, reference_url=share)
    ref = d.reference
    assert ref["title"] == "图文xyz" and ref["local"] == ["_refs/1.jpg", "_refs/2.jpg"]  # 视频排后面，第一篇图文当配图模板
    assert [x["title"] for x in ref["extra"]] == ["视频爆款讲通勤", "图文abc"] and "local" not in ref["extra"][0]
    w = llm.prompts_of("writer")[-1]
    assert "参考帖（3 篇）" in w and "主参考帖，配图也照它" in w and "视频文案" in w

    r = client.put(f"/api/drafts/{d.id}/reference", json={"url": "https://www.xiaohongshu.com/explore/new"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reference"]["title"] == "图文new" and body["reference"]["source"] == "user"
    assert [x["title"] for x in body["reference"]["extra"]] == ["视频爆款讲通勤", "图文abc"] and body["image_spec"] == ""
    assert [i["ref_url"] for i in body["images"]][:2] == ["/files/images/_refs/1.jpg", "/files/images/_refs/2.jpg"]
    r = client.put(f"/api/drafts/{d.id}/reference", json={"url": "https://www.xiaohongshu.com/explore/vid"})
    assert r.status_code == 400 and "视频笔记" in r.json()["detail"]

    for bad, msg in (("https://x.com/abc https://xhslink.com/bad", "第 2 个链接"),
                     ("https://www.xiaohongshu.com/explore/vid", "至少给一篇图文笔记")):
        try:
            await write_draft(session, llm, a["id"], topic_id=t2.id, reference_url=bad)
            raise AssertionError("用户给的链接用不了要报错")
        except ValueError as e:
            assert msg in str(e), str(e)


def _sse(r) -> list[dict]:
    import json

    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def test_chat_stream_events_and_persisted_steps(client, llm):
    """流式对话：先吐用户消息，再是思考/工具步骤（带用时），回复逐字出，最后存进对话（payload 里有步骤和总用时）。"""
    from mediaflow.llm.client import LLMResponse, ToolCall

    a = make_account(client)
    two = LLMResponse(content="我先记一下", tool_calls=[
        ToolCall(id="c1", name="add_rule", arguments={"text": "不用感叹号"}),
        ToolCall(id="c2", name="list_drafts", arguments={})])
    llm.push("manager", two, say("记好了，以后不用感叹号"))
    r = client.post(f"/api/accounts/{a['id']}/chat/stream", json={"text": "以后别用感叹号"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _sse(r)
    types = [e["type"] for e in evs]
    assert types[0] == "user" and types[-2:] == ["message", "done"]
    starts = [e for e in evs if e["type"] == "step_start"]
    assert [s["kind"] for s in starts] == ["thinking", "tool", "tool", "thinking"]
    assert starts[1]["name"] == "add_rule" and starts[1]["args"] == {"text": "不用感叹号"}
    assert any(e["type"] == "note" and e["text"] == "我先记一下" for e in evs)
    assert len([e for e in evs if e["type"] == "tool_message"]) == 2
    assert "".join(e["text"] for e in evs if e["type"] == "delta").endswith("记好了，以后不用感叹号")
    final = evs[-2]["message"]
    assert final["content"] == "记好了，以后不用感叹号" and final["payload"]["ms"] >= 0
    kinds = [s["kind"] for s in final["payload"]["steps"]]
    assert kinds == ["thinking", "note", "tool", "tool", "thinking"]
    tool = final["payload"]["steps"][2]
    assert tool["ok"] and tool["message_id"] and "ms" in tool

    hist = client.get(f"/api/accounts/{a['id']}/chat").json()
    assert [m["role"] for m in hist] == ["user", "tool", "tool", "assistant"]
    assert hist[-1]["payload"]["steps"] == final["payload"]["steps"]
    assert client.get(f"/api/accounts/{a['id']}").json()["rules"][0]["text"] == "不用感叹号"


def test_chat_stream_llm_error_still_answers(client, llm):
    from tests.fakes import fail

    a = make_account(client)
    llm.push("manager", fail("超时"))
    evs = _sse(client.post(f"/api/accounts/{a['id']}/chat/stream", json={"text": "在吗"}))
    assert evs[-1]["type"] == "done" and "连不上 AI 服务" in evs[-2]["message"]["content"]


async def test_edit_images_ops(client, session, llm):
    """改配图：编号按改之前的顺序；改过的、新加的、要重出的标成待出图并派出图任务，其余不动。"""
    from mediaflow.domain.models import DraftImage, ImageStatus, JobKind

    a = make_account(client)
    d = await _make_draft(session, llm, a["id"])
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    for i in imgs:
        i.status, i.path = ImageStatus.done, f"{d.id}/{i.idx}.png"
        session.add(i)
    session.commit()
    before = [i.prompt for i in imgs]
    assert len(before) == 2
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [
        {"op": "update", "no": 2, "description": "三套穿搭对比拼图"},
        {"op": "add", "after": 1, "description": "单品清单"},
        {"op": "add", "after": 0, "description": "新封面"},
        {"op": "move", "no": 1, "to": 4},
    ]})
    assert r.status_code == 200, r.text
    got = r.json()["images"]
    assert [i["prompt"] for i in got] == ["新封面", "单品清单", "三套穿搭对比拼图", before[0]]
    assert [i["status"] for i in got] == ["pending", "pending", "pending", "done"]
    jobs = session.exec(select(Job).where(Job.kind == JobKind.generate_images)).all()
    assert len(jobs) == 1 and jobs[0].payload["draft_id"] == d.id

    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "remove", "no": 1}]})
    assert r.status_code == 409 and "正在出图" in r.json()["detail"]  # 上一轮还没出完
    session.delete(jobs[0])
    session.commit()
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "remove", "no": 9}]})
    assert r.status_code == 400 and "没有第 9 张" in r.json()["detail"]
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "remove", "no": 1}, {"op": "redo", "no": 4}],
                                                         "regenerate": False})
    assert [(i["idx"], i["prompt"], i["status"]) for i in r.json()["images"]] == [
        (0, "单品清单", "pending"), (1, "三套穿搭对比拼图", "pending"), (2, before[0], "pending")]
    r = client.post(f"/api/drafts/{d.id}/images/edit", json={"ops": [{"op": "remove", "no": k} for k in (1, 2, 3)]})
    assert r.status_code == 400 and "至少要留一张" in r.json()["detail"]


async def test_chat_edits_current_draft_images(client, session, llm):
    """在草稿页跟小媒说「第二张换成…」：上下文里有这篇的每张图，小媒调 edit_images 直接改。"""
    from mediaflow.domain.models import DraftImage

    a = make_account(client)
    d = await _make_draft(session, llm, a["id"])
    llm.push("manager", tool_call("edit_images", ops=[{"op": "update", "no": 2, "description": "三套穿搭对比拼图，每格标 Look1/2/3"}]),
             say("第 2 张换成对比拼图了，正在重新出"))
    r = client.post(f"/api/accounts/{a['id']}/chat", json={"text": "第二张换成三套穿搭的对比拼图", "draft_id": d.id})
    assert r.status_code == 200, r.text
    sys = llm.calls[-2][1][0]["content"]
    assert "用户正在看的草稿" in sys and d.id in sys and '"no": 2' in sys
    img = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id, DraftImage.idx == 1)).one()
    session.refresh(img)
    assert img.prompt.startswith("三套穿搭对比拼图")
    tool = [m for m in r.json() if m["role"] == "tool"][0]
    assert tool["tool_name"] == "edit_images" and tool["payload"]["result"]["changed"] == [2]
    assert r.json()[0]["payload"]["draft_id"] == d.id


async def test_write_with_image_plan(session, llm, account):
    """用户写稿时说了每张图要什么：写稿提示里带上，张数按用户的，漏写的直接用原话。"""
    from mediaflow.agents.pipeline import write_draft
    from mediaflow.domain.models import DraftImage
    from tests.fakes import fake_fetch

    llm.push("writer", post(images=["封面：大字「3套」"])).push("eval", evaluation(8.5))
    d = await write_draft(session, llm, account.id, hint="通勤穿搭", fetch=fake_fetch,
                          image_plan=["封面大字「3套通勤公式」", "三套全身照拼图", "单品清单"])
    w = llm.prompts_of("writer")[0]
    assert "用户对配图的要求（必须照做）" in w and "第 2 张：三套全身照拼图" in w
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    assert [i.prompt for i in imgs] == ["封面：大字「3套」", "三套全身照拼图", "单品清单"]
