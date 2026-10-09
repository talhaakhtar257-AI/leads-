from leadscout.scoring import relevant_signals, score_lead


def test_strong_lead_scores_high():
    biz = {"signals": ["no_website", "few_reviews"], "email": "a@b.pk", "phone": "0300"}
    assert score_lead(biz, "web_design") == 45 + 15


def test_need_is_capped_and_reach_added():
    biz = {"signals": ["site_down", "no_https", "not_mobile_friendly", "outdated_copyright"], "email": "a@b.pk", "phone": "1"}
    assert score_lead(biz, "web_design") == 100


def test_unreachable_lead_is_capped():
    assert score_lead({"signals": ["no_website", "social_only"], "email": None, "phone": None}, "web_design") == 20


def test_service_changes_relevance():
    signals = ["no_booking", "no_website", "few_reviews"]
    assert relevant_signals(signals, "booking_system")[0] == "no_booking"
    assert relevant_signals(signals, "reputation") == ["few_reviews"]
    assert score_lead({"signals": ["no_booking"], "phone": "1"}, "reputation") == 5
