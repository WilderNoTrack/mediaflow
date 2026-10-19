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
    llm.push("writer", post(title="这" * 25), post()).push("eval", evaluation(9), evaluation(8))
    d, _ = await run(session, llm, account)
    assert d.attempts == 2 and d.title == "通勤穿搭3个小心机" and d.check_issues == []
    assert "超过小红书上限" in llm.prompts_of("reviser")[0]
    assert "这" * 25 in llm.prompts_of("reviser")[0]  # 是在上一版上改，不是重写


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
