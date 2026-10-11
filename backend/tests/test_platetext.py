from platedex.services.platetext import (
    clean_display,
    is_partial,
    lookalike_pairs,
    match_score,
    normalize,
    normalize_state,
    parse_query,
    partial_matches,
    skeleton,
)


def test_normalize_and_display():
    assert normalize("dhk-4821") == "DHK4821"
    assert normalize("7a?123") == "7A?123"
    assert clean_display(" kgt·5527 ") == "KGT-5527"
    assert is_partial("7A?123")
    assert not is_partial("GR8FUL")


def test_skeleton_folds_lookalikes():
    assert skeleton("B0SS") == skeleton("8OSS")
    assert skeleton("GR8FUL") == skeleton("GR8FU1")
    assert skeleton("LUVU2") == skeleton("LUVVZ")
    assert skeleton("SL0WPKE") == skeleton("SLOWPKE")
    assert skeleton("ABC") != skeleton("ABD")


def test_lookalike_pairs():
    assert lookalike_pairs("GR8FUL", "GR8FU1") == [("L", "1")]
    assert lookalike_pairs("GR8FUL", "GR8FUN") == []
    assert lookalike_pairs("ABC", "ABCD") == []


def test_partial_matches():
    assert partial_matches("7A?123", "7AB123")
    assert not partial_matches("7A?123", "7AB124")


def test_state_normalization():
    assert normalize_state("tx") == "TX"
    assert normalize_state("New Mexico") == "NM"
    assert normalize_state("Narnia") is None


def score(q, text, hay=""):
    return match_score(parse_query(q), text, hay)


def test_wildcards():
    assert score("7AB*", "7ABC123") > 0
    assert score("7AB*", "8ABC123") == 0
    assert score("7A?12", "7A?123") > 0  # stored partial
    assert score("7A?12", "7AB123") > 0
    assert score("7A?12", "7XY123") == 0


def test_fuzzy_is_lookalike_aware():
    assert score("~LUVU2", "LUVU2") > 0
    assert score("~LUVV2", "LUVU2") > 0
    assert score("~1UVU2", "LUVU2") > 0
    assert score("~GR8FU1", "GR8FUL") > 0
    assert score("~ZZZZ", "LUVU2") == 0


def test_plain_text_and_words():
    assert score("GR8FUL", "GR8FUL") > score("GR8", "GR8FUL") > 0
    assert score("4821", "DHK-4821") > 0
    assert score("grateful", "GR8FUL", "grateful vanity deadhead") > 0
    assert score("ski", "NOTMYCAR", "not my car vanity ski Silver Subaru") > 0
    assert score("#ski", "NOTMYCAR", "vanity ski") > 0
    assert score("boat", "NOTMYCAR", "vanity ski") == 0
    assert score("", "ANY") > 0
