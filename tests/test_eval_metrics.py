from evals import metrics
from evals.taxonomy import category_for_service


def test_groups_match_handles_markdown_and_fullwidth():
    assert metrics.groups_match("The **Tameike Suzuki** Building, Akasaka", [["tameike suzuki"], ["akasaka"]])
    assert metrics.groups_match("ＶＣ＠npo-jibb.org", [["vc@npo-jibb.org"]])
    assert metrics.groups_match("+91‑70000‑17005", [["70000-17005"]])
    assert not metrics.groups_match("Noida only", [["akasaka", "tameike"]])


def test_retrieval_hit_requires_all_groups_in_top_k():
    ctx = ["a", "b", "c", "d", "e", "imtex"]
    assert metrics.retrieval_hit(ctx, [["imtex"]]) is False  # 6th chunk is outside top-5
    assert metrics.retrieval_hit(ctx, [["a"], ["e"]]) is True
    assert metrics.retrieval_hit(ctx, []) is None


def test_language_detection():
    assert metrics.replied_in_language("東京本社は赤坂にあります。", "ja")
    assert not metrics.replied_in_language("The Tokyo office is in Akasaka.", "ja")
    assert metrics.replied_in_language("The Tokyo office is in Akasaka.", "en")


def test_asks_for_contact():
    assert metrics.asks_for_contact("Could you please share your work email address?")
    assert metrics.asks_for_contact("メールアドレスを教えていただけますか？")
    assert not metrics.asks_for_contact("The Tokyo office is in Akasaka.")


def test_lead_matches():
    exp = {"name": "Kenji Tanaka", "email": "k@example.jp", "interest_category": "partner_identification"}
    got = {"name": "kenji tanaka", "email": "K@example.jp", "interest_category": "partner_identification"}
    assert metrics.lead_matches(got, exp)["lead_ok"]
    assert not metrics.lead_matches(None, exp)["lead_ok"]
    assert metrics.lead_matches(None, None)["lead_ok"]


def test_taxonomy_maps_legacy_service_labels():
    assert category_for_service("Market Landscaping") == "market_landscaping"
    assert category_for_service("Back Office & Corporate Support") == "back_office"
    assert category_for_service("membership") == "membership"
    assert category_for_service(None) is None
