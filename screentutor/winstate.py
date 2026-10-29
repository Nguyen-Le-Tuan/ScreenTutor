"""Windows sensors over ctypes (no extra packages). Import only on Windows.

S1 window list (top to bottom), S2 foreground window, S3 app of a window,
S4 default apps, S6 known folders. S5 (recent files) is plain Python in state.py.
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from pathlib import Path

from .state import APP_NAMES, WindowInfo, app_name

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
shell32 = ctypes.WinDLL("shell32")
shlwapi = ctypes.WinDLL("shlwapi")
ole32 = ctypes.WinDLL("ole32")

HRESULT = ctypes.c_long
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
dwmapi.DwmGetWindowAttribute.restype = HRESULT
shlwapi.AssocQueryStringW.argtypes = [ctypes.c_uint, ctypes.c_int, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
shlwapi.AssocQueryStringW.restype = HRESULT
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = HRESULT


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]


shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                         ctypes.POINTER(ctypes.c_wchar_p)]
shell32.SHGetKnownFolderPath.restype = HRESULT

GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
COINIT_APARTMENTTHREADED = 0x2
ASSOCF_NONE = 0x0
ASSOCF_INIT_IGNOREUNKNOWN = 0x400   # do not fall back to the "Open with" handler
ASSOCF_IS_PROTOCOL = 0x1000
ASSOCSTR_EXECUTABLE = 2
ASSOCSTR_FRIENDLYAPPNAME = 4
HR_NO_ASSOCIATION = 0x80070483

# Shell windows that are not apps: report them by what the person sees.
SHELL_CLASSES = {"Progman": "màn hình nền (Desktop)", "WorkerW": "màn hình nền (Desktop)",
                 "Shell_TrayWnd": "thanh taskbar", "Shell_SecondaryTrayWnd": "thanh taskbar"}
STORE_FRAME = "applicationframehost.exe"
STORE_CORE_CLASS = "Windows.UI.Core.CoreWindow"

KNOWN_FOLDERS = {
    "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
}

# What the tutor needs to know opens what. "link" is the http protocol.
DEFAULT_TARGETS = {"link": ("http", ASSOCF_IS_PROTOCOL),
                   ".docx": (".docx", ASSOCF_INIT_IGNOREUNKNOWN),
                   ".pdf": (".pdf", ASSOCF_INIT_IGNOREUNKNOWN),
                   ".xlsx": (".xlsx", ASSOCF_INIT_IGNOREUNKNOWN),
                   ".jpg": (".jpg", ASSOCF_INIT_IGNOREUNKNOWN)}


def _text(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _exe(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return ""
        return Path(buf.value).name
    finally:
        kernel32.CloseHandle(h)


def _cloaked(hwnd) -> bool:
    value = wintypes.DWORD()
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return hr == 0 and value.value != 0


def _enum(fn, parent=None) -> None:
    """EnumWindows/EnumChildWindows with a Python callback; errors in the callback are re-raised.

    `fn(hwnd)` returns False to stop. ctypes would otherwise swallow the exception.
    """
    caught, stopped = [], []

    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            go_on = bool(fn(hwnd))
        except Exception as e:
            caught.append(e)
            return False
        if not go_on:
            stopped.append(True)
        return go_on

    ctypes.set_last_error(0)
    if parent is None:
        ok = user32.EnumWindows(cb, 0)
    else:
        ok = user32.EnumChildWindows(parent, cb, 0)
    if caught:
        raise caught[0]
    if parent is None and not ok and not stopped and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())


def _app_exe(hwnd) -> str:
    """Store apps (Calculator, Settings...) run inside ApplicationFrameHost; report the real app."""
    host_pid = _pid(hwnd)
    exe = _exe(host_pid)
    if exe.lower() != STORE_FRAME:
        return exe
    found = []

    def child(ch):
        p = _pid(ch)
        if p != host_pid:
            found.append(p)
            return False
        return True

    _enum(child, parent=hwnd)
    if not found:  # minimized: the app's window is detached from its frame
        title = _text(hwnd)

        def core(h):
            if _class(h) == STORE_CORE_CLASS and _text(h) == title and _pid(h) != host_pid:
                found.append(_pid(h))
                return False
            return True

        _enum(core)
    return _exe(found[0]) if found else exe


def _owners(hwnd) -> list[str]:
    """Titles of the owning windows, nearest first (an error box -> Save As -> Word)."""
    titles, h = [], user32.GetWindow(hwnd, GW_OWNER)
    while h and len(titles) < 5:
        titles.append(_text(h))
        h = user32.GetWindow(h, GW_OWNER)
    return titles


def describe(hwnd) -> WindowInfo:
    cls = _class(hwnd)
    if cls in SHELL_CLASSES:
        return WindowInfo(title=SHELL_CLASSES[cls], exe="", kind="shell")
    return WindowInfo(
        title=_text(hwnd),
        exe=_app_exe(hwnd),
        minimized=bool(user32.IsIconic(hwnd)),
        maximized=bool(user32.IsZoomed(hwnd)),
        owners=_owners(hwnd),
    )


def _is_task_window(hwnd) -> bool:
    """Roughly the windows Alt+Tab shows."""
    if not user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
        return False
    if _class(hwnd) in SHELL_CLASSES or not _text(hwnd):
        return False
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
        return False
    return not user32.GetWindow(hwnd, GW_OWNER) or bool(ex & WS_EX_APPWINDOW)


def foreground_hwnd():
    return user32.GetForegroundWindow() or None


def list_windows() -> list[tuple[int, WindowInfo]]:
    """Task windows in z-order, top first. EnumWindows walks the z-order from the top."""
    hwnds = []

    def keep(hwnd):
        if _is_task_window(hwnd):
            hwnds.append(hwnd)
        return True

    _enum(keep)
    return [(h, describe(h)) for h in hwnds]


def _assoc(name: str, flags: int, what: int) -> str:
    size = wintypes.DWORD(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    hr = shlwapi.AssocQueryStringW(flags, what, name, None, buf, ctypes.byref(size))
    if hr != 0:
        code = hr & 0xFFFFFFFF
        if code == HR_NO_ASSOCIATION:
            raise LookupError("chưa đặt app nào")
        raise OSError(f"AssocQueryString({name}) HRESULT 0x{code:08X}")
    return buf.value


def default_apps() -> dict[str, str]:
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)  # S_FALSE if already done; harmless
    out = {}
    for key, (name, flags) in DEFAULT_TARGETS.items():
        try:
            exe = Path(_assoc(name, flags, ASSOCSTR_EXECUTABLE)).name
            if exe.lower() in APP_NAMES:
                out[key] = app_name(exe)
                continue
        except LookupError as e:
            out[key] = str(e)
            continue
        except OSError:
            pass  # Store apps (e.g. Photos) may have no plain executable; try the display name
        try:
            out[key] = _assoc(name, flags, ASSOCSTR_FRIENDLYAPPNAME)
        except (LookupError, OSError) as e:
            out[key] = f"không đọc được ({e})"
    return out


def known_folders() -> dict[str, str]:
    out = {}
    for label, gid in KNOWN_FOLDERS.items():
        g = GUID.from_buffer_copy(uuid.UUID(gid).bytes_le)
        p = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
        try:
            if hr != 0:
                raise OSError(f"SHGetKnownFolderPath({label}) HRESULT 0x{hr & 0xFFFFFFFF:08X}")
            out[label] = p.value
        finally:
            if p:
                ole32.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))
    return out
