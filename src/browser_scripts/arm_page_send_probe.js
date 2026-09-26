(() => {
  window.__promptaSendProbe?.cancel?.();
  const previous = window.__promptaSendProbeOriginalFetch || window.fetch;
  window.__promptaSendProbeOriginalFetch = previous;
  const probe = {
    message_id: '', parent_message_id: '', conversation_id: '',
    response_status: 0, committed: false, stream_error: '',
  };
  window.__promptaSendProbe = probe;
  let captured = false;
  let stopped = false;
  let reader;
  let timer;
  probe.cancel = () => {
    stopped = true;
    clearTimeout(timer);
    if (reader) {
      try { void reader.cancel().catch(() => {}); } catch (_) {}
    }
  };
  const captureBody = text => {
    try {
      const body = JSON.parse(text || '{}');
      probe.message_id = body.messages?.[0]?.id || '';
      probe.parent_message_id = body.parent_message_id || '';
    } catch (_) {}
  };
  const inspect = value => {
    if (!value || typeof value !== 'object') return;
    if (typeof value.conversation_id === 'string') {
      probe.conversation_id = value.conversation_id;
    }
    if (value.type === 'input_message' && probe.message_id &&
        [value.id, value.message?.id, value.input_message?.id].includes(probe.message_id)) {
      probe.committed = true;
    }
    for (const child of Object.values(value)) inspect(child);
  };
  const inspectEvent = event => {
    const data = event.split(/\r?\n/)
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart()).join('\n');
    if (!data || data === '[DONE]') return;
    try { inspect(JSON.parse(data)); } catch (_) {}
  };
  window.fetch = function(input, init) {
    let isSend = false;
    let bodyReady;
    try {
      const url = new URL(input instanceof Request ? input.url : input, location.href);
      const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
      isSend = !captured && !stopped && method === 'POST' && url.origin === location.origin &&
        ['/backend-api/f/conversation', '/backend-api/conversation'].includes(url.pathname);
      if (isSend) {
        captured = true;
        if (typeof init?.body === 'string') {
          captureBody(init.body);
        } else if (input instanceof Request) {
          bodyReady = new Request(input.clone(), init).text().then(captureBody).catch(() => {});
        }
      }
    } catch (_) {}
    const result = previous.apply(this, arguments);
    if (!isSend) return result;
    return result.then(response => {
      probe.response_status = response.status;
      if (stopped || !response.ok) return response;
      try {
        reader = response.clone().body?.getReader();
        if (reader) {
          timer = setTimeout(probe.cancel, 15000);
          void (async () => {
            const decoder = new TextDecoder();
            let buffer = '';
            let bytes = 0;
            try {
              await bodyReady;
              while (!stopped && bytes < 65536) {
                const item = await reader.read();
                if (item.done) break;
                bytes += item.value.byteLength;
                buffer += decoder.decode(item.value, {stream: true});
                let boundary;
                while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
                  inspectEvent(buffer.slice(0, boundary.index));
                  buffer = buffer.slice(boundary.index + boundary[0].length);
                }
                if (probe.committed || bytes >= 65536) break;
              }
            } catch (error) {
              probe.stream_error = String(error || 'stream probe failed');
            } finally {
              probe.cancel();
            }
          })();
        }
      } catch (error) {
        probe.stream_error = String(error || 'stream probe setup failed');
        probe.cancel();
      }
      return response;
    }, error => {
      probe.stream_error = String(error || 'fetch failed');
      probe.cancel();
      throw error;
    });
  };
  return true;
})()
