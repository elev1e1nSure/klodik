const { spawn } = require("child_process");
const path = require("path");

const isWin = process.platform === "win32";

// Sidecar
const python = path.resolve(__dirname, "..", "sidecar", ".venv_new", "Scripts", "python.exe");
const sidecar = spawn(python, [path.resolve(__dirname, "..", "sidecar", "main.py")], {
  stdio: "inherit",
  shell: isWin,
});

// Tauri dev
const tauri = spawn("pnpm", ["tauri", "dev"], {
  cwd: path.resolve(__dirname, ".."),
  stdio: "inherit",
  shell: isWin,
});

function shutdown(code) {
  sidecar.kill();
  tauri.kill();
  process.exit(code);
}

sidecar.on("close", (code) => {
  console.log(`[sidecar] exited ${code}`);
  shutdown(code || 0);
});

tauri.on("close", (code) => {
  console.log(`[tauri] exited ${code}`);
  shutdown(code || 0);
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
