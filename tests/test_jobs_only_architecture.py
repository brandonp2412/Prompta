from pathlib import Path


def test_chat_client_modules_are_absent() -> None:
    removed = {
        "cache.py",
        "conversation_actions.py",
        "conversation_snapshot.py",
        "conversation_tracker.py",
        "conversation_worker.py",
        "pinned_chats.py",
        "read_state.py",
        "structured_capture.py",
        "transcript_browser_engine.py",
        "web_store.py",
    }
    assert removed.isdisjoint({path.name for path in Path("src").glob("*.py")})


def test_ui_contains_only_jobs_surface() -> None:
    assert {path.name for path in Path("src/ui").glob("*")} == {
        "App.svelte",
        "JobsPage.svelte",
        "main.ts",
    }
    app = Path("src/ui/App.svelte").read_text()
    assert "JobsPage" in app
    assert "PromptaPage" not in app
    assert "Machine Gun" not in app
    assert "Jobs only" not in app


def test_jobs_api_requests_are_relative_to_deployment_prefix() -> None:
    page = Path("src/ui/JobsPage.svelte").read_text()
    assert 'fetch("./api/jobs"' in page
    assert 'fetch("/api/jobs"' not in page


def test_jobs_ui_is_paginated() -> None:
    page = Path("src/ui/JobsPage.svelte").read_text()
    assert "const pageSize = 10" in page
    assert "{#each visibleJobs as job" in page
    assert 'aria-label="Job pages"' in page
    assert "Previous" in page
    assert "Next" in page


def test_web_server_exposes_no_chat_or_result_routes() -> None:
    web = Path("src/web.py").read_text()
    assert "/api/jobs" in web
    assert "/api/health" in web
    for route in (
        "/api/chats",
        "/api/messages",
        "/api/send",
        "/api/reply",
        "/api/pins",
        "/api/read",
        "/api/logs",
    ):
        assert route not in web


def test_machine_gun_and_unattended_modes_are_removed() -> None:
    source = "\n".join(path.read_text() for path in Path("src").glob("*.py"))
    lowered = source.casefold()
    assert "machine gun" not in lowered
    assert "machine_gun" not in lowered
    assert "unattended_mode" not in lowered
