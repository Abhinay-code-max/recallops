from app.memory import pattern_siblings


def test_pattern_siblings_finds_same_signature_incidents() -> None:
    siblings = pattern_siblings("INC-002")
    sibling_ids = {inc["incident_id"] for inc in siblings}
    # INC-002/009/017/021 all share postgres_pool_exhaustion; siblings excludes itself.
    assert sibling_ids == {"INC-009", "INC-017", "INC-021"}
    assert all(inc["error_signature"] == "postgres_pool_exhaustion" for inc in siblings)


def test_pattern_siblings_excludes_the_incident_itself() -> None:
    siblings = pattern_siblings("INC-002")
    assert "INC-002" not in {inc["incident_id"] for inc in siblings}


def test_pattern_siblings_empty_for_unique_signature() -> None:
    # INC-012 is the only expired_tls_cert incident.
    assert pattern_siblings("INC-012") == []


def test_pattern_siblings_unknown_incident_id_returns_empty() -> None:
    assert pattern_siblings("INC-999") == []
