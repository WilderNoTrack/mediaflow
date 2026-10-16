"""调研能力测试：mock 各平台接口，验证解析、短句柄、限速缓存与不支持时的报错。"""

import httpx
import pytest

from mediaflow.research import service
from mediaflow.research.types import Unsupported, count_num, fmt_count
from mediaflow.sources import platforms

E = "https://edith.xiaohongshu.com"


@pytest.fixture
def mock_http(monkeypatch):
    routes: dict[str, object] = {}
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        for prefix in sorted(routes, key=len, reverse=True):
            if str(req.url).startswith(prefix):
                body = routes[prefix]
                body = body(req) if callable(body) else body
                return httpx.Response(200, text=body) if isinstance(body, str) else httpx.Response(200, json=body)
        return httpx.Response(404)

    real = httpx.AsyncClient

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    monkeypatch.setattr(service, "_MIN_GAP", 0)
    monkeypatch.setattr("asyncio.sleep", _nosleep)
    service._cache.clear()
    return routes, seen


async def _nosleep(*_a, **_k):
    return None


@pytest.fixture
def creds(monkeypatch):
    values = {"xhs_cookie": "a1=aaa; web_session=s", "douyin_cookie": "sessionid=x; UIFID=u; s_v_web_id=v"}
    monkeypatch.setattr(platforms.credentials, "get", lambda k: values.get(k, ""))
    return values


def test_counts():
    assert count_num("1.3万") == 13000 and count_num("10万+") == 100000 and count_num("") == 0
    assert fmt_count(7769131) == "776.9万" and fmt_count(20000) == "2万" and fmt_count(999) == "999"


async def test_xhs_creator_flow(mock_http, creds):
    routes, seen = mock_http
    routes[f"{E}/api/sns/web/v1/search/usersearch"] = {"success": True, "data": {"users": [
        {"id": "u1", "xsec_token": "tk", "name": "程十安an", "fans": "776.9万", "note_count": 389, "sub_title": "小红书号：1"}]}}
    routes[f"{E}/api/sns/web/v1/user/otherinfo"] = {"success": True, "data": {
        "basic_info": {"nickname": "程十安an", "desc": "美妆\n护肤"}, "interactions": [{"type": "fans", "count": "7769131"}],
        "liked": 100, "collected": 20, "tags": [{"name": "美妆博主"}]}}
    routes[f"{E}/api/sns/web/v1/user_posted"] = {"success": True, "data": {"notes": [
        {"note_id": "n1", "xsec_token": "t1", "display_title": "裸感底妆", "time": 1683973847000, "type": "normal",
         "interact_info": {"liked_count": "1.1万"}},
        {"note_id": "n2", "xsec_token": "t2", "display_title": "春天", "time": 1683699678000, "type": "video",
         "interact_info": {"liked_count": "1.3万"}}]}}
    routes[f"{E}/api/sns/web/v1/feed"] = {"success": True, "data": {"items": [{"note_card": {
        "title": "春天", "desc": "正文内容", "type": "video", "time": 1683699678000, "user": {"nickname": "程十安an"},
        "interact_info": {"liked_count": "1.3万", "collected_count": "1067", "comment_count": "2387", "share_count": "380"},
        "tag_list": [{"name": "护肤"}]}}]}}
    routes[f"{E}/api/sns/web/v2/comment/page"] = {"success": True, "data": {"comments": [
        {"content": "还好吗", "like_count": "321"}, {"content": "等你", "like_count": "1131"}]}}

    found = await service.search_creators("xiaohongshu", "程十安")
    c = found["creators"][0]
    assert c["name"] == "程十安an" and c["fans"] == "776.9万" and c["ref"].startswith("xhs:c")

    got = await service.creator_posts(c["ref"], limit=1, sort="top")
    assert got["creator"]["fans"] == "776.9万" and got["creator"]["标签"] == ["美妆博主"]
    assert [p["title"] for p in got["posts"]] == ["春天"] and "hint" in got
    assert got["posts"][0]["type"] == "视频" and got["posts"][0]["date"] == "2023-05-10"
    get_req = [r for r in seen if "user_posted" in str(r.url)][0]
    assert "x-s" in get_req.headers and "image_scenes=FD_WM_WEBP" in str(get_req.url)

    d = await service.post_detail(got["posts"][0]["ref"])
    assert d["content"] == "正文内容" and d["collects"] == "1067" and d["tags"] == ["护肤"]
    assert d["top_comments"][0] == "1131赞｜等你"

    n = len(seen)
    await service.search_creators("xiaohongshu", "程十安")
    assert len(seen) == n  # 10 分钟内命中缓存


async def test_douyin_creator_flow(mock_http, creds):
    routes, seen = mock_http
    D = "https://www.douyin.com"
    routes[f"{D}/aweme/v1/web/discover/search/"] = {"status_code": 0, "user_list": [{"user_info": {
        "nickname": "papi酱", "sec_uid": "SEC1", "follower_count": 28412223, "signature": "美貌\n才华", "unique_id": "1937"}}]}
    routes[f"{D}/aweme/v1/web/user/profile/other/"] = {"status_code": 0, "user": {
        "nickname": "papi酱", "follower_count": 28412223, "aweme_count": 538, "total_favorited": 343208348}}
    routes[f"{D}/aweme/v1/web/aweme/post/"] = {"status_code": 0, "aweme_list": [
        {"aweme_id": "77", "desc": "热烈欢迎\n袁咏仪", "create_time": 1792036876,
         "statistics": {"digg_count": 169134, "comment_count": 5323, "collect_count": 19703, "share_count": 24264}}]}
    routes[f"{D}/aweme/v1/web/aweme/detail/"] = {"status_code": 0, "aweme_detail": {
        "aweme_id": "77", "desc": "热烈欢迎袁咏仪 #娇兰", "statistics": {"digg_count": 1},
        "text_extra": [{"hashtag_name": "娇兰"}, {"hashtag_name": None}]}}
    routes[f"{D}/aweme/v1/web/comment/list/"] = {"status_code": 0, "comments": [{"text": "快找蔡少芬", "digg_count": 811}]}

    c = (await service.search_creators("douyin", "papi酱"))["creators"][0]
    assert c["fans"] == "2841.2万" and c["抖音号"] == "1937" and c["ref"].startswith("dy:c")
    got = await service.creator_posts(c["ref"])
    p = got["posts"][0]
    assert got["creator"]["posts"] == "538" and p["title"] == "热烈欢迎 袁咏仪" and p["likes"] == "16.9万"
    d = await service.post_detail(p["ref"])
    assert d["tags"] == ["娇兰"] and d["top_comments"] == ["811赞｜快找蔡少芬"]
    assert all("a_bogus=" in str(r.url) for r in seen)


async def test_unsupported_and_bad_refs(creds):
    with pytest.raises(Unsupported, match="百度暂不支持搜博主"):
        await service.search_creators("baidu", "x")
    with pytest.raises(Unsupported, match="不认识的平台"):
        await service.search_creators("kuaishou", "x")
    with pytest.raises(LookupError, match="重新搜索"):
        await service.creator_posts("xhs:c99999")


async def test_needs_login(monkeypatch):
    monkeypatch.setattr(platforms.credentials, "get", lambda k: "")
    with pytest.raises(Unsupported, match="小红书没登录"):
        await service.search_creators("xiaohongshu", "x")


async def test_bilibili_creator_flow(mock_http, monkeypatch):
    monkeypatch.setattr(platforms.credentials, "get", lambda k: "")
    monkeypatch.setattr(platforms.BilibiliSource, "_key", ("", 0.0))
    monkeypatch.setattr(platforms.BilibiliSource, "_buvid", ({}, 0.0))
    routes, seen = mock_http
    A = "https://api.bilibili.com"
    routes[f"{A}/x/web-interface/nav"] = {"data": {"wbi_img": {
        "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
        "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png"}}}
    routes[f"{A}/x/frontend/finger/spi"] = {"code": 0, "data": {"b_3": "B3", "b_4": "B4"}}
    routes[f"{A}/x/web-interface/wbi/search/type"] = {"code": 0, "data": {"result": [
        {"mid": 946974, "uname": "<em class=\"keyword\">影视飓风</em>", "fans": 13900000, "videos": 900, "usign": "简介"}]}}
    routes[f"{A}/x/web-interface/card"] = {"code": 0, "data": {
        "card": {"name": "影视飓风", "sign": "简介"}, "follower": 13900000, "archive_count": 900, "like_num": 500000000}}
    routes[f"{A}/x/space/wbi/arc/search"] = {"code": 0, "data": {"list": {"vlist": [
        {"bvid": "BV1", "title": "相机评测", "play": 3000000, "comment": 5000, "created": 1700000000},
        {"bvid": "BV2", "title": "航拍", "play": 9000000, "comment": 9000, "created": 1700100000}]}}}
    routes[f"{A}/x/web-interface/view"] = {"code": 0, "data": {
        "aid": 11, "title": "航拍", "desc": "简介正文", "owner": {"name": "影视飓风"}, "pubdate": 1700100000,
        "stat": {"view": 9000000, "like": 600000, "reply": 9000, "favorite": 100000, "share": 2000}}}
    routes[f"{A}/x/tag/archive/tags"] = {"code": 0, "data": [{"tag_name": "无人机"}]}
    routes[f"{A}/x/v2/reply"] = {"code": 0, "data": {"replies": [
        {"like": 5, "content": {"message": "一般"}}, {"like": 900, "content": {"message": "太强了"}}]}}

    c = (await service.search_creators("bilibili", "影视飓风"))["creators"][0]
    assert c["name"] == "影视飓风" and c["fans"] == "1390万" and c["ref"].startswith("bili:c")
    got = await service.creator_posts(c["ref"], limit=1, sort="top")
    assert got["creator"]["获赞"] == "5亿" and got["posts"][0]["title"] == "航拍" and got["posts"][0]["views"] == "900万"
    d = await service.post_detail(got["posts"][0]["ref"])
    assert d["tags"] == ["无人机"] and d["top_comments"][0] == "900赞｜太强了" and d["collects"] == "10万"
    arc = [r for r in seen if "arc/search" in str(r.url)][0]
    assert "w_rid=" in str(arc.url) and "dm_img_str=" in str(arc.url) and "buvid3=B3" in arc.headers.get("cookie", "")


def test_capabilities_listed():
    caps = service.capabilities()
    assert caps["xiaohongshu"] == ["搜内容", "搜博主", "看博主作品", "看作品详情"]
    assert caps["baidu"] == ["搜内容"]
