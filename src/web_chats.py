from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from .image_store import image_refs
from .reply_contracts import ReplyConflict, ReplyIntent
from .web_models import (
    EmptyRequest,
    FollowupRequest,
    FreshChatRequest,
    ImageUpload,
    PinImport,
    PinRequest,
    ReadImport,
    ReadRequest,
    ReplyRequest,
    RequestId,
    ResultsQuery,
)

if TYPE_CHECKING:
    from .web import WebServices


def register_chat_routes(app: FastAPI, local: WebServices) -> None:
    @app.head("/api/chats/requests/{request_id}", include_in_schema=False)
    @app.get("/api/chats/requests/{request_id}")
    def receipt(request_id: RequestId) -> dict[str, object]:
        record = local.queue.get("manual-" + request_id)
        if record is None or record["client_id"] not in (
            "manual:" + request_id,
            "manual:once:" + request_id,
        ):
            raise HTTPException(404, "Queue request not found")
        return {"send_id": record["send_id"], "status": record["status"]}

    @app.post("/api/chats", status_code=202)
    def fresh_chat(payload: FreshChatRequest) -> dict[str, object]:
        refs = image_refs(payload.images)
        for ref in refs:
            local.images.path(ref)
        accepted = local.queue.enqueue_manual(
            payload.prompt.strip(),
            images=refs,
            request_id=payload.request_id,
            pin_local_default=True,
        )
        return {"ok": True, "send_id": accepted["send_id"], "status": accepted["status"]}

    @app.post("/api/images")
    def upload(payload: ImageUpload) -> dict[str, object]:
        ref = local.images.save(payload.name, payload.data)
        return {
            "ok": True,
            "image": {"ref": ref, "name": ref.split("/", 1)[1], "url": "./api/images/" + ref},
        }

    @app.head("/api/images/{ref:path}", include_in_schema=False)
    @app.get("/api/images/{ref:path}")
    def image(ref: str) -> Response:
        try:
            mime, body = local.images.read(ref)
        except ValueError as exc:
            raise HTTPException(404) from exc
        return Response(body, media_type=mime)

    @app.head("/api/results", include_in_schema=False)
    @app.get("/api/results")
    def results(request: Request, params: Annotated[ResultsQuery, Query()]) -> dict[str, object]:
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValueError("Invalid result query")
        page = local.results.page(
            limit=params.limit, offset=params.offset, query=params.q.strip(), status=params.status
        )
        local.replies.annotate_response_markers(page["items"])
        local.results.annotate_local_reads(page["items"])
        return dict(page)

    @app.head("/api/results/{send_id}/turns", include_in_schema=False)
    @app.get("/api/results/{send_id}/turns")
    def turns(send_id: str) -> dict[str, object]:
        items = local.replies.turns(send_id)
        if items is None:
            raise HTTPException(404, "Run not found")
        return {"turns": items}

    @app.head("/api/results/{send_id}", include_in_schema=False)
    @app.get("/api/results/{send_id}")
    def detail(send_id: str) -> dict[str, object]:
        record = local.results.detail(send_id)
        if record is None:
            raise HTTPException(404, "Run not found")
        local.replies.annotate_response_markers([record])
        local.results.annotate_local_reads([record])
        queued = local.queue.get(send_id)
        record["images"] = (
            [
                {"name": ref.split("/", 1)[1], "url": "./api/images/" + ref}
                for ref in image_refs(queued["images"])
            ]
            if queued is not None
            else []
        )
        return record

    @app.post("/api/results/{send_id}/reply-recover")
    def recover(send_id: str, payload: EmptyRequest) -> dict[str, object]:
        return {"ok": True, **local.reply_dispatch.recover(send_id)}

    @app.post("/api/results/{send_id}/reply-queue", status_code=202)
    def followup(send_id: str, payload: FollowupRequest) -> dict[str, object]:
        return {
            "ok": True,
            "turn": local.replies.queue_followup(send_id, payload.reply_id, payload.text),
        }

    @app.post("/api/results/{send_id}/reply-intents", status_code=202)
    def prepare_reply(send_id: str, payload: ReplyRequest) -> dict[str, object]:
        turn = local.replies.prepare(
            send_id,
            ReplyIntent(payload.reply_id, payload.conversation_id, payload.parent_id, payload.text),
        )
        return {"ok": True, "dispatched": False, "turn": turn}

    @app.post("/api/results/{send_id}/reply-send", status_code=202)
    def send_reply(send_id: str, payload: ReplyRequest) -> dict[str, object]:
        turn = local.replies.queue_explicit_send(
            send_id,
            ReplyIntent(payload.reply_id, payload.conversation_id, payload.parent_id, payload.text),
        )
        return {
            "ok": True,
            "dispatched": False,
            "queued_for_explicit_dispatch": turn["status"] == "prepared",
            "turn": turn,
        }

    @app.head("/api/local-chat-pins", include_in_schema=False)
    @app.get("/api/local-chat-pins")
    def pins() -> dict[str, object]:
        items = local.results.local_pinned_runs()
        local.replies.annotate_response_markers(items)
        local.results.annotate_local_reads(items)
        return {"items": items}

    @app.post("/api/local-chat-pins")
    def pin(payload: PinRequest) -> dict[str, object]:
        if not local.results.set_local_pin(payload.send_id, pinned=payload.pinned):
            raise HTTPException(404, "Local run not found")
        return {"ok": True}

    @app.post("/api/local-chat-pins/import")
    def import_pins(payload: PinImport) -> dict[str, object]:
        local.results.import_legacy_local_pins(payload.send_ids)
        return {"ok": True}

    @app.post("/api/local-chat-reads")
    def read(payload: ReadRequest) -> dict[str, object]:
        record = local.results.detail(payload.send_id)
        if record is None:
            raise HTTPException(404, "Local run not found")
        local.replies.annotate_response_markers([record])
        if not payload.revision or record["last_reply_revision"] != payload.revision:
            raise ReplyConflict("Reply revision changed")
        local.results.mark_local_read(payload.send_id, payload.revision)
        return {"ok": True}

    @app.post("/api/local-chat-reads/import")
    def import_reads(payload: ReadImport) -> dict[str, object]:
        local.results.import_legacy_local_reads(payload.reads)
        return {"ok": True}

    @app.post("/api/local-chat-reads/all")
    def read_all(payload: EmptyRequest) -> dict[str, object]:
        return {"ok": True, "count": local.replies.mark_all_local_read()}
