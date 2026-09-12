# -*- coding: utf-8 -*-
"""Phone Link OTP Autofill for Windows.

Flow:
    iPhone -> Bluetooth -> Microsoft Phone Link -> UI Automation -> OTP parser
    -> foreground-browser guard -> type into the current keyboard focus.

Designed for Windows 10/11. No LAN connectivity between iPhone and PC is required.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Optional

import pystray
from PIL import Image, ImageDraw
import uiautomation as auto

APP_NAME = "PhoneLinkOtpAutofill"
APP_DISPLAY_NAME = "Phone Link 验证码自动填写"
VERSION = "1.0.3"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = APP_NAME
ERROR_ALREADY_EXISTS = 183

DEFAULT_CONFIG = {
    "autofill_enabled": True,
    "browser_only": True,
    "strict_input_focus": False,
    "smart_focus_guard": True,
    "poll_interval": 0.35,
    "pending_seconds": 15.0,
    "otp_cooldown_seconds": 120.0,
    "detected_code_cooldown_seconds": 300.0,
    "baseline_settle_seconds": 5.0,
    "notify_on_fill": True,
    "show_code_in_notification": False,
    "ignore_existing_on_start": True,
    "browser_processes": [
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "arc.exe",
        "vivaldi.exe",
        "opera.exe",
        "opera_gx.exe",
        "360chrome.exe",
        "360se.exe",
        "qqbrowser.exe",
    ],
}

PHONE_LINK_TITLE_HINTS = ("手机连接", "Phone Link")
PHONE_LINK_PROCESSES = {"phoneexperiencehost.exe"}
LEGACY_PHONE_LINK_HOST_PROCESSES = {"applicationframehost.exe"}
PHONE_LINK_IGNORED_TITLE_PREFIXES = ("splashscreen",)
BROWSER_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}
BLOCKED_FOCUS_TYPES = {
    "ButtonControl",
    "HyperlinkControl",
    "MenuItemControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "TabItemControl",
    "TreeItemControl",
    "ListItemControl",
}

OTP_PATTERNS = [
    re.compile(
        r"(?:验证码|校验码|动态码|认证码|短信码|安全码|"
        r"verification\s*code|security\s*code|one[-\s]*time\s*(?:code|password)|OTP)"
        r"[^\d]{0,20}(\d{4,8})(?!\d)",
        re.I,
    ),
    re.compile(
        r"(?<!\d)(\d{4,8})(?!\d)"
        r"[^\d]{0,20}(?:是|为|is)?[^\d]{0,8}"
        r"(?:您的|你的|your)?[^\d]{0,5}"
        r"(?:验证码|校验码|动态码|认证码|verification\s*code|security\s*code|OTP)",
        re.I,
    ),
]
OTP_KEYWORD = re.compile(
    r"验证码|校验码|动态码|认证码|短信码|安全码|"
    r"verification\s*code|security\s*code|one[-\s]*time|OTP",
    re.I,
)
SENDER_PATTERN = re.compile(r"^\s*【([^】]{1,30})】")


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME}"


DATA_DIR = app_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "otp_autofill.log"


def setup_logging() -> logging.Logger:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


LOGGER = setup_logging()


def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            LOGGER.exception("读取配置失败，使用默认配置")
    save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def mask_code(code: str) -> str:
    if len(code) <= 2:
        return "*" * len(code)
    return code[:2] + "*" * (len(code) - 2)


def extract_sender(text: str) -> str:
    m = SENDER_PATTERN.search(text or "")
    return m.group(1).strip() if m else "短信验证码"


def extract_otp(text: str) -> Optional[str]:
    if not text or not OTP_KEYWORD.search(text):
        return None
    normalized = " ".join(text.split())
    for pattern in OTP_PATTERNS:
        m = pattern.search(normalized)
        if m:
            code = m.group(1)
            if 4 <= len(code) <= 8:
                return code
    return None


# ---------------- Win32 declarations ----------------
if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    ULONG_PTR = ctypes.c_size_t
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ULONG_PTR]
    user32.keybd_event.restype = None

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
else:
    user32 = None
    kernel32 = None
    WNDENUMPROC = None


KEYEVENTF_KEYUP = 0x0002


def ensure_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("本程序仅支持 Windows 10/11。")


def acquire_single_instance_mutex():
    ensure_windows()
    handle = kernel32.CreateMutexW(None, False, f"Local\\{APP_NAME}_Singleton")
    if not handle:
        return None, False
    already_exists = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, not already_exists


def get_window_title(hwnd) -> str:
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def get_window_class(hwnd) -> str:
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    n = user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value if n else ""


def get_process_name_from_hwnd(hwnd) -> str:
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h_process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size))
        if not ok:
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h_process)


def foreground_app_info() -> dict:
    hwnd = user32.GetForegroundWindow()
    return {
        "hwnd": int(hwnd) if hwnd else 0,
        "title": get_window_title(hwnd),
        "class": get_window_class(hwnd),
        "process": get_process_name_from_hwnd(hwnd),
    }


def enum_visible_windows() -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        try:
            if user32.IsWindowVisible(hwnd):
                title = get_window_title(hwnd).strip()
                if title:
                    items.append((int(hwnd), title))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    return items


def select_phone_link_window(
    windows: list[tuple[int, str, str]],
) -> tuple[Optional[int], Optional[str]]:
    for hwnd, title, process in windows:
        normalized_title = title.strip().casefold()
        is_transient = any(
            normalized_title.startswith(prefix)
            for prefix in PHONE_LINK_IGNORED_TITLE_PREFIXES
        )
        if process.lower() in PHONE_LINK_PROCESSES and not is_transient:
            return hwnd, title

    exact_titles = {hint.casefold() for hint in PHONE_LINK_TITLE_HINTS}
    exact_titles.add("iphone")
    for hwnd, title, process in windows:
        if (
            process.lower() in LEGACY_PHONE_LINK_HOST_PROCESSES
            and title.strip().casefold() in exact_titles
        ):
            return hwnd, title

    return None, None


def find_phone_link_hwnd() -> tuple[Optional[int], Optional[str]]:
    windows = [
        (hwnd, title, get_process_name_from_hwnd(hwnd))
        for hwnd, title in enum_visible_windows()
    ]
    return select_phone_link_window(windows)


def type_digits(code: str) -> None:
    for ch in code:
        if not ch.isdigit():
            continue
        vk = ord(ch)
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.022)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.014)


# ---------------- Phone Link UI Automation ----------------
def control_from_hwnd(hwnd):
    try:
        fn = getattr(auto, "ControlFromHandle", None)
        if fn:
            c = fn(hwnd)
            if c:
                return c
    except Exception:
        pass
    try:
        return auto.WindowControl(Handle=hwnd)
    except Exception:
        return None


def collect_texts(control, max_depth: int = 16) -> list[str]:
    result: list[str] = []
    stack = [(control, 0)]
    visited = 0
    max_nodes = 2500
    while stack and visited < max_nodes:
        node, depth = stack.pop()
        visited += 1
        try:
            name = (node.Name or "").strip()
            if name:
                result.append(name)
        except Exception:
            pass
        if depth >= max_depth:
            continue
        try:
            children = node.GetChildren()
        except Exception:
            children = []
        if children:
            for child in reversed(children):
                stack.append((child, depth + 1))
    return result


def focused_control_state(strict: bool, smart_guard: bool) -> tuple[bool, str]:
    """Return (safe_to_type, description).

    Strict mode accepts only UIA EditControl. Smart mode (default) allows unknown
    or document-level focus, but blocks obvious buttons/links/menu controls so a
    fast-arriving OTP is less likely to be typed into "Get code" itself.
    """
    try:
        c = auto.GetFocusedControl()
        if not c:
            return (not strict), "无法取得焦点控件"
        name = getattr(c, "Name", "") or ""
        ctype = getattr(c, "ControlTypeName", "") or ""
        desc = f"{ctype or 'Unknown'}: {name}".strip()
        if strict:
            return ctype == "EditControl", desc
        if smart_guard and ctype in BLOCKED_FOCUS_TYPES:
            return False, desc
        return True, desc
    except Exception as exc:
        return (not strict), f"焦点检测失败: {exc}"


# ---------------- Startup / shell helpers ----------------
def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --startup'
    script = Path(__file__).resolve()
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{script}" --startup'


def is_startup_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


def open_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix and not path.exists():
        path.touch()
    os.startfile(str(path))  # type: ignore[attr-defined]


def open_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(str(DATA_DIR))  # type: ignore[attr-defined]


def try_open_phone_link() -> None:
    # The classic AUMID is still supported on most Windows 10/11 installations.
    try:
        subprocess.Popen(
            ["explorer.exe", r"shell:AppsFolder\Microsoft.YourPhone_8wekyb3d8bbwe!App"],
            close_fds=True,
        )
    except Exception:
        LOGGER.exception("尝试打开 Phone Link 失败")


def make_tray_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    # Simple phone + OTP dots icon. Kept programmatic so source runs standalone.
    d.rounded_rectangle((13, 5, 51, 59), radius=8, fill=(45, 110, 220, 255))
    d.rounded_rectangle((18, 11, 46, 49), radius=4, fill=(245, 248, 255, 255))
    for x in (24, 32, 40):
        d.ellipse((x - 2, 28, x + 2, 32), fill=(45, 110, 220, 255))
    d.ellipse((30, 53, 34, 57), fill=(245, 248, 255, 255))
    return image


class OtpAutofillApp:
    def __init__(self, config: dict):
        self.config = config
        self.stop_event = threading.Event()
        self.config_lock = threading.Lock()
        self.paused_until = 0.0
        self.phone = None
        self.phone_hwnd: Optional[int] = None
        self.seen_texts: set[str] = set()
        self.observed_codes: dict[str, float] = {}
        self.filled_codes: dict[str, float] = {}
        self.pending: Optional[tuple[str, float, str]] = None
        self.baseline_settle_until = 0.0
        self.status = "正在启动"
        self.icon = pystray.Icon(
            APP_NAME,
            make_tray_image(),
            APP_DISPLAY_NAME,
            menu=self._make_menu(),
        )

    def _make_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                "自动填写",
                self.toggle_autofill,
                checked=lambda _item: bool(self.config.get("autofill_enabled", True)),
            ),
            pystray.MenuItem(
                "仅允许浏览器",
                self.toggle_browser_only,
                checked=lambda _item: bool(self.config.get("browser_only", True)),
            ),
            pystray.MenuItem(
                "严格输入框检测",
                self.toggle_strict_focus,
                checked=lambda _item: bool(self.config.get("strict_input_focus", False)),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("暂停 10 分钟", self.pause_10m),
            pystray.MenuItem("立即恢复", self.resume),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "开机自动启动",
                self.toggle_startup,
                checked=lambda _item: is_startup_enabled(),
            ),
            pystray.MenuItem("打开手机连接", self.open_phone_link),
            pystray.MenuItem("打开日志", self.open_log),
            pystray.MenuItem("打开配置目录", self.open_config_dir),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.quit),
        )

    def _persist(self):
        with self.config_lock:
            save_config(self.config)
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def toggle_autofill(self, _icon=None, _item=None):
        self.config["autofill_enabled"] = not bool(self.config.get("autofill_enabled", True))
        self._persist()
        LOGGER.info("自动填写=%s", self.config["autofill_enabled"])

    def toggle_browser_only(self, _icon=None, _item=None):
        self.config["browser_only"] = not bool(self.config.get("browser_only", True))
        self._persist()
        LOGGER.info("仅浏览器=%s", self.config["browser_only"])

    def toggle_strict_focus(self, _icon=None, _item=None):
        self.config["strict_input_focus"] = not bool(self.config.get("strict_input_focus", False))
        self._persist()
        LOGGER.info("严格输入框检测=%s", self.config["strict_input_focus"])

    def pause_10m(self, _icon=None, _item=None):
        self.paused_until = time.time() + 600
        self._set_status("已暂停 10 分钟")
        LOGGER.info("用户暂停 10 分钟")

    def resume(self, _icon=None, _item=None):
        self.paused_until = 0.0
        self._set_status("已恢复")
        LOGGER.info("用户立即恢复")

    def toggle_startup(self, _icon=None, _item=None):
        try:
            set_startup_enabled(not is_startup_enabled())
            self.icon.update_menu()
        except Exception:
            LOGGER.exception("修改开机启动失败")
            self._notify("修改开机启动失败，请查看日志", "验证码自动填写")

    def open_phone_link(self, _icon=None, _item=None):
        try_open_phone_link()

    def open_log(self, _icon=None, _item=None):
        try:
            open_path(LOG_PATH)
        except Exception:
            LOGGER.exception("打开日志失败")

    def open_config_dir(self, _icon=None, _item=None):
        try:
            open_data_dir()
        except Exception:
            LOGGER.exception("打开配置目录失败")

    def quit(self, _icon=None, _item=None):
        LOGGER.info("程序退出")
        self.stop_event.set()
        try:
            self.icon.stop()
        except Exception:
            pass

    def _notify(self, message: str, title: str = APP_DISPLAY_NAME):
        try:
            self.icon.notify(message, title)
        except Exception:
            LOGGER.debug("托盘通知失败", exc_info=True)

    def _set_status(self, status: str):
        if status == self.status:
            return
        self.status = status
        try:
            self.icon.title = f"{APP_DISPLAY_NAME} · {status}"
        except Exception:
            pass

    def _is_browser(self, info: dict) -> bool:
        if not bool(self.config.get("browser_only", True)):
            return True
        process = (info.get("process") or "").lower()
        klass = info.get("class") or ""
        allowed = {str(x).lower() for x in self.config.get("browser_processes", [])}
        if process in allowed:
            return True
        if klass in BROWSER_CLASSES or klass.startswith("Chrome_WidgetWin_"):
            return True
        return False

    def _bind_phone_link(self) -> bool:
        hwnd, title = find_phone_link_hwnd()
        if not hwnd:
            self.phone = None
            self.phone_hwnd = None
            self._set_status("等待手机连接")
            return False
        control = control_from_hwnd(hwnd)
        if control is None:
            self.phone = None
            self.phone_hwnd = None
            self._set_status("连接手机连接失败")
            return False
        self.phone = control
        self.phone_hwnd = hwnd
        self._set_status("已连接手机连接")
        LOGGER.info(
            "已连接 Phone Link: %s / process=%s / HWND=0x%X",
            title,
            get_process_name_from_hwnd(hwnd),
            hwnd,
        )
        return True

    def _establish_baseline(self):
        if not self.phone:
            return
        texts = collect_texts(self.phone)
        if bool(self.config.get("ignore_existing_on_start", True)):
            self.seen_texts = set()
            self._absorb_baseline(texts)
            settle_seconds = max(
                0.0,
                float(self.config.get("baseline_settle_seconds", 5.0)),
            )
            self.baseline_settle_until = time.monotonic() + settle_seconds
        else:
            self.seen_texts = set()
            self.baseline_settle_until = 0.0
        LOGGER.info("初始 UI 文本基线=%d 段", len(self.seen_texts))

    def _absorb_baseline(self, texts: list[str]) -> None:
        observed_at = time.monotonic()
        for text in texts:
            self.seen_texts.add(text)
            code = extract_otp(text)
            if code:
                self.observed_codes[code] = observed_at

    def _process_text_snapshot(self, current_texts: list[str]) -> None:
        if time.monotonic() < self.baseline_settle_until:
            self._absorb_baseline(current_texts)
            return

        for text in current_texts:
            if text in self.seen_texts:
                continue
            self.seen_texts.add(text)
            self._handle_new_text(text)

    def _disconnect_phone_link(self) -> None:
        self.phone = None
        self.phone_hwnd = None
        self.pending = None
        self.baseline_settle_until = 0.0

    def _recently_observed(self, code: str) -> tuple[bool, float]:
        cooldown = max(
            0.0,
            float(self.config.get("detected_code_cooldown_seconds", 300.0)),
        )
        now = time.monotonic()
        last = self.observed_codes.get(code)
        if last is None:
            return False, 0.0

        elapsed = now - last
        if cooldown == 0.0 or elapsed >= cooldown:
            self.observed_codes.pop(code, None)
            return False, elapsed

        return True, elapsed

    def _recently_filled(self, code: str) -> tuple[bool, float]:
        cooldown = max(
            0.0,
            float(self.config.get("otp_cooldown_seconds", 120.0)),
        )
        now = time.monotonic()
        last = self.filled_codes.get(code)
        if last is None:
            return False, 0.0

        elapsed = now - last
        if cooldown == 0.0 or elapsed >= cooldown:
            self.filled_codes.pop(code, None)
            return False, elapsed

        return True, elapsed

    def _handle_new_text(self, text: str):
        code = extract_otp(text)
        if not code:
            return
        duplicate, elapsed = self._recently_filled(code)
        if duplicate:
            LOGGER.info(
                "忽略重复验证码 %s / 距上次填写 %.1f 秒",
                mask_code(code),
                elapsed,
            )
            return
        duplicate, elapsed = self._recently_observed(code)
        if duplicate:
            LOGGER.info(
                "忽略已检测验证码 %s / 距首次检测 %.1f 秒",
                mask_code(code),
                elapsed,
            )
            return
        self.observed_codes[code] = time.monotonic()
        sender = extract_sender(text)
        deadline = time.time() + float(self.config.get("pending_seconds", 15.0))
        self.pending = (code, deadline, text)
        LOGGER.info("检测到验证码 %s / 来源=%s", mask_code(code), sender)
        self._set_status(f"检测到 {sender} 验证码")

    def _try_fill_pending(self):
        if not self.pending:
            return
        code, deadline, source = self.pending
        if time.time() > deadline:
            LOGGER.info("验证码 %s 等待输入焦点超时", mask_code(code))
            self.pending = None
            self._set_status("等待验证码")
            return

        if time.time() < self.paused_until:
            return
        if not bool(self.config.get("autofill_enabled", True)):
            return

        info = foreground_app_info()
        if not self._is_browser(info):
            return

        safe, focus_desc = focused_control_state(
            strict=bool(self.config.get("strict_input_focus", False)),
            smart_guard=bool(self.config.get("smart_focus_guard", True)),
        )
        if not safe:
            return

        # Re-check the foreground after a short stabilization delay.
        time.sleep(0.10)
        info2 = foreground_app_info()
        if not self._is_browser(info2):
            return

        duplicate, elapsed = self._recently_filled(code)
        if duplicate:
            LOGGER.info(
                "忽略重复验证码 %s / 距上次填写 %.1f 秒",
                mask_code(code),
                elapsed,
            )
            self.pending = None
            self._set_status("等待验证码")
            return

        type_digits(code)
        self._record_successful_fill(code)
        sender = extract_sender(source)
        LOGGER.info(
            "已填写验证码 %s / browser=%s / focus=%s",
            mask_code(code),
            info2.get("process") or "unknown",
            focus_desc,
        )
        self.pending = None
        self._set_status("验证码已填写")

        if bool(self.config.get("notify_on_fill", True)):
            if bool(self.config.get("show_code_in_notification", False)):
                msg = f"{sender} · {code} 已自动填写"
            else:
                msg = f"{sender}验证码已自动填写"
            self._notify(msg)

    def _record_successful_fill(
        self,
        code: str,
        filled_at: Optional[float] = None,
    ) -> None:
        self.observed_codes.pop(code, None)
        self.filled_codes[code] = (
            time.monotonic() if filled_at is None else filled_at
        )

    def _worker_loop_inner(self):
        LOGGER.info("后台监听线程启动，版本=%s", VERSION)
        last_bind_attempt = 0.0
        last_hwnd_check = 0.0
        baseline_done = False

        while not self.stop_event.is_set():
            try:
                now = time.time()

                if self.phone is None:
                    if now - last_bind_attempt >= 2.0:
                        last_bind_attempt = now
                        if self._bind_phone_link():
                            self._establish_baseline()
                            baseline_done = True
                    time.sleep(0.25)
                    continue

                if now - last_hwnd_check >= 3.0:
                    last_hwnd_check = now
                    if not self.phone_hwnd or not user32.IsWindow(self.phone_hwnd):
                        LOGGER.info("Phone Link 窗口已失效，准备重新连接")
                        self._disconnect_phone_link()
                        baseline_done = False
                        continue

                if not baseline_done:
                    self._establish_baseline()
                    baseline_done = True

                current_texts = collect_texts(self.phone)
                self._process_text_snapshot(current_texts)

                if len(self.seen_texts) > 5000:
                    self.seen_texts = set(current_texts)

                self._try_fill_pending()
                if not self.pending and time.time() >= self.paused_until:
                    self._set_status("等待验证码")

                time.sleep(max(0.15, float(self.config.get("poll_interval", 0.35))))
            except Exception:
                LOGGER.exception("后台循环异常")
                self._set_status("发生错误，自动重试")
                time.sleep(1.0)

    def run(self):
        # On Windows pystray explicitly allows Icon.run() from a secondary thread.
        # Keeping UI Automation on the main thread avoids COM/UIA initialization
        # surprises and preserves the behavior of the already-proven v3 script.
        tray_thread = threading.Thread(target=self.icon.run, name="TrayIcon", daemon=True)
        tray_thread.start()
        self._set_status("等待手机连接")
        try:
            self._worker_loop_inner()
        finally:
            self.stop_event.set()
            try:
                self.icon.stop()
            except Exception:
                pass
            tray_thread.join(timeout=2.0)


def parse_args():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--startup", action="store_true", help="由开机启动项启动")
    parser.add_argument("--version", action="store_true", help="显示版本号")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main():
    ensure_windows()
    _args = parse_args()
    if _args.version:
        if sys.stdout is not None:
            print(VERSION)
        else:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"{APP_DISPLAY_NAME} v{VERSION}",
                APP_DISPLAY_NAME,
                0x00000040,
            )
        return 0
    if _args.smoke_test:
        return 0
    mutex, is_first = acquire_single_instance_mutex()
    if not is_first:
        return 0
    LOGGER.info("%s v%s 启动", APP_DISPLAY_NAME, VERSION)
    config = load_config()
    app = OtpAutofillApp(config)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        LOGGER.exception("主程序异常退出")
        raise
    finally:
        if mutex:
            kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
