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
    assert client.put("/api/settings/llm", json={"api_key": " sk-good "}).json() == {"configured": True, "origin": "ui"}
    assert llm_client.llm_key() == "sk-good" and client.get("/api/system").json()["llm_configured"] is True
    assert client.post("/api/settings/llm/test", json={"api_key": ""}).json()["ok"] is True  # 不传就测已保存的
    assert seen == ["sk-bad", "sk-good", "sk-good"]
    assert client.put("/api/settings/llm", json={"api_key": ""}).json()["configured"] is False
