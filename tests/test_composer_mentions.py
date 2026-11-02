from prompta.composer_mentions import NativeMention, expected_native_text, split_native_mentions


def test_known_mentions_route_but_email_and_unknown_mentions_remain_plain() -> None:
    parts = split_native_mentions("Use @Glass then @Web search; email me@example.com and @unknown")
    assert parts == [
        "Use ",
        NativeMention("Glass", "connector"),
        " then ",
        NativeMention("Web search", "tool"),
        "; email me@example.com and @unknown",
    ]
    assert expected_native_text(parts) == (
        "Use Glass  then Web search ; email me@example.com and @unknown"
    )


def test_longer_names_take_precedence_and_repeated_mentions_are_preserved() -> None:
    assert split_native_mentions("@Glass Serena and @glass") == [
        NativeMention("Glass Serena", "connector"),
        " and ",
        NativeMention("Glass", "connector"),
    ]
    assert split_native_mentions("nothing here") == ["nothing here"]
    assert split_native_mentions("a@Glass.com") == ["a@Glass.com"]
