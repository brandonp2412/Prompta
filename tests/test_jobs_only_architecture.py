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


def test_ui_keeps_jobs_and_forbids_unsafe_chat_actions() -> None:
    app = Path("src/ui/App.svelte").read_text()
    sidebar = Path("src/ui/ChatsPage.svelte").read_text()
    assert "ChatsPage" in app
    assert 'import JobsPage from "./JobsPage.svelte"' in sidebar
    assert '{#if view === "jobs"}' in sidebar
    assert "<JobsPage />" in sidebar
    assert "Machine Gun" not in app
    assert 'fetch("./api/results?' in sidebar
    assert 'fetch("./api/results/"' in sidebar
    assert "localStorage.setItem(preferencesKey" in sidebar
    assert 'fetch("./api/local-chat-pins"' in sidebar
    assert "pinnedIds = Array.isArray(prefs.pinnedIds)" not in sidebar
    assert "/backend-api/pins" not in sidebar
    assert "onNewChat" in sidebar
    for component in Path("src/ui").glob("*.svelte"):
        source = component.read_text()
        assert "Machine Gun" not in source
        assert "/backend-api/conversation" not in source


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


def test_jobs_ui_pause_resume_targets_only_visible_page() -> None:
    page = Path("src/ui/JobsPage.svelte").read_text()
    assert 'role="switch"' not in page
    assert 'visibleJobs.map((job) => job.name)' in page
    assert '"pause_many"' in page
    assert '"resume_many"' in page
    assert "Pause visible" in page
    assert "Resume visible" in page
    assert '"pause_all"' not in page
    assert '"resume_all"' not in page


def test_web_server_exposes_no_mutating_chat_routes() -> None:
    web = Path("src/web.py").read_text()
    assert "/api/jobs" in web
    assert "/api/health" in web
    for route in (
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


def test_passive_capture_is_owned_and_history_free() -> None:
    guardrails = Path("AGENTS.md").read_text().casefold()
    for phrase in (
        "fresh chat",
        "45 minutes without activity",
        "only an explicit user ui reply may reopen",
        "no account-wide history reads",
        "read-only historical recovery may navigate",
        "internal history api calls",
        "global rate-limit backoff",
        "machine gun mode",
        "no raw messages in logs",
    ):
        assert phrase in guardrails
    source = Path("src/response_capture.py").read_text()
    assert "urlopen" not in source
    assert "requests.get" not in source
    assert "/backend-api/conversation/" not in source
