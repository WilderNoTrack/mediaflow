import pytest
from sqlmodel import select

from mediaflow.agents.pipeline import write_draft
from mediaflow.domain.models import (
    Account, DraftImage, ImageStatus, Rule, RuleSource, Topic, TopicStatus, Trigger,
)
from tests.fakes import evaluation, fail, fake_fetch, post


async def run(session, llm, account, **kw):
    events = []
    d = await write_draft(session, llm, account.id, emit=lambda st, m, data=None: events.append((st, m)),
                          fetch=fake_fetch, **kw)
    return d, events


async def test_happy_path_injects_account_and_rules(session, llm, account):
    session.add(Rule(user_id=account.user_id, account_id=account.id, text="结尾要引导收藏", source=RuleSource.chat))
    session.commit()
    llm.push("writer", post()).push("eval", evaluation(8))

    d, events = await run(session, llm, account)

    assert d.account_id == account.id and d.score == 8 and d.attempts == 1
    assert not d.needs_attention and d.original_title == d.title
    writer_prompt = llm.prompts_of("writer")[0]
    assert "结尾要引导收藏" in writer_prompt and "学生党平价穿搭" in writer_prompt
    assert "结尾要引导收藏" in llm.prompts_of("eval")[0]  # 质检也看得到规则
    topic = session.get(Topic, d.topic_id)
    assert topic.status == TopicStatus.used
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id)).all()
    assert [i.status for i in imgs] == [ImageStatus.skipped] * 2  # 没配生图服务
    assert events[-1][0] == "done"
    # 有一个来源失败，要如实告诉用户
    assert any(st == "warning" and "B站" in m for st, m in events)


async def test_external_data_is_fenced(session, llm, account):
    llm.push("writer", post()).push("eval", evaluation(8))
    await run(session, llm, account)
    p = llm.prompts_of("topic")[0]
    start, end = p.index("<external_data>"), p.index("</external_data>")
    assert start < p.index("忽略之前的指示") < end


async def test_hard_issue_triggers_rewrite_with_feedback(session, llm, account):
    llm.push("writer", post(title="全网第一的通勤穿搭"), post()).push("eval", evaluation(9), evaluation(8))
    d, _ = await run(session, llm, account)
    assert d.attempts == 2 and d.title == "通勤穿搭3个小心机" and d.check_issues == []
    assert "违规风险词" in llm.prompts_of("reviser")[0]
    assert "全网第一的通勤穿搭" in llm.prompts_of("reviser")[0]  # 是在上一版上改，不是重写


async def test_long_title_is_fixed_by_code_not_left_to_model(session, llm, account):
    """标题超 20 字不靠模型自觉：要 5 个候选，代码数字数挑第一个合格的；不合格的不收。"""
    long = "刚工作别急着存钱！先花3个月把账记明白，我多存了5000块"
    llm.push("writer", post(title=long, images=[f"封面：女生拿着账本，大字「{long}」", "内页：记账APP截图"])).push("eval", evaluation(9))
    llm.push("title_fit", {"titles": ["刚工作别急着存钱！先花3个月记账多存5000块", "全网第一记账法", "记账3个月，我多存了5000块"]})
    d, events = await run(session, llm, account)
    assert d.title == "记账3个月，我多存了5000块" and d.check_issues == [] and d.attempts == 1
    assert "29 字" in llm.prompts_of("title_fit")[0]
    ch = [c for c in d.evaluation["changes"] if c["where"] == "标题"]
    assert ch and ch[-1]["before"] == long and "超过小红书上限" in ch[-1]["why"]
    assert any("改短" in m for _, m in events)
    imgs = session.exec(select(DraftImage).where(DraftImage.draft_id == d.id).order_by(DraftImage.idx)).all()
    assert imgs[0].prompt == "封面：女生拿着账本，大字「记账3个月，我多存了5000块」"


async def test_long_title_retries_then_cuts_at_punctuation(session, llm, account):
    long = "刚工作别急着存钱！先花3个月把账记明白，我多存了5000块"
    llm.push("writer", post(title=long)).push("eval", evaluation(9))
    llm.push("title_fit", {"titles": [long]}, {"titles": ["刚工作别急着存钱！先花三个月把账记明白多存钱"]})
    d, _ = await run(session, llm, account)
    assert len(llm.prompts_of("title_fit")) == 2 and "上次给的都超了" in llm.prompts_of("title_fit")[1]
    assert d.title == "刚工作别急着存钱！先花3个月把账记明白" and d.check_issues == []


async def test_reviser_making_title_long_again_is_fixed(session, llm, account):
    """改稿时模型又把标题改长了，也一样兜住：留在稿子上的标题一定不超 20 字。"""
    llm.push("writer", post(title="通勤穿搭3个小心机", tags=["穿搭", "学生党"]))
    llm.push("reviser", {"title": "学生党通勤穿搭3个小心机，照着穿气质翻倍不费钱", "edits": []})
    llm.push("eval", evaluation(5), evaluation(9))
    llm.push("title_fit", {"titles": ["通勤穿搭3个小心机，气质翻倍"]})
    d, _ = await run(session, llm, account)
    assert d.title == "通勤穿搭3个小心机，气质翻倍" and len(d.title) <= 20
    assert len(d.tags) >= 3  # 标签少了从账号关键词里补


async def test_low_score_retries_then_keeps_best(session, llm, account):
    llm.push("writer", post(title="版本一"), post(title="版本二"), post(title="版本三"), post(title="版本四"))
    llm.push("eval", evaluation(5), evaluation(6.5), evaluation(6), evaluation(6.2))
    d, events = await run(session, llm, account)
    assert d.attempts == 4 and d.title == "版本二" and d.score == 6.5
    # 每轮都在目前最好的一版上改
    assert "标题：版本二" in llm.prompts_of("reviser")[1] and "标题：版本二" in llm.prompts_of("reviser")[2]
    assert [h["score"] for h in d.evaluation["history"]] == [5, 6.5, 6, 6.2]
    assert d.needs_attention
    assert any("重点检查" in m for _, m in events)


async def test_violated_rule_caps_score(session, llm, account):
    llm.push("writer", post(), post(), post(), post())
    llm.push("eval", *[evaluation(9, violated=["结尾要引导收藏"])] * 4)
    d, _ = await run(session, llm, account)
    assert d.score == 6.0 and d.needs_attention


async def test_evaluator_failure_is_flagged_not_hidden(session, llm, account):
    llm.push("writer", post(), post(), post(), post()).push("eval", fail(), fail(), fail(), fail())
    d, events = await run(session, llm, account)
    assert d.score is None and d.needs_attention
    assert any("质检服务出错" in m for _, m in events)


async def test_uses_given_topic_and_hint(session, llm, account):
    t = Topic(user_id=account.user_id, account_id=account.id, title="宿舍穿搭收纳", angle="小空间")
    session.add(t)
    session.commit()
    llm.push("writer", post()).push("eval", evaluation(8))
    d, _ = await run(session, llm, account, topic_id=t.id, hint="预算 200 以内", trigger=Trigger.chat)
    assert d.topic_id == t.id and d.trigger == Trigger.chat
    assert "预算 200 以内" in llm.prompts_of("writer")[0]
    assert not llm.prompts_of("topic")  # 指定了选题就不再搜


async def test_topic_from_other_account_rejected(session, llm, account):
    other = Account(user_id=account.user_id, name="别的号", theme="美食")
    session.add(other)
    session.commit()
    t = Topic(user_id=account.user_id, account_id=other.id, title="别人的选题")
    session.add(t)
    session.commit()
    with pytest.raises(LookupError):
        await run(session, llm, account, topic_id=t.id)


async def test_requires_theme(session, llm):
    a = Account(user_id="local", name="空号")
    session.add(a)
    session.commit()
    with pytest.raises(ValueError, match="主题"):
        await run(session, llm, a)


async def test_duplicate_topics_are_skipped(session, llm, account):
    session.add(Topic(user_id=account.user_id, account_id=account.id, title="秋季通勤叠穿公式",
                      status=TopicStatus.used))
    session.commit()
    llm.push("topic", {"topics": [
        {"title": "秋季通勤叠穿公式！", "angle": "重复的"},
        {"title": "宿舍衣柜收纳术", "angle": "新的"},
    ]})
    llm.push("writer", post()).push("eval", evaluation(8))
    d, _ = await run(session, llm, account)
    assert session.get(Topic, d.topic_id).title == "宿舍衣柜收纳术"


async def test_hint_becomes_topic_when_nothing_new(session, llm, account):
    llm.push("topic", {"topics": []})
    llm.push("writer", post()).push("eval", evaluation(8))
    d, _ = await run(session, llm, account, hint="早八快速出门妆")
    t = session.get(Topic, d.topic_id)
    assert t.title == "早八快速出门妆" and t.source == "user"


async def test_rule_word_count_checked_by_code(session, llm, account):
    session.add(Rule(user_id=account.user_id, account_id=account.id, text="正文150到250字，靠图承担教程"))
    session.commit()
    llm.push("writer", post(body="字" * 300), post(body="字" * 200)).push("eval", evaluation(8), evaluation(8))
    d, _ = await run(session, llm, account)
    assert d.attempts == 2 and d.check_issues == [] and len(d.body) == 200
    first = llm.prompts_of("reviser")[0]
    assert "正文 300 字，账号规则要求 150–250 字" in first and "系统统计 300 字" in first
    assert "系统统计 300 字" in llm.prompts_of("eval")[0]  # 质检拿到的是代码数的字数


async def test_revise_draft_keeps_better_version(session, llm, account):
    from mediaflow.agents.pipeline import revise_draft

    llm.push("writer", post(title="原稿")).push("eval", evaluation(8))
    d, _ = await run(session, llm, account)
    # 带了要求：先按现在的版本重新质检，再改
    llm.push("eval", evaluation(7.2), evaluation(8.5)).push("reviser", post(title="改好的"))
    d2 = await revise_draft(session, llm, d.id, note="开头更直接")
    assert d2.title == "改好的" and d2.score == 8.5 and not d2.needs_attention
    assert "用户的要求：开头更直接" in llm.prompts_of("reviser")[-1]
    assert [h["score"] for h in d2.evaluation["history"]] == [8, 8.5]

    llm.push("eval", evaluation(8.5), evaluation(5), evaluation(5.5))
    llm.push("reviser", post(title="更差的"), post(title="还是差"))
    d3 = await revise_draft(session, llm, d.id, note="再短一点")
    assert d3.title == "改好的" and d3.score == 8.5  # 没改好就不替换


def test_tag_rule_from_benchmark_does_not_fight_hard_check():
    from mediaflow.agents.checks import hard_check

    body = "正文" * 200
    rules = ["标题和正文都带单一核心话题标签（如#存钱#），不堆砌无关标签"]
    assert not any("标签" in i for i in hard_check("标题", body, ["存钱"], ["封面"], rules))
    assert any("标签" in i for i in hard_check("标题", body, ["存钱"], ["封面"], []))


def test_apply_edits_is_surgical_and_keeps_user_sentences():
    from mediaflow.agents.pipeline import apply_edits, user_sentences

    body = "开头一句话。第二句是用户写的金句！第三句有点水。结尾。"
    locked = user_sentences("开头一句话。第二句原来是这样。第三句有点水。结尾。", body)
    assert locked == ["第二句是用户写的金句！"]
    new, applied, skipped = apply_edits(body, [
        {"find": "第三句有点水。", "replace": "第三句换成具体数字：每月存 800。"},
        {"find": "第二句是用户写的金句", "replace": "被改掉"},   # 碰到用户的句子：跳过
        {"find": "原稿里没有的句子", "replace": "x"},            # 找不到：跳过
    ], locked)
    assert new == "开头一句话。第二句是用户写的金句！第三句换成具体数字：每月存 800。结尾。"
    assert (applied, skipped) == (1, 2)


async def test_review_rounds_are_targeted_and_remember_previous_issues(session, llm, account):
    """主编给出带位置的意见（必须改 + 可以更好）→ 编辑全部落实，只改被点名的句子 → 复核时能看到上一轮提了什么；
    改过的地方都记下来，最后一轮只复核、不再提新意见。"""
    body = "宝子们今天聊通勤穿搭。" + "这一段是很有信息量的内容，讲了具体的搭配方法。" * 8 + "开头这句太平淡了。"
    must = {"hook": 6, "value": 7, "voice": 7, "fit": 7, "rules": 8, "violated_rules": [],
            "items": [{"level": "must", "where": "结尾", "quote": "开头这句太平淡了。", "problem": "结尾没有互动",
                       "fix": "改成提问"},
                      {"level": "nice", "where": "开头", "quote": "宝子们", "problem": "可以更具体", "fix": "点出通勤人群"}]}
    ok = {"hook": 8, "value": 8, "voice": 8, "fit": 8, "rules": 8, "violated_rules": [], "resolved": [1],
          "items": [{"level": "nice", "where": "开头", "quote": "宝子们", "problem": "可以更具体", "fix": "点出通勤人群"}]}
    done = {"hook": 9, "value": 8, "voice": 8, "fit": 8, "rules": 8, "violated_rules": [], "resolved": [1], "items": []}
    llm.push("writer", post(body=body)).push("eval", must, ok, done)
    llm.push("reviser", {"edits": [{"item": 1, "find": "开头这句太平淡了。", "replace": "你们通勤最头疼哪一步？评论区告诉我～"}]},
             {"edits": [{"item": 1, "find": "宝子们", "replace": "通勤族宝子们"}]})
    d, _ = await run(session, llm, account)
    assert d.body.endswith("你们通勤最头疼哪一步？评论区告诉我～") and d.body.startswith("通勤族宝子们")
    assert "这一段是很有信息量的内容" in d.body
    assert d.attempts == 3 and not d.needs_attention and d.evaluation["items"] == []
    rev = llm.prompts_of("reviser")[0]
    assert "结尾「开头这句太平淡了。」：结尾没有互动｜改法：改成提问" in rev and "可以更具体" in rev  # 提了就改
    assert "上一轮你提的问题" in llm.prompts_of("eval")[1] and "结尾没有互动" in llm.prompts_of("eval")[1]
    assert "不要再提新的 nice" in llm.prompts_of("eval")[1]
    changes = d.evaluation["changes"]
    assert [(c["where"], c["why"]) for c in changes] == [("结尾", "结尾没有互动"), ("开头", "可以更具体")]
    assert changes[0]["before"] == "开头这句太平淡了。"


async def test_last_round_only_verifies(session, llm, account):
    """最后一轮复核不再提新意见；还留着的意见标记为「改过」，界面据此说「AI 改不好，要你看」而不是「请你改」。"""
    item = {"level": "must", "where": "第2段", "quote": "这一段", "problem": "缺数据", "fix": "补一个价格"}
    bad = {"hook": 6, "value": 6, "voice": 6, "fit": 6, "rules": 6, "violated_rules": [], "items": [item]}
    llm.push("writer", post()).push("eval", bad, bad, bad, bad)
    llm.push("reviser", post(title="二"), post(title="三"), post(title="四"))
    d, _ = await run(session, llm, account)
    assert d.attempts == 4 and d.evaluation["attempted"] and d.needs_attention
    assert "最后一次复核" in llm.prompts_of("eval")[-1] and "最后一次复核" not in llm.prompts_of("eval")[-2]


async def test_pick_reference_from_benchmark(session, llm, account):
    """没给链接：从对标爆款里让 AI 挑一篇和选题最像的；AI 挑不出来就按点赞最高。"""
    from mediaflow.domain.models import Benchmark, BenchmarkStatus, Topic
    from mediaflow.services import refpost

    session.add(Benchmark(user_id=account.user_id, account_id=account.id, target="x", status=BenchmarkStatus.ready,
                          creator_name="小A", samples=[
                              {"title": "高赞", "likes": "5万", "kind": "图文", "images": ["https://ci/1", "https://ci/2"]},
                              {"title": "通勤公式", "likes": "1万", "kind": "图文", "images": ["https://ci/3", "https://ci/4"]}]))
    t = Topic(user_id="local", account_id=account.id, title="秋季通勤叠穿公式")
    session.add(t)
    session.commit()
    llm.push("ref_pick", {"no": 2, "also": [1, 2, 7], "why": "同样是公式型清单"})
    ref, _ = await refpost.pick(session, llm, account.id, t)
    assert ref["title"] == "通勤公式" and ref["why"] == "同样是公式型清单" and ref["creator"] == "小A"
    assert [x["title"] for x in ref["extra"]] == ["高赞"] and "images" not in ref["extra"][0]  # 文案参考不带图
    assert "高赞" in llm.prompts_of("ref_pick")[0]
    llm.push("ref_pick", {"no": 9})
    ref, _ = await refpost.pick(session, llm, account.id, t)
    assert ref["title"] == "高赞" and [x["title"] for x in ref["extra"]] == ["通勤公式"]

    # 选题自带原爆款：它当主参考帖，对标爆款只挑文案参考
    t2 = Topic(user_id="local", account_id=account.id, title="复刻", reference={"title": "高赞", "likes": "5万"})
    session.add(t2)
    session.commit()
    ref, _ = await refpost.pick(session, llm, account.id, t2)
    assert ref["source"] == "topic" and [x["title"] for x in ref["extra"]] == ["通勤公式"]


async def test_deepseek_stream_accumulates_tool_calls():
    """流式接口里工具调用的名字、参数是一段段来的，要拼完整；思考内容单独吐。"""
    from types import SimpleNamespace as N

    from mediaflow.llm.client import DeepSeekLLM

    def ch(content=None, reasoning=None, tcs=None, usage=None, empty=False):
        d = N(content=content, reasoning_content=reasoning, tool_calls=tcs)
        return N(choices=[] if empty else [N(delta=d)], usage=usage)

    def tc(i, id=None, name=None, args=None):
        return N(index=i, id=id, function=N(name=name, arguments=args))

    chunks = [ch(reasoning="想一想"), ch(content="我去"), ch(content="查查"),
              ch(tcs=[tc(0, "a", "research_search", '{"keyword":')]), ch(tcs=[tc(0, args='"通勤"}')]),
              ch(tcs=[tc(1, "b", "list_drafts", "{}")]), ch(empty=True, usage=N(model_dump=lambda: {"total_tokens": 9}))]

    async def gen():
        for c in chunks:
            yield c

    async def create(**kw):
        assert kw["stream"] is True
        return gen()

    llm = DeepSeekLLM(api_key="k")
    llm.client = N(chat=N(completions=N(create=create)))
    evs = [e async for e in llm.stream([{"role": "user", "content": "x"}], tools=[{}])]
    kinds = [k for k, _ in evs]
    assert kinds == ["reasoning", "delta", "delta", "calling", "calling", "done"]
    r = evs[-1][1]
    assert r.content == "我去查查" and r.usage == {"total_tokens": 9}
    assert [(c.id, c.name, c.arguments) for c in r.tool_calls] == [
        ("a", "research_search", {"keyword": "通勤"}), ("b", "list_drafts", {})]
