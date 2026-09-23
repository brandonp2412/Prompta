from prompta.read_state import ConversationReadState


def test_read_state_baseline_and_persistence(tmp_path):
    now = [100.0]
    state = ConversationReadState(tmp_path, clock=lambda: now[0])

    decorated = state.decorate(
        [
            {"id": "historical", "last_assistant_at": 99.0},
            {"id": "fresh", "last_assistant_at": 101.0},
            {"id": "no-assistant", "last_assistant_at": None},
        ]
    )

    assert [chat["unread"] for chat in decorated] == [False, True, False]

    now[0] = 102.0
    state.mark_read("fresh")
    assert state.decorate([{"id": "fresh", "last_assistant_at": 101.0}])[0]["unread"] is False

    now[0] = 200.0
    restarted = ConversationReadState(tmp_path, clock=lambda: now[0])
    decorated = restarted.decorate(
        [
            {"id": "fresh", "last_assistant_at": 103.0},
            {"id": "new-after-restart", "last_assistant_at": 150.0},
            {"id": "still-historical", "last_assistant_at": 99.0},
        ]
    )

    assert [chat["unread"] for chat in decorated] == [True, True, False]


def test_mark_read_rejects_empty_conversation_id(tmp_path):
    state = ConversationReadState(tmp_path, clock=lambda: 100.0)

    try:
        state.mark_read("   ")
    except ValueError as exc:
        assert str(exc) == "Conversation id is required"
    else:
        raise AssertionError("Expected an empty conversation id to be rejected")
