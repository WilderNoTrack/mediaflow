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
