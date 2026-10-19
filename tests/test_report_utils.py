from src.reports.build_reports import _narrative_is_grounded, _pct, _signed_pct


def test_formatters():
    assert _pct(0.1234) == "12.34%"
    assert _signed_pct(0.1) == "+10.0%"


def test_narrative_grounding_accepts_known_numbers():
    facts = {"current": {"applications": 1200, "approval_rate": 0.3456}}
    assert _narrative_is_grounded("本期进件 1,200 笔，通过率 34.56%。", facts)


def test_narrative_grounding_rejects_many_unknown_numbers():
    facts = {"current": {"applications": 1200}}
    assert not _narrative_is_grounded("本期进件 9,999 笔，增长 88.8%，金额 7,777 万元。", facts)

