# Prompta

Prompta schedules one-off and recurring prompts for ChatGPT. Jobs can be managed from the CLI or the mobile-friendly web UI; each run opens a fresh ChatGPT chat, submits the prompt, and leaves the response to ChatGPT.

<p align="center">
  <img src="docs/prompta-cli.png" alt="Prompta CLI" width="900">
</p>

<p align="center">
  <img src="docs/prompta-ui-mobile.png" alt="Prompta web UI on mobile" width="360">
</p>

## Run

```bash
git clone https://github.com/brandonp2412/Prompta.git ~/prompta
cd ~/prompta
uv sync --locked
bun install --frozen-lockfile
bun run build

mkdir -p ~/.config/systemd/user
cp systemd/prompta-*.service systemd/prompta.target ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now prompta.target
```

The UI is at `http://127.0.0.1:8765`. The CLI is available as `uv run prompta`, for example:

```bash
uv run prompta add nightly-review "Review the project and improve it" --daily-at 21:00
uv run prompta list
```

## Login to ChatGPT

Prompta uses a dedicated Chromium profile. Stop the background browser, open that same profile visibly, and log in at ChatGPT:

```bash
systemctl --user stop prompta-browser.service

/opt/brave-bin/brave \
  --user-data-dir="$HOME/.local/state/prompta/chrome-profile" \
  --profile-directory=Default \
  --password-store=basic \
  --remote-debugging-port=9222 \
  https://chatgpt.com
```

After login, close that browser window and start Prompta's browser again:

```bash
systemctl --user start prompta-browser.service
```
