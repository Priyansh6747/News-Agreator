#!/usr/bin/env python3
"""Sync the environments and run the API + web dev servers with live logs."""

from __future__ import annotations

import argparse
import atexit
import json
import locale
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import curses
except ImportError:  # pragma: no cover - Windows without windows-curses
    curses = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
WEB_DIR = ROOT / "web"

DEFAULT_API_PORT = 8012
DEFAULT_WEB_PORT = 3000

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-_])")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

PAIR_IDS = {"api": 1, "web": 2, "ok": 3, "warn": 4, "err": 5, "accent": 6}
STATE_GLYPHS = {
    "pending": ("·", "dim"),
    "ok": ("✓", "ok"),
    "failed": ("✗", "err"),
    "skipped": ("–", "dim"),
}

DIRTY = threading.Event()
LIVE: list[Service] = []
UV = "uv"
BUN = "bun"
META = ""

IS_WINDOWS = os.name == "nt"
CURSES_AVAILABLE = curses is not None


def _popen_group_kwargs() -> dict[str, int]:
    """Start each service in its own group so both children can be stopped."""
    if IS_WINDOWS:
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        }
    return {"start_new_session": True}


def _command(executable: str, *args: str) -> list[str]:
    """Build a launchable command, wrapping .cmd/.bat shims on Windows."""
    if IS_WINDOWS and executable.lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [
            comspec,
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline([executable, *args]),
        ]
    return [executable, *args]


def _taskkill(pid: int, *, force: bool) -> None:
    command = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _terminate_process(
    proc: subprocess.Popen[str] | None,
    *,
    force: bool = False,
) -> None:
    """Terminate a service tree with the right primitive for the OS."""
    if proc is None or proc.poll() is not None:
        return

    if IS_WINDOWS:
        if force:
            _taskkill(proc.pid, force=True)
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass
            return
        ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break is not None:
            try:
                proc.send_signal(ctrl_break)
                return
            except (OSError, ValueError):
                pass
        try:
            proc.terminate()
        except OSError:
            pass
        return

    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except OSError:
        try:
            if force:
                proc.kill()
            else:
                proc.terminate()
        except OSError:
            pass


def _check_tool(name: str, executable: str) -> bool:
    """Verify the tool resolves and can actually run."""
    try:
        result = subprocess.run(
            _command(executable, "--version"),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"start: {name} at {executable} could not run: {exc}",
            file=sys.stderr,
        )
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[:3]
        print(
            f"start: {name} at {executable} is not usable "
            f"(exit {result.returncode})",
            file=sys.stderr,
        )
        for line in detail:
            print(f"  {line}", file=sys.stderr)
        return False
    return True


def clean_line(raw: str) -> str:
    line = raw.replace("\r\n", "\n")
    if "\r" in line:
        line = line.rsplit("\r", 1)[-1]
    line = ANSI_RE.sub("", line)
    line = line.replace("\t", "    ")
    line = CONTROL_RE.sub("", line)
    return line.rstrip()


@dataclass
class Service:
    key: str
    label: str
    url: str
    health_url: str
    cmd: list[str]
    cwd: Path
    env: dict[str, str]
    status: str = "starting"
    exit_code: int | None = None
    proc: subprocess.Popen[str] | None = None
    stopping: bool = False
    lines: deque[tuple[str, str]] = field(default_factory=lambda: deque(maxlen=2500))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self.push("$ " + " ".join(self.cmd), "sys")
        try:
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                **_popen_group_kwargs(),
            )
        except OSError as exc:
            self.status = "failed"
            self.exit_code = 127
            self.push(f"could not start: {exc}", "err")
            return
        self.push(f"pid {self.proc.pid}", "sys")
        threading.Thread(target=self._pump, name=f"{self.key}-log", daemon=True).start()
        threading.Thread(target=self._probe, name=f"{self.key}-probe", daemon=True).start()

    def push(self, text: str, level: str = "out") -> None:
        with self.lock:
            self.lines.append((text, level))
        DIRTY.set()

    def snapshot(self) -> list[tuple[str, str]]:
        with self.lock:
            return list(self.lines)

    def status_label(self) -> tuple[str, str]:
        if self.status == "failed":
            return "failed", "err"
        if self.stopping:
            if self.status == "exited":
                return "stopped", "dim"
            return "stopping", "warn"
        if self.status == "ready":
            return "ready", "ok"
        if self.status == "starting":
            return "starting", "warn"
        if self.exit_code:
            return f"exit {self.exit_code}", "err"
        return "stopped", "dim"

    def _pump(self) -> None:
        proc = self.proc
        assert proc is not None and proc.stdout is not None
        for raw in proc.stdout:
            text = clean_line(raw)
            if text:
                self.push(text)
        code = proc.wait()
        self.exit_code = code
        self.status = "exited"
        if self.stopping:
            self.push(f"stopped (exit {code})", "sys")
        elif code == 0:
            self.push("exited (exit 0)", "sys")
        else:
            self.push(f"exited with code {code}", "err")
        DIRTY.set()

    def _probe(self) -> None:
        deadline = time.monotonic() + 180
        while self.status == "starting" and time.monotonic() < deadline:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return
            try:
                request = urllib.request.Request(
                    self.health_url, headers={"User-Agent": "NewsAgreator/start.py"}
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    ok = 200 <= response.status < 400
            except urllib.error.HTTPError as exc:
                ok = 200 <= exc.code < 400
            except Exception:  # noqa: BLE001
                ok = False
            if ok and self.status == "starting" and proc.poll() is None:
                self.status = "ready"
                self.push(f"ready at {self.url}", "ok")
                return
            time.sleep(0.5)


@dataclass
class Step:
    label: str
    detail: str
    cmd: list[str] | None = None
    cwd: Path | None = None
    action: Callable[[], str] | None = None
    state: str = "pending"
    started: float = 0.0
    duration: float = 0.0
    note: str = ""
    output: list[str] = field(default_factory=list)
    proc: subprocess.Popen[str] | None = None
    reader: threading.Thread | None = None
    terminating: bool = False


@dataclass
class Pane:
    service: Service
    window: curses.window | None = None
    scroll: int = 0


def _start_step(step: Step) -> None:
    step.started = time.monotonic()
    if step.action is not None:
        try:
            step.note = step.action()
            step.state = "ok"
        except Exception as exc:  # noqa: BLE001
            step.note = str(exc)
            step.output.append(str(exc))
            step.state = "failed"
        step.duration = time.monotonic() - step.started
        return
    assert step.cmd is not None
    try:
        step.proc = subprocess.Popen(
            step.cmd,
            cwd=str(step.cwd) if step.cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            **_popen_group_kwargs(),
        )
    except OSError as exc:
        step.output.append(f"could not start: {exc}")
        step.state = "failed"
        step.duration = 0.0
        return
    step.state = "running"
    step.reader = threading.Thread(target=_read_step, args=(step,), daemon=True)
    step.reader.start()


def _read_step(step: Step) -> None:
    proc = step.proc
    assert proc is not None and proc.stdout is not None
    for raw in proc.stdout:
        text = clean_line(raw)
        if text:
            step.output.append(text)
    proc.wait()


def _poll_step(step: Step) -> None:
    if step.state != "running" or step.proc is None:
        return
    if step.proc.poll() is None:
        return
    if step.reader is not None:
        step.reader.join(timeout=2)
    step.duration = time.monotonic() - step.started
    step.state = "ok" if step.proc.returncode == 0 else "failed"


def _terminate_step(step: Step) -> None:
    if step.proc is None or step.proc.poll() is not None or step.terminating:
        return
    step.terminating = True
    _terminate_process(step.proc)


def _kill_step(step: Step) -> None:
    if step.proc is None or step.proc.poll() is not None:
        return
    _terminate_process(step.proc, force=True)


def ensure_server_env() -> str:
    env = SERVER_DIR / ".env"
    example = SERVER_DIR / ".env.example"
    if env.exists():
        return ".env present"
    if not example.exists():
        return ".env missing"
    shutil.copyfile(example, env)
    return "created .env from .env.example"


def build_steps(args: argparse.Namespace) -> list[Step]:
    steps = [Step(label="server env", detail=".env", action=ensure_server_env)]
    if args.no_sync:
        steps.append(
            Step(label="server deps", detail="uv sync --extra laya", state="skipped", note="--no-sync")
        )
        steps.append(Step(label="web deps", detail="bun install", state="skipped", note="--no-sync"))
    else:
        steps.append(
            Step(
                label="server deps",
                detail="uv sync --extra laya",
                cmd=_command(UV, "sync", "--extra", "laya"),
                cwd=SERVER_DIR,
            )
        )
        steps.append(
            Step(
                label="web deps",
                detail="bun install",
                cmd=_command(BUN, "install"),
                cwd=WEB_DIR,
            )
        )
    return steps


def _read_cors_origins(web_port: int) -> list[str]:
    raw = os.environ.get("NEWS_CORS_ORIGINS")
    env_path = SERVER_DIR / ".env"
    if raw is None and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("NEWS_CORS_ORIGINS="):
                raw = stripped.split("=", 1)[1].strip().strip("'\"")
                break
    origins: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            origins = [str(item) for item in parsed]
    if not origins:
        origins = ["http://localhost:3000"]
    needed = f"http://localhost:{web_port}"
    if needed not in origins:
        origins.append(needed)
    return origins


def build_services(args: argparse.Namespace) -> list[Service]:
    api_url = f"http://localhost:{args.port}"
    web_url = f"http://localhost:{args.web_port}"

    api_env = os.environ.copy()
    api_env["NEWS_APP_ENV"] = args.app_env
    api_env["NEWS_CORS_ORIGINS"] = json.dumps(_read_cors_origins(args.web_port))
    if args.device:
        api_env["NEWS_LAYA_DEVICE"] = args.device

    web_env = os.environ.copy()
    web_env.pop("NODE_ENV", None)
    web_env["NEXT_PUBLIC_API_BASE_URL"] = api_url

    return [
        Service(
            key="api",
            label="api",
            url=api_url,
            health_url=api_url + "/ready",
            cmd=_command(
                UV,
                "run",
                "uvicorn",
                "main:app",
                "--host",
                args.host,
                "--port",
                str(args.port),
            ),
            cwd=SERVER_DIR,
            env=api_env,
        ),
        Service(
            key="web",
            label="web",
            url=web_url,
            health_url=web_url + "/",
            cmd=_command(
                BUN,
                "run",
                "dev",
                "--",
                "--port",
                str(args.web_port),
            ),
            cwd=WEB_DIR,
            env=web_env,
        ),
    ]


def port_in_use(port: int) -> bool:
    for host, family in (("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def stop_services(services: list[Service]) -> None:
    for service in services:
        proc = service.proc
        if proc is not None and proc.poll() is None:
            service.stopping = True
            _terminate_process(proc)
    deadline = time.monotonic() + 8
    for service in services:
        proc = service.proc
        if proc is None:
            continue
        try:
            proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _terminate_process(proc, force=True)


@atexit.register
def _emergency_cleanup() -> None:
    for service in LIVE:
        _terminate_process(service.proc)


def _attr(name: str, extra: int = 0) -> int:
    try:
        return curses.color_pair(PAIR_IDS.get(name, 0)) | extra
    except curses.error:
        return extra


def _line_attr(level: str) -> int:
    if level == "sys":
        return curses.A_DIM
    if level == "ok":
        return _attr("ok")
    if level == "err":
        return _attr("err")
    return 0


def _put(win, y: int, x: int, text: str, attr: int = 0) -> None:
    try:
        height, width = win.getmaxyx()
    except curses.error:
        return
    if not text or y < 0 or y >= height or x < 0 or x >= width:
        return
    try:
        win.addnstr(y, x, text, max(0, width - x), attr)
    except (curses.error, UnicodeEncodeError):
        pass


def _init_curses(stdscr) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    stdscr.nodelay(True)
    if not curses.has_colors():
        return
    try:
        curses.start_color()
        curses.use_default_colors()
    except curses.error:
        pass
    for name, color in (
        ("api", curses.COLOR_CYAN),
        ("web", curses.COLOR_MAGENTA),
        ("ok", curses.COLOR_GREEN),
        ("warn", curses.COLOR_YELLOW),
        ("err", curses.COLOR_RED),
        ("accent", curses.COLOR_CYAN),
    ):
        try:
            curses.init_pair(PAIR_IDS[name], color, -1)
        except curses.error:
            pass


def _draw_preflight(stdscr, steps: list[Step], started: float) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    _put(stdscr, 1, 2, "NewsAgreator", curses.A_BOLD | _attr("accent"))
    _put(stdscr, 1, 15, "environment", curses.A_DIM)
    _put(stdscr, 2, 2, "─" * max(0, min(width - 4, 76)), curses.A_DIM)

    frame = SPINNER[int((time.monotonic() - started) * 12) % len(SPINNER)]
    column = 24
    row = 4
    for step in steps:
        if row > height - 3:
            break
        if step.state == "running":
            glyph, level = frame, "warn"
        else:
            glyph, level = STATE_GLYPHS.get(step.state, ("·", "dim"))
        _put(stdscr, row, 2, glyph, _attr(level))
        _put(stdscr, row, 4, step.label, curses.A_BOLD if step.state == "running" else 0)

        if step.state == "running":
            status = f"{time.monotonic() - step.started:.1f}s"
        elif step.state == "failed":
            status = "failed"
        elif step.state == "skipped":
            status = "skipped"
        elif step.state == "ok" and step.duration >= 0.05:
            status = f"{step.duration:.1f}s"
        else:
            status = ""

        info = step.note if step.state in ("ok", "failed", "skipped") and step.note else step.detail
        info_width = max(0, width - column - len(status) - 4)
        _put(stdscr, row, column, info[:info_width], curses.A_DIM)
        if status:
            _put(stdscr, row, max(column, width - len(status) - 2), status, _attr(level))

        if step.state == "running" and step.output:
            tail = step.output[-1]
            row += 1
            _put(stdscr, row, column, tail[: max(0, width - column - 2)], curses.A_DIM)
        row += 2

    if height >= 3:
        _put(stdscr, height - 2, 2, "Ctrl+C to cancel", curses.A_DIM)
    stdscr.noutrefresh()
    curses.doupdate()


def _preflight_tui(stdscr, steps: list[Step]) -> bool:
    for step in steps:
        if step.state == "pending" and step.action is not None:
            _start_step(step)
    for step in steps:
        if step.state == "pending":
            _start_step(step)

    started = time.monotonic()
    failed = False
    terminate_at = 0.0
    while True:
        for step in steps:
            _poll_step(step)
        running = [step for step in steps if step.state == "running"]
        if not failed and any(step.state == "failed" for step in steps):
            failed = True
            terminate_at = time.monotonic() + 3.0
            for step in running:
                _terminate_step(step)
        elif failed and running and time.monotonic() >= terminate_at:
            for step in running:
                _kill_step(step)
        _draw_preflight(stdscr, steps, started)
        if not running:
            break
        time.sleep(0.08)
    _draw_preflight(stdscr, steps, started)
    time.sleep(0.2)
    return all(step.state in ("ok", "skipped") for step in steps)


def _preflight_plain(steps: list[Step]) -> bool:
    for step in steps:
        if step.state == "pending":
            print(f"→ {step.label}: {step.detail}", flush=True)
            _start_step(step)
        while step.state == "running":
            _poll_step(step)
            time.sleep(0.05)
        if step.state == "skipped":
            print(f"– {step.label}: skipped")
        elif step.state == "ok":
            note = f"  {step.note}" if step.note else ""
            print(f"✓ {step.label}{note}  {step.duration:.1f}s")
        else:
            print(f"✗ {step.label} failed")
            for line in step.output[-40:]:
                print(f"  {line}")
            return False
    return True


def _report_preflight_failure(steps: list[Step]) -> None:
    failed = [step for step in steps if step.state == "failed"]
    if not failed:
        print("\nenvironment sync did not finish", file=sys.stderr)
        return
    print("\nenvironment sync failed:", file=sys.stderr)
    for step in failed:
        print(f"  ✗ {step.label}: {step.detail}", file=sys.stderr)
        for line in step.output[-40:]:
            print(f"    {line}", file=sys.stderr)


def _layout_panes(panes: list[Pane], stdscr, size: tuple[int, int]) -> None:
    for pane in panes:
        if pane.window is not None:
            try:
                curses.delwin(pane.window)
            except curses.error:
                pass
            pane.window = None
    height, width = size
    header = 1 if height >= 8 else 0
    body = height - header - 1
    if body < 3 or width < 8:
        return
    if width >= 104 or body < 8:
        half = max(4, width // 2)
        geometry = [(header, 0, body, half), (header, half, body, width - half)]
    else:
        top = body // 2
        geometry = [(header, 0, top, width), (header + top, 0, body - top, width)]
    for pane, (y, x, pane_height, pane_width) in zip(panes, geometry):
        if pane_height < 3 or pane_width < 4:
            continue
        pane.window = curses.newwin(pane_height, pane_width, y, x)
        pane.window.keypad(True)


def _draw_pane(pane: Pane, focused: bool) -> None:
    win = pane.window
    if win is None:
        return
    service = pane.service
    height, width = win.getmaxyx()
    win.erase()
    if height >= 2 and width >= 2:
        try:
            win.box()
        except curses.error:
            pass

    status, level = service.status_label()
    status_text = f" {status} "
    status_x = max(2, width - len(status_text) - 2)
    title = f" {service.label} · {service.url} "
    base_attr = _attr(service.key) | (curses.A_BOLD if focused else 0)
    _put(win, 0, 2, title[: max(0, status_x - 3)], base_attr)
    _put(win, 0, status_x, status_text, _attr(level) | (curses.A_BOLD if focused else 0))

    inner_height = height - 2
    inner_width = width - 2
    if inner_height <= 0 or inner_width <= 0:
        return

    wrapped: list[tuple[str, str]] = []
    for text, line_level in service.snapshot():
        if not text:
            wrapped.append(("", line_level))
            continue
        for start in range(0, len(text), inner_width):
            wrapped.append((text[start : start + inner_width], line_level))

    total = len(wrapped)
    pane.scroll = min(pane.scroll, max(0, total - inner_height))
    first = max(0, total - inner_height - pane.scroll)
    for row in range(inner_height):
        index = first + row
        if index >= total:
            break
        text, line_level = wrapped[index]
        if text:
            _put(win, 1 + row, 1, text, _line_attr(line_level))


def _draw_services(stdscr, panes: list[Pane], focus: int, meta: str) -> None:
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    if height >= 8:
        _put(stdscr, 0, 2, "NewsAgreator", curses.A_BOLD | _attr("accent"))
        _put(stdscr, 0, 15, "· dev stack", curses.A_DIM)
        if meta and width > len(meta) + 20:
            _put(stdscr, 0, width - len(meta) - 2, meta, curses.A_DIM)

    for index, pane in enumerate(panes):
        _draw_pane(pane, index == focus)

    if height >= 2:
        hints = f"q quit   tab focus: {panes[focus].service.label}   ↑↓ scroll   end tail"
        crashed = [
            pane.service
            for pane in panes
            if pane.service.status in ("exited", "failed")
            and pane.service.exit_code not in (None, 0)
        ]
        right = (
            f"{crashed[0].label} exited {crashed[0].exit_code} — q to quit"
            if crashed
            else "Ctrl+C stops both"
        )
        _put(stdscr, height - 1, 2, hints, curses.A_DIM)
        right_x = width - len(right) - 2
        if right_x > len(hints) + 4:
            _put(stdscr, height - 1, right_x, right, _attr("err") if crashed else curses.A_DIM)

    stdscr.noutrefresh()
    for pane in panes:
        if pane.window is not None:
            pane.window.noutrefresh()
    curses.doupdate()


def _service_tui(stdscr, services: list[Service], meta: str) -> None:
    panes = [Pane(service) for service in services]
    focus = 0
    last_size = None
    stdscr.timeout(100)
    DIRTY.set()

    while True:
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 3):
            return
        if key == 9:
            focus = (focus + 1) % len(panes)
            DIRTY.set()
        elif key == curses.KEY_UP:
            panes[focus].scroll += 1
        elif key == curses.KEY_DOWN:
            panes[focus].scroll = max(0, panes[focus].scroll - 1)
        elif key == curses.KEY_PPAGE:
            panes[focus].scroll += 15
        elif key == curses.KEY_NPAGE:
            panes[focus].scroll = max(0, panes[focus].scroll - 15)
        elif key == curses.KEY_END:
            panes[focus].scroll = 0
        elif key == -1:
            pass
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE, curses.KEY_END):
            DIRTY.set()

        size = stdscr.getmaxyx()
        if size != last_size:
            _layout_panes(panes, stdscr, size)
            last_size = size
            DIRTY.set()

        if DIRTY.is_set():
            DIRTY.clear()
            _draw_services(stdscr, panes, focus, meta)


def _run_tui(steps: list[Step], start_stack, meta: str) -> bool:
    def loop(stdscr) -> bool:
        _init_curses(stdscr)
        if not _preflight_tui(stdscr, steps):
            return False
        services = start_stack()
        _service_tui(stdscr, services, meta)
        return True

    return curses.wrapper(loop)


def _run_plain(services: list[Service]) -> None:
    color = sys.stdout.isatty()
    reset = "\x1b[0m" if color else ""
    tag_colors = {"api": "\x1b[36m", "web": "\x1b[35m"} if color else {}
    level_colors = {"ok": "\x1b[32m", "err": "\x1b[31m", "sys": "\x1b[2m"} if color else {}
    dim = level_colors.get("sys", "")

    print("NewsAgreator dev stack")
    for service in services:
        print(f"  {service.label:<3} {service.url}")
    print(f"{dim}  Ctrl+C stops both{reset}\n", flush=True)

    seen = {service.key: 0 for service in services}
    while True:
        alive = False
        for service in services:
            lines = service.snapshot()
            if seen[service.key] > len(lines):
                seen[service.key] = 0
            for text, level in lines[seen[service.key] :]:
                if not text:
                    continue
                tag = f"{tag_colors.get(service.key, '')}{service.label:<3}{reset}"
                tint = level_colors.get(level, "")
                body = f"{tint}{text}{reset}" if tint else text
                print(f"{tag} │ {body}", flush=True)
            seen[service.key] = len(lines)
            if service.proc is not None and service.proc.poll() is None:
                alive = True
        if not alive:
            break
        time.sleep(0.15)


def _crashed(services: list[Service]) -> bool:
    return any(
        service.status == "failed"
        or (service.exit_code not in (None, 0) and not service.stopping)
        for service in services
    )


def _print_summary(services: list[Service]) -> None:
    for service in services:
        status, _ = service.status_label()
        print(f"  {service.label:<3} {service.url:<28} {status}")


def _install_signal_handlers() -> None:
    def handler(signum, frame) -> None:
        raise KeyboardInterrupt

    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (OSError, ValueError):
            pass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync the environments and run the NewsAgreator API + web dev servers."
    )
    parser.add_argument("--host", default="127.0.0.1", help="API bind host (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_API_PORT, help=f"API port (default: {DEFAULT_API_PORT})"
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=DEFAULT_WEB_PORT,
        help=f"web port (default: {DEFAULT_WEB_PORT})",
    )
    parser.add_argument("--device", choices=("cuda", "cpu"), help="Laya device; defaults to .env")
    parser.add_argument(
        "--app-env",
        choices=("dev", "demo", "prod"),
        default="dev",
        help="server app environment (default: dev)",
    )
    parser.add_argument("--no-sync", action="store_true", help="skip uv sync and bun install")
    parser.add_argument("--plain", action="store_true", help="stream plain prefixed logs")
    parser.add_argument(
        "--tui",
        action="store_true",
        help="force the curses UI when available (Windows needs windows-curses)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global UV, BUN, META

    args = _parse_args(argv)
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    _install_signal_handlers()

    UV = shutil.which("uv") or ""
    BUN = shutil.which("bun") or ""
    if not (SERVER_DIR / "main.py").exists():
        print(f"start: server not found at {SERVER_DIR}", file=sys.stderr)
        return 1
    if not (WEB_DIR / "package.json").exists():
        print(f"start: web app not found at {WEB_DIR}", file=sys.stderr)
        return 1
    if not UV:
        print(
            "start: uv is not installed or not on PATH.\n"
            "  Install: https://docs.astral.sh/uv/getting-started/installation/",
            file=sys.stderr,
        )
        return 1
    if not BUN:
        print(
            "start: bun is not installed or not on PATH.\n"
            "  Install: https://bun.sh/docs/installation",
            file=sys.stderr,
        )
        return 1
    if not _check_tool("uv", UV):
        return 1
    if not _check_tool("bun", BUN):
        return 1
    if port_in_use(args.port):
        print(f"start: port {args.port} is already in use (try --port)", file=sys.stderr)
        return 1
    if port_in_use(args.web_port):
        print(f"start: port {args.web_port} is already in use (try --web-port)", file=sys.stderr)
        return 1

    META = (
        f"{args.app_env} · {platform.system().lower()} · "
        f"laya {args.device or 'from .env'}"
    )
    steps = build_steps(args)

    if args.tui and not CURSES_AVAILABLE:
        print(
            "start: --tui requested but curses is unavailable; using plain logs",
            file=sys.stderr,
        )
    term_ok = IS_WINDOWS or os.environ.get("TERM", "") not in ("", "dumb")
    use_tui = (
        not args.plain
        and CURSES_AVAILABLE
        and (args.tui or not IS_WINDOWS)
        and term_ok
        and sys.stdout.isatty()
        and sys.stdin.isatty()
    )

    services: list[Service] = []
    interrupted = False

    def start_stack() -> list[Service]:
        services.extend(build_services(args))
        for service in services:
            service.start()
        LIVE.extend(services)
        return services

    try:
        if use_tui:
            try:
                ok = _run_tui(steps, start_stack, META)
            except curses.error as exc:
                print(f"start: terminal UI unavailable ({exc}); using plain logs", file=sys.stderr)
                ok = _preflight_plain(steps)
                if ok and not services:
                    start_stack()
                if ok:
                    _run_plain(services)
        else:
            ok = _preflight_plain(steps)
            if ok:
                start_stack()
                _run_plain(services)

        if not ok and not services:
            _report_preflight_failure(steps)
            return 1
    except KeyboardInterrupt:
        interrupted = True
        for step in steps:
            _terminate_step(step)
    finally:
        stop_services(services)

    if not services:
        print("\ncancelled" if interrupted else "\nno services started")
        return 130 if interrupted else 1

    print()
    print("stopped")
    _print_summary(services)
    if interrupted:
        return 130
    return 1 if _crashed(services) else 0


if __name__ == "__main__":
    raise SystemExit(main())
