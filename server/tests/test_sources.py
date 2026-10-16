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


@pytest.fixture
def creds(monkeypatch):
    values: dict[str, str] = {}
    monkeypatch.setattr(platforms.credentials, "get", lambda k: values.get(k, ""))
    return values


async def test_zhihu_not_configured_is_off_not_failed(creds):
    from mediaflow.sources.registry import fetch_all
    report = await fetch_all("穿搭", sources=[platforms.ZhihuSource()])
    st = report.statuses[0]
    assert st.mode == "off" and not st.ok and report.failed_labels == []


async def test_zhihu_open_platform_search(mock_http, creds):
    routes, seen = mock_http
    creds["zhihu_access_secret"] = "sec"
    routes["https://developer.zhihu.com/api/v1/content/zhihu_search"] = {"Code": 0, "Message": "", "Data": {
        "HasMore": False, "Items": [{"Title": "秋季穿搭有哪些技巧？", "Url": "https://zhihu.com/q/1",
                                     "VoteUpCount": 520, "ContentText": "<p>先说结论</p>"}]}}
    items = await platforms.ZhihuSource().fetch("秋季穿搭", 5)
    assert items[0].title == "秋季穿搭有哪些技巧？" and items[0].snippet == "先说结论" and items[0].kind == "search"
    req = seen[-1]
    assert req.headers["authorization"] == "Bearer sec" and "x-request-timestamp" in req.headers
    assert "Query=" in str(req.url)


async def test_zhihu_auth_error_is_explained(mock_http, creds):
    routes, _ = mock_http
    creds["zhihu_access_secret"] = "bad"
    routes["https://developer.zhihu.com/"] = {"Code": 20001, "Message": "Authorization failed", "Data": None}
    with pytest.raises(RuntimeError, match="Access Secret"):
        await platforms.ZhihuSource().fetch("穿搭", 5)


async def test_baidu_uses_qianfan_search_when_key_set(mock_http, creds):
    routes, seen = mock_http
    creds["qianfan_api_key"] = "bce-v3/xx"
    routes["https://qianfan.baidubce.com/v2/ai_search/web_search"] = {"references": [
        {"title": "2026秋季穿搭指南", "url": "https://a.com", "snippet": "叠穿", "date": "2026-10-01"}]}
    items = await BaiduSource().fetch("秋季穿搭", 5)
    assert items[0].title == "2026秋季穿搭指南" and items[0].kind == "search"
    body = json.loads(seen[-1].content)
    assert body["messages"][0]["content"] == "秋季穿搭" and seen[-1].headers["authorization"] == "Bearer bce-v3/xx"


async def test_baidu_without_key_marks_hot(mock_http, creds):
    routes, _ = mock_http
    data = {"data": {"cards": [{"content": [{"word": "热点A", "query": "热点A"}]}]}}
    routes["https://top.baidu.com/board"] = f"<!--s-data:{json.dumps(data)}-->"
    from mediaflow.sources.registry import fetch_all
    report = await fetch_all("穿搭", sources=[BaiduSource()])
    assert report.items[0].kind == "hot" and report.statuses[0].mode == "hot" and "热榜" in report.statuses[0].note


async def test_douyin_search_with_cookie(mock_http, creds):
    routes, seen = mock_http
    creds["douyin_cookie"] = "sessionid=abc; msToken=tok; UIFID=u1; s_v_web_id=verify_x"
    routes["https://www.douyin.com/aweme/v1/web/general/search/single/"] = {"status_code": 0, "data": [
        {"type": 1, "aweme_info": {"aweme_id": "73", "desc": "秋季穿搭一衣多穿", "statistics": {"digg_count": 9}}},
        {"type": 999, "user_list": []}]}
    items = await platforms.DouyinSource().fetch("秋季穿搭", 5)
    assert [i.title for i in items] == ["秋季穿搭一衣多穿"] and items[0].url.endswith("/video/73")
    url = str(seen[-1].url)
    assert "a_bogus=" in url and "msToken=tok" in url and "verifyFp=verify_x" in url
    assert seen[-1].headers["cookie"].startswith("sessionid=abc") and seen[-1].headers["uifid"] == "u1"
    from urllib.parse import parse_qs, urlsplit

    from mediaflow.sources.douyin_abogus.abogus import structure_error
    assert structure_error(parse_qs(urlsplit(url).query)["a_bogus"][0]) is None


async def test_douyin_antispam_is_reported(mock_http, creds):
    routes, _ = mock_http
    creds["douyin_cookie"] = "sessionid=abc"
    routes["https://www.douyin.com/aweme/"] = {"status_code": 0, "data": [],
                                               "search_nil_info": {"search_nil_type": "antispam_check"}}
    with pytest.raises(RuntimeError, match="风控"):
        await platforms.DouyinSource().fetch("穿搭", 5)


async def test_douyin_expired_cookie_reports_login(mock_http, creds):
    routes, _ = mock_http
    creds["douyin_cookie"] = "x=1"
    routes["https://www.douyin.com/aweme/"] = {"status_code": 2483, "status_msg": "请先登录，再继续搜索吧"}
    with pytest.raises(RuntimeError, match="请先登录"):
        await platforms.DouyinSource().fetch("穿搭", 5)


def test_credentials_store_overrides_env(tmp_path, monkeypatch):
    from mediaflow import credentials
    monkeypatch.setattr(credentials, "_path", lambda: tmp_path / "c.json")
    assert credentials.get("douyin_cookie") == ""
    credentials.update({"douyin_cookie": " a=1 ", "nope": "x", "zhihu_access_secret": None})
    assert credentials.get("douyin_cookie") == "a=1"
    credentials.update({"douyin_cookie": ""})
    assert credentials.get("douyin_cookie") == ""
