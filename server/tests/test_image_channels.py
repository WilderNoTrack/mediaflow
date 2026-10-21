"""生图两条通道：openai-next 优先，额度用完 / 出不了自动换 grsai。"""

import base64

import httpx
import pytest

from mediaflow import credentials
from mediaflow.services import images as images_mod


@pytest.fixture(autouse=True)
def clean_keys():
    keys = {"image_next_api_key": "", "image_api_key": "", "image_next_exhausted": ""}
    credentials.update(keys)
    yield
    credentials.update(keys)


class Resp:
    def __init__(self, status: int, data: dict | None = None, content: bytes = b"") -> None:
        self.status_code, self._data, self.content = status, data, content
        self.text = str(data)

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]


async def test_next_provider_request_and_parse(monkeypatch):
    sent = []

    async def post(self, url, headers=None, json=None, **kw):
        sent.append((url, headers, json))
        if json["model"] == "gpt-image-2.5":
            return Resp(200, {"data": [{"url": "https://cdn/x.png"}]})
        return Resp(200, {"data": [{"b64_json": base64.b64encode(b"gem").decode()}]})

    async def get(self, url, **kw):
        return Resp(200, content=b"gpt")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    p = images_mod.OpenAINextProvider(key="nk", model="gpt-image-2.5")
    assert await p.generate("封面", ["data:image/jpeg;base64,AA"]) == b"gpt"
    url, headers, body = sent[0]
    assert url.endswith("/v1/images/generations") and headers["User-Agent"] == "curl/8.5.0"
    assert body["size"] == "1152x1536" and body["image"] == ["data:image/jpeg;base64,AA"]
    # 界面里的 Nano Banana 在 openai-next 上对应 Gemini 3.1 Flash Image，用 aspect_ratio 出 3:4
    assert await images_mod.OpenAINextProvider(key="nk", model="nano-banana-2.1").generate("x") == b"gem"
    assert sent[-1][2]["model"] == "gemini-3.1-flash-image" and sent[-1][2]["aspect_ratio"] == "3:4"


async def test_next_errors(monkeypatch):
    replies = {}

    async def post(self, url, headers=None, json=None, **kw):
        return replies[json["model"]]

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    replies["gpt-image-2.5"] = Resp(403, {"error": {"message": "用户额度不足, 剩余额度: ¥0.01", "type": "shell_api_error"}})
    replies["gemini-3.1-flash-image"] = Resp(200, {"data": [{"b64_json": base64.b64encode(b"g").decode()}]})
    with pytest.raises(images_mod.ImageError) as e:  # 额度用完不换模型，直接让外面换通道
        await images_mod.OpenAINextProvider(key="nk").generate("x")
    assert e.value.exhausted
    replies["gpt-image-2.5"] = Resp(401, {"error": {"message": "Invalid token. (request id: x)"}})
    with pytest.raises(images_mod.ImageError) as e:
        await images_mod.OpenAINextProvider(key="nk").generate("x")
    assert not e.value.retryable and not e.value.exhausted and "Key" in str(e.value)
    replies["gpt-image-2.5"] = Resp(500, {"error": {"message": "upstream busy"}})  # 普通失败换另一个模型
    assert await images_mod.OpenAINextProvider(key="nk").generate("x") == b"g"


async def test_chain_falls_back_to_grsai_and_remembers(monkeypatch):
    credentials.update({"image_next_api_key": "nk", "image_api_key": "gk"})
    calls = []
    state = {"next": "quota"}

    async def next_gen(self, prompt, refs=None):
        calls.append("next")
        if state["next"] == "quota":
            raise images_mod.ImageError("openai-next 额度用完了", retryable=False, exhausted=True)
        if state["next"] == "busy":
            raise images_mod.ImageError("openai-next 生图失败：busy")
        return b"N"

    async def grsai_gen(self, prompt, refs=None):
        calls.append("grsai")
        return b"G"

    monkeypatch.setattr(images_mod.OpenAINextProvider, "generate", next_gen)
    monkeypatch.setattr(images_mod.GrsaiProvider, "generate", grsai_gen)
    assert images_mod.channels() == ["next", "grsai"] and images_mod.active_channel() == "next"
    p = images_mod.get_provider()
    assert await p.generate("x") == b"G" and calls == ["next", "grsai"]
    assert images_mod.next_exhausted_at() and images_mod.active_channel() == "grsai"
    calls.clear()
    assert await p.generate("y") == b"G" and calls == ["grsai"]  # 暂停期内直接走 grsai
    # 过了暂停期再试 openai-next（可能充值了）；这次能出就用它
    credentials.update({"image_next_exhausted": "2000-01-01T00:00:00+00:00"})
    state["next"] = "ok"
    calls.clear()
    assert await images_mod.get_provider().generate("z") == b"N" and calls == ["next"]
    # 普通失败（不是额度）这张换 grsai，但不记成用完
    state["next"] = "busy"
    calls.clear()
    assert await images_mod.get_provider().generate("w") == b"G" and calls == ["next", "grsai"]
    assert not images_mod.next_exhausted_at()


async def test_only_next_configured(monkeypatch):
    credentials.update({"image_next_api_key": "nk", "image_api_key": ""})
    assert images_mod.image_configured() and images_mod.channels() == ["next"]

    async def next_gen(self, prompt, refs=None):
        raise images_mod.ImageError("openai-next 额度用完了", retryable=False, exhausted=True)

    monkeypatch.setattr(images_mod.OpenAINextProvider, "generate", next_gen)
    with pytest.raises(images_mod.ImageError):
        await images_mod.get_provider().generate("x")
    # 只有这一条时，用完了也还是它（界面会提示去充值或填 grsai 的 Key）
    assert images_mod.active_channel() == "next" and images_mod.next_exhausted_at()


def test_image_settings_next_key(client):
    r = client.get("/api/settings/image").json()
    assert r["next_configured"] is False and r["channel"] == ""
    r = client.put("/api/settings/image", json={"next_api_key": "sk-next", "api_key": "sk-g"}).json()
    assert r["next_configured"] and r["configured"] and r["channel"] == "next" and r["next_exhausted_at"] == ""
    images_mod.mark_next_exhausted()
    r = client.get("/api/settings/image").json()
    assert r["next_exhausted_at"] and r["channel"] == "grsai"
    r = client.put("/api/settings/image", json={"next_api_key": "sk-next2"}).json()  # 换了 Key 重新试
    assert r["next_exhausted_at"] == "" and r["channel"] == "next"
    assert client.get("/api/system").json()["image_configured"]
