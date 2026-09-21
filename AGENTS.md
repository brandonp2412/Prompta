# Agent workflow

- At the end of every work session, rebase validated work onto `main`, fast-forward `main` to include it, push `main`, and deploy Prompta.
- Serialize all `main` integration work with the shared lock file `/home/brandon/prompta/.git/prompta-main-merge.lock`. Acquire it with `flock` before fetching/rebasing against `main`, fast-forwarding `main`, or pushing `main`, and hold it until the push completes. Deploy only after the updated `main` is pushed.
- If the main-merge lock is already held, wait for it instead of attempting a concurrent fetch/rebase, merge, fast-forward, or push. Do not delete the lock file to bypass another worker; `flock` ownership is released automatically when the owning process exits.
