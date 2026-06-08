const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const isWin = process.platform === "win32";

function findPython() {
  const candidates = [
    path.resolve(__dirname, "..", "sidecar", ".venv", "Scripts", "python.exe"),
    path.resolve(__dirname, "..", "sidecar", ".venv_new", "Scripts", "python.exe"),
    path.resolve(__dirname, "..", "sidecar", "venv", "Scripts", "python.exe"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return "python";
}

const python = findPython();
console.log(`[dev] Using Python: ${python}`);

// Sidecar
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

let shuttingDown = false;
let exitedCount = 0;

function forceKill(child, label) {
  if (child.exitCode !== null) return; // already exited
  try {
    if (isWin) {
      // Windows: taskkill /T kills the process tree
      spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGKILL");
    }
  } catch (e) {
    // ignore
  }
}

function gracefulKill(child, label) {
  if (child.exitCode !== null) return;
  try {
    if (isWin) {
      child.kill(); // default SIGTERM equivalent on libuv
    } else {
      child.kill("SIGTERM");
    }
  } catch (e) {
    // ignore
  }
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log("\n[dev] Shutting down...");

  gracefulKill(sidecar, "sidecar");
  gracefulKill(tauri, "tauri");

  // Force-kill after 2s if still running
  const forceTimer = setTimeout(() => {
    forceKill(sidecar, "sidecar");
    forceKill(tauri, "tauri");
  }, 2000);

  // Wait for both to actually exit before process.exit
  const check = setInterval(() => {
    if (sidecar.exitCode !== null && tauri.exitCode !== null) {
      clearInterval(check);
      clearTimeout(forceTimer);
      process.exit(code);
    }
  }, 100);
}

function onChildExit(label, code) {
  console.log(`[${label}] exited ${code !== null ? code : ""}`);
  exitedCount++;
  if (exitedCount >= 2) {
    // Both gone — clean exit
    process.exit(0);
  }
}

sidecar.on("close", (code) => onChildExit("sidecar", code));
tauri.on("close", (code) => onChildExit("tauri", code));

// Raw-mode stdin so 'q' works without Enter
if (process.stdin.isTTY) {
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (data) => {
    const ch = data[0];
    if (ch === "q" || ch === "Q") {
      console.log("\n[dev] Shutdown requested.");
      shutdown(0);
    } else if (ch === "\u0003") {
      // Ctrl+C
      shutdown(0);
    }
  });
} else {
  // Fallback for non-TTY (e.g. piped CI)
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (data) => {
    if (data.trim().toLowerCase() === "q") {
      console.log("\n[dev] Shutdown requested.");
      shutdown(0);
    }
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

