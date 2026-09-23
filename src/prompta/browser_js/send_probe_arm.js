() => {
  const previous = window.__promptaSendProbeOriginalFetch || window.fetch;
  window.__promptaSendProbeOriginalFetch = previous;

  const probe = {
    message_id: "",
    parent_message_id: "",
    conversation_id: "",
    response_status: 0,
    committed: false,
    stream_error: "",
  };
  window.__promptaSendProbe = probe;

  const captureBody = (text) => {
    try {
      const body = JSON.parse(text || "{}");
      probe.message_id = body.messages?.[0]?.id || "";
      probe.parent_message_id = body.parent_message_id || "";
    } catch (_) {}
  };

  window.fetch = function (input, init) {
    let isSend = false;
    let request = null;
    try {
      request = new Request(input instanceof Request ? input.clone() : input, init);
      const url = new URL(request.url, location.href);
      isSend =
        request.method === "POST" &&
        (url.pathname === "/backend-api/f/conversation" ||
          url.pathname === "/backend-api/conversation");
      if (isSend) {
        if (typeof init?.body === "string") {
          captureBody(init.body);
        } else {
          request.clone().text().then(captureBody).catch(() => {});
        }
      }
    } catch (_) {}

    const result = previous.apply(this, arguments);
    if (!isSend) return result;

    return result.then(
      (response) => {
        probe.response_status = response.status;
        try {
          const reader = response.clone().body?.getReader();
          if (reader) {
            const decoder = new TextDecoder();
            let buffer = "";
            let chunks = 0;
            (async () => {
              try {
                while (chunks < 24 && buffer.length < 65536) {
                  const item = await reader.read();
                  if (item.done) break;
                  chunks += 1;
                  buffer += decoder.decode(item.value, { stream: true });
                  if (!probe.conversation_id) {
                    const match = buffer.match(
                      /["']conversation_id["'][ ]*:[ ]*["']([^"']+)["']/,
                    );
                    if (match) probe.conversation_id = match[1];
                  }
                  const id = probe.message_id;
                  if (
                    id &&
                    buffer.includes('\"type\":\"input_message\"') &&
                    buffer.includes('\"id\":\"' + id + '\"')
                  ) {
                    probe.committed = true;
                    try {
                      await reader.cancel();
                    } catch (_) {}
                    break;
                  }
                }
              } catch (error) {
                probe.stream_error = String(error || "stream probe failed");
              }
            })();
          }
        } catch (error) {
          probe.stream_error = String(error || "stream probe setup failed");
        }
        return response;
      },
      (error) => {
        probe.stream_error = String(error || "fetch failed");
        throw error;
      },
    );
  };

  return true;
}
