"""热点来源解析测试：用 httpx.MockTransport 模拟各平台返回，不访问外网。"""

import json

import httpx
import pytest

from mediaflow.sources import platforms
from mediaflow.sources.base import TrendItem
from mediaflow.sources.platforms import BaiduSource, BilibiliSource, ToutiaoSource, _prefer_keyword


@pytest.fixture
def mock_http(monkeypatch):
    routes: dict[str, object] = {}
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        for prefix, body in routes.items():
            if str(req.url).startswith(prefix):
                body = body(req) if callable(body) else body
                if isinstance(body, str):
                    return httpx.Response(200, text=body)
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(platforms.httpx, "AsyncClient", factory)
    return routes, seen


def test_prefer_keyword_puts_hits_first():
    items = [TrendItem(title=t, source="x") for t in ["油价上涨", "秋季穿搭指南", "球赛", "通勤穿搭"]]
    out = _prefer_keyword(items, "穿搭", 3)
    assert [i.title for i in out] == ["秋季穿搭指南", "通勤穿搭", "油价上涨"]
    assert len(_prefer_keyword(items, "", 2)) == 2


async def test_baidu_parses_board_sdata(mock_http):
    routes, _ = mock_http
    data = {"data": {"cards": [{"content": [
        {"word": "秋天第一杯奶茶", "query": "秋天第一杯奶茶", "hotScore": 4900000, "desc": "又到季节"},
        {"word": "", "query": ""},
    ]}]}}
    routes["https://top.baidu.com/board"] = f"<html><!--s-data:{json.dumps(data, ensure_ascii=False)}--></html>"
    items = await BaiduSource().fetch("", 10)
    assert len(items) == 1 and items[0].title == "秋天第一杯奶茶" and items[0].heat == "4900000"
    assert "wd=" in items[0].url


async def test_baidu_layout_change_raises(mock_http):
    routes, _ = mock_http
    routes["https://top.baidu.com/board"] = "<html>请输入验证码</html>"
    with pytest.raises(RuntimeError, match="结构变了"):
        await BaiduSource().fetch("", 10)


async def test_toutiao_parses_hot_board(mock_http):
    routes, _ = mock_http
    routes["https://www.toutiao.com/hot-event/hot-board/"] = {"data": [
        {"Title": "国庆出行高峰", "HotValue": "123", "Url": "https://t/1"}, {"Title": ""}]}
    items = await ToutiaoSource().fetch("", 10)
    assert [i.title for i in items] == ["国庆出行高峰"] and items[0].source == "toutiao"


async def test_bilibili_falls_back_to_ranking_when_search_empty(mock_http, monkeypatch):
    routes, seen = mock_http
    monkeypatch.setattr(BilibiliSource, "_key", ("", 0.0))
    monkeypatch.setattr(BilibiliSource, "_buvid", ({}, 0.0))
    routes["https://api.bilibili.com/x/frontend/finger/spi"] = {"data": {"b_3": "B3", "b_4": "B4"}}
    routes["https://api.bilibili.com/x/web-interface/nav"] = {"data": {"wbi_img": {
        "img_url": "https://i0/" + "a" * 32 + ".png", "sub_url": "https://i0/" + "b" * 32 + ".png"}}}
    routes["https://api.bilibili.com/x/web-interface/wbi/search/type"] = {"code": 0, "data": {"result": []}}
    routes["https://api.bilibili.com/x/web-interface/ranking/v2"] = {"data": {"list": [
        {"title": "排行榜视频", "bvid": "BV1", "stat": {"view": 99}}]}}
    items = await BilibiliSource().fetch("穿搭", 5)
    assert [i.title for i in items] == ["排行榜视频"]
    search = next(r for r in seen if "search/type" in str(r.url))
    assert "buvid3=B3" in search.headers.get("cookie", "") and "w_rid=" in str(search.url)


async def test_bilibili_search_results_are_cleaned(mock_http, monkeypatch):
    routes, _ = mock_http
    monkeypatch.setattr(BilibiliSource, "_key", ("k" * 32, 9e12))
    monkeypatch.setattr(BilibiliSource, "_buvid", ({"buvid3": "x"}, 9e12))
    routes["https://api.bilibili.com/x/web-interface/wbi/search/type"] = {"data": {"result": [
        {"title": '<em class="keyword">穿搭</em>&amp;通勤', "bvid": "BV2", "play": 10}]}}
    items = await BilibiliSource().fetch("穿搭", 5)
    assert items[0].title == "穿搭&通勤" and items[0].url.endswith("BV2")
