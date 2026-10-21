from mediaflow.agents.checks import clean_tags, hard_check, is_duplicate, similarity
from tests.fakes import GOOD_BODY


def test_good_post_has_no_issues():
    assert hard_check("通勤穿搭3个小心机", GOOD_BODY, ["a", "b", "c"], ["封面"]) == []


def test_platform_limits():
    issues = hard_check("这" * 21, "短", ["a"], [])
    assert any("标题 21 字" in i for i in issues)
    assert any("太单薄" in i for i in issues)
    assert any("标签 1 个" in i for i in issues)
    assert any("配图 0 张" in i for i in issues)
    assert any("超过小红书上限 1000" in i for i in hard_check("t", "字" * 1001, ["a", "b", "c"], ["x"]))


def test_risky_words():
    issues = hard_check("全网第一好用", GOOD_BODY + "加我vx领资料", ["a", "b", "c"], ["x"])
    assert any("全网第一" in i and "vx" in i for i in issues)


def test_clean_tags():
    assert clean_tags(["#穿搭", "穿搭", " 通勤 ", ""]) == ["穿搭", "通勤"]


def test_duplicate_detection_catches_rephrasing():
    assert is_duplicate("秋季通勤叠穿公式", ["秋季通勤叠穿公式！"])
    assert is_duplicate("学生党秋季通勤穿搭", ["秋季通勤穿搭（学生党版）"])
    assert not is_duplicate("宿舍收纳神器推荐", ["秋季通勤叠穿公式"])
    assert similarity("", "abc") == 0


def test_shorten_title():
    from mediaflow.agents.checks import shorten_title

    assert shorten_title("刚工作别急着存钱！先花3个月把账记明白，我多存了5000块") == "刚工作别急着存钱！先花3个月把账记明白"
    assert shorten_title("短标题") == "短标题"
    assert shorten_title("这" * 25) == "这" * 20
    assert len(shorten_title("月薪5千，发薪日先做3件事，一年存下1万2不是梦")) <= 20
