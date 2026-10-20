"""文字模型通道：openai-next 优先调 DeepSeek，出错自动换官方；设置接口能填 Key、模型名、选通道。"""
import pytest

from mediaflow import credentials
from mediaflow.llm import client as c
from mediaflow.llm.client import ChainLLM, LLMError, LLMResponse


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from mediaflow.config import get_settings

    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("IMAGE_NEXT_API_KEY", "")
    get_settings.cache_clear()
    credentials.update({k: "" for k in ("deepseek_api_key", "image_next_api_key", "llm_next_model", "llm_channel")})
    c.reset_next_pause()
    yield
    credentials.update({k: "" for k in ("deepseek_api_key", "image_next_api_key", "llm_next_model", "llm_channel")})
    c.reset_next_pause()


def _fake(monkeypatch, bad_labels=(), stream_fail_after=None):
    seen = []

    async def complete(self, messages, **kw):
        seen.append((self.label, self.model, self.client.base_url.host, self.client.default_headers.get("User-Agent")))
        if self.label in bad_labels:
            raise LLMError(f"{self.label} 调用失败：Error code: 402 - insufficient quota")
        return LLMResponse(content=f"来自 {self.label}")

    async def stream(self, messages, **kw):
        seen.append((self.label, self.model, "", ""))
        if self.label in bad_labels and stream_fail_after is None:
            raise LLMError(f"{self.label} 调用失败：Error code: 503")
        yield ("delta", f"来自 {self.label}")
        if self.label in bad_labels:
            raise LLMError(f"{self.label} 调用失败：断了")
        yield ("done", LLMResponse(content=f"来自 {self.label}"))

    monkeypatch.setattr(c.DeepSeekLLM, "complete", complete)
    monkeypatch.setattr(c.DeepSeekLLM, "stream", stream)
    return seen


def _llm():
    c.set_llm(None)
    return c.get_llm()


async def test_next_first_then_falls_back_to_deepseek(monkeypatch):
    seen = _fake(monkeypatch, bad_labels=("openai-next",))
    credentials.update({"deepseek_api_key": "sk-ds", "image_next_api_key": "sk-next"})
    assert c.llm_channels() == ["next", "deepseek"] and c.llm_configured()
    llm = _llm()
    assert isinstance(llm, ChainLLM)
    r = await llm.complete([{"role": "user", "content": "hi"}])
    assert r.content == "来自 DeepSeek"
    assert seen[0] == ("openai-next", "deepseek-v4-1-flash-261017", "api.openai-next.com", "curl/8.5.0")
    assert c.next_paused()  # 额度用完：之后一阵子先走官方，不再每次先撞一下
    seen.clear()
    await _llm().complete([{"role": "user", "content": "hi"}])
    assert [s[0] for s in seen] == ["DeepSeek"]


async def test_stream_falls_back_only_before_output(monkeypatch):
    seen = _fake(monkeypatch, bad_labels=("openai-next",))
    credentials.update({"deepseek_api_key": "sk-ds", "image_next_api_key": "sk-next"})
    evs = [e async for e in _llm().stream([{"role": "user", "content": "hi"}])]
    assert evs[-1][1].content == "来自 DeepSeek" and [s[0] for s in seen] == ["openai-next", "DeepSeek"]

    c.reset_next_pause()
    _fake(monkeypatch, bad_labels=("openai-next",), stream_fail_after=1)
    with pytest.raises(LLMError):  # 已经吐出字了就不换，免得用户看到重复的话
        [e async for e in _llm().stream([{"role": "user", "content": "hi"}])]


async def test_only_next_key_is_enough_and_can_see_images(monkeypatch):
    _fake(monkeypatch)
    credentials.update({"image_next_api_key": "sk-next"})
    assert c.llm_configured() and c.llm_channels() == ["next"]
    assert (await _llm().complete([{"role": "user", "content": "hi"}])).content == "来自 openai-next"
    assert c.vision_available()
    v = c.get_vision_llm("low")
    assert v.label == "openai-next" and v.extra == {"reasoning_effort": "low"}


async def test_channel_preference(monkeypatch):
    _fake(monkeypatch)
    credentials.update({"deepseek_api_key": "sk-ds", "image_next_api_key": "sk-next", "llm_channel": "deepseek"})
    assert c.llm_channels() == ["deepseek"]
    credentials.update({"llm_channel": "next"})
    assert c.llm_channels() == ["next"]
    credentials.update({"llm_channel": ""})
    assert c.llm_channels() == ["next", "deepseek"]


def test_settings_api_next_key_model_and_channel(client, monkeypatch):
    seen = []

    async def complete(self, messages, **kw):
        seen.append((self.label, self.model))
        if self.model == "no-such-model":
            raise LLMError("openai-next 调用失败：Error code: 404 - model not found")
        return LLMResponse(content="好")

    monkeypatch.setattr(c.DeepSeekLLM, "complete", complete)
    st = client.get("/api/settings/llm").json()
    assert st["configured"] is False and st["next_model"] == "deepseek-v4-1-flash-261017" and st["channel"] == "auto"
    r = client.put("/api/settings/llm", json={"next_api_key": "sk-next", "next_model": "no-such-model"})
    assert r.status_code == 400 and "没有这个模型" in r.json()["detail"]
    st = client.put("/api/settings/llm", json={"next_api_key": "sk-next"}).json()
    assert st["configured"] and st["next_configured"] and st["order"] == ["next"]
    assert credentials.get("image_next_api_key") == "sk-next"  # 和配图共用一个 Key
    assert client.get("/api/system").json()["llm_configured"] is True
    st = client.put("/api/settings/llm", json={"channel": "deepseek"}).json()
    assert st["channel"] == "deepseek" and st["order"] == ["next"]  # 官方没配就还用 openai-next
    assert client.put("/api/settings/llm", json={"channel": "bad"}).status_code == 400
    assert client.post("/api/settings/llm/test", json={"channel": "next"}).json()["ok"] is True
    assert ("openai-next", "deepseek-v4-1-flash-261017") in seen
