import { spawn, spawnSync } from "node:child_process";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const stateDir = resolve(process.env.PROMPTA_DEV_STATE_DIR || join(root, ".prompta-dev"));
const apiPort = process.env.PROMPTA_DEV_API_PORT || "18765";
const apiTarget = process.env.PROMPTA_DEV_API_TARGET || `http://127.0.0.1:${apiPort}`;
const children = [];
let stopping = false;

function stop() {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
  }
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);

function start(label, command, args, env = process.env) {
  const child = spawn(command, args, { cwd: root, env, stdio: "inherit" });
  children.push(child);
  child.on("error", (error) => {
    console.error(`[dev] ${label} failed: ${error.message}`);
    process.exitCode = 1;
    stop();
  });
  child.on("exit", (code, signal) => {
    if (stopping) return;
    console.error(`[dev] ${label} exited (${signal || code}); shutting down.`);
    process.exitCode = code || 1;
    stop();
  });
}

if (!process.env.PROMPTA_DEV_API_TARGET) {
  console.log(`[dev] Initializing isolated API state: ${stateDir}`);
  const migration = spawnSync("uv", ["run", "--locked", "prompta-migrate", "--state-dir", stateDir], {
    cwd: root,
    stdio: "inherit",
  });
  if (migration.error || migration.status !== 0) {
    console.error("[dev] Could not initialize the local API:", migration.error?.message || migration.status);
    process.exit(1);
  }
  start("API", "uv", [
    "run", "--no-sync", "prompta-ui", "--host", "127.0.0.1", "--port", apiPort,
    "--state", join(stateDir, "runtime.sqlite3"),
    "--jobs-file", join(stateDir, "runtime.sqlite3"),
  ], {
    ...process.env,
    PROMPTA_DEV_MODE: "1",
    PROMPTA_CONFIG_PATH: join(stateDir, "config.toml"),
  });
} else {
  console.warn(`[dev] Using external API ${apiTarget}; its data may be live.`);
}

console.log(`[dev] UI: http://127.0.0.1:5173 (API: ${apiTarget})`);
start("Vite", "bun", ["x", "vite"], { ...process.env, PROMPTA_DEV_API_TARGET: apiTarget });
