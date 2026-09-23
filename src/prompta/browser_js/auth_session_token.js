async () => {
  try {
    const response = await fetch("/api/auth/session");
    const session = await response.json();
    return JSON.stringify({
      ok: response.ok,
      token: session.accessToken || session.access_token || "",
    });
  } catch (_) {
    return JSON.stringify({ ok: false, token: "" });
  }
}
