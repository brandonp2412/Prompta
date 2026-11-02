from web_results_support import post_json, server


def test_bump_routes_reorder_existing_deliveries_and_reject_missing(tmp_path):
    with server(tmp_path) as (app, port):
        for send_id, client in (("first", "manual:first"), ("second", "scheduled:key:Test job")):
            app.queue.upsert({"send_id": send_id, "message": "hello", "client_id": client, "status": "queued", "created_at": 10})
        assert post_json(port, "/api/queue-jobs/Test%20job/front", {})[0] == 200
        assert app.queue.pending_dispatch_metadata()[0]["send_id"] == "second"
        assert post_json(port, "/api/queue/first/front", {})[0] == 200
        assert app.queue.pending_dispatch_metadata()[0]["send_id"] == "first"
        assert post_json(port, "/api/queue/missing/front", {})[0] == 409
        assert post_json(port, "/api/queue-jobs/missing/front", {})[0] == 409
        assert len(app.queue.records()) == 2
