import re
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
    app = Path("src/ui/App.tsx").read_text()
    sidebar = Path("src/ui/ChatsPage.tsx").read_text()
    assert "ChatsPage" in app
    assert 'import JobsPage from "./JobsPage"' in sidebar
    assert 'view.value === "jobs"' in sidebar
    assert "<JobsPage workspace={jobsWorkspace.value}" in sidebar
    assert "Machine Gun" not in app
    controller = Path("src/ui/ChatsPageController.ts").read_text()
    assert 'localGet("./api/results?' in controller
    local_reads = Path("src/ui/localRead.ts").read_text()
    assert 'cache: "no-store"' in local_reads
    assert "AbortSignal.timeout" in local_reads
    assert '"./api/results/" + encodeURIComponent(sendId) + "/reply-recover"' in controller
    assert re.search(r"localStorage\.setItem\(\s*preferencesKey", controller)
    assert re.search(r'localPost\(\s*"\./api/local-chat-pins"', controller)
    local_mutations = Path("src/ui/localMutation.ts").read_text()
    assert 'cache: "no-store"' in local_mutations
    assert "AbortSignal.timeout(timeoutMs)" in local_mutations
    assert 'method: "POST"' in local_mutations
    assert "return fetch(url, {" in local_mutations
    assert "pinnedIds = Array.isArray(prefs.pinnedIds)" not in controller
    assert "/backend-api/pins" not in controller
    assert "onNewChat" in sidebar
    assert not list(Path("src/ui").glob("*.svelte"))
    for component in Path("src/ui").glob("*.tsx"):
        source = component.read_text()
        assert "Machine Gun" not in source
        assert "/backend-api/conversation" not in source


def test_jobs_api_requests_are_relative_to_deployment_prefix() -> None:
    page = Path("src/ui/JobsPageController.ts").read_text()
    assert 'localPost("./api/jobs", payload)' in page
    assert 'localGet("./api/jobs")' in page
    assert 'localPost("/api/jobs"' not in page
    assert 'fetch("/api/jobs"' not in page


def test_jobs_ui_is_paginated() -> None:
    page = Path("src/ui/JobsPageController.ts").read_text()
    jsx = Path("src/ui/JobsPage.tsx").read_text()
    table = Path("src/ui/JobsTable.tsx").read_text()
    assert "const pageSize = 10" in page
    assert "<JobsTable model={model} />" in jsx
    assert "visibleJobs.value.map((job" in table
    assert 'aria-label="Job pages"' in table
    assert "Previous" in table
    assert "Next" in table


def test_jobs_ui_pause_resume_targets_only_visible_page() -> None:
    page = Path("src/ui/JobsPageController.ts").read_text()
    jsx = Path("src/ui/JobsPage.tsx").read_text()
    assert 'role="switch"' not in jsx
    assert 'visibleJobs.value.map((job) => job.name)' in page
    assert '"pause_many"' in page
    assert '"resume_many"' in page
    assert "Pause visible" in jsx
    assert "Resume visible" in jsx
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
        "read-only rate-limit backoff",
        "machine gun mode",
        "no raw messages in logs",
    ):
        assert phrase in guardrails
    source = Path("src/response_capture.py").read_text()
    assert "urlopen" not in source
    assert "requests.get" not in source
    assert "/backend-api/conversation/" not in source
