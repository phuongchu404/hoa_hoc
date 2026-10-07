"""Desktop entry point used by ChemImage.app.

Runs the FastAPI server in a background thread and shows a small native
control window (Dock icon, status, "Mở giao diện" / "Thoát"). The UI itself
opens in the default browser. Quitting the app (⌘Q, the button or closing the
window) stops the server, so nothing keeps running in the background.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "ChemImage"
LOG_DIR = Path.home() / "Library" / "Logs" / APP_NAME


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_DIR / "chemimage.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    sys.stdout = sys.stderr = open(LOG_DIR / "chemimage.out", "a", buffering=1, encoding="utf-8")


def _health(port: int, timeout: float = 0.5) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _free_port(start: int = 8000, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Không tìm được cổng trống")


def main() -> None:
    _setup_logging()
    log = logging.getLogger("desktop")

    # Another copy already running? Just show its UI.
    for port in range(8000, 8020):
        h = _health(port)
        if h is not None and "accelerator" in h:
            webbrowser.open(f"http://127.0.0.1:{port}")
            return

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    import uvicorn

    from app import main as web

    web.DESKTOP.enabled = True  # heartbeat-based auto quit + "Tắt chương trình" button

    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    server_error: list[str] = []

    def serve() -> None:
        try:
            server.run()
        except BaseException as exc:  # noqa: BLE001
            log.exception("server crashed")
            server_error.append(str(exc))

    threading.Thread(target=serve, name="uvicorn", daemon=True).start()
    log.info("starting server on %s", url)
    _run_ui(url, port, server, server_error, web.DESKTOP)


# ----------------------------------------------------------------------------- native UI


# quit this long after the last ChemImage browser tab closed (env override for tests)
IDLE_QUIT_SECONDS = float(os.environ.get("CHEM_IDLE_QUIT_SECONDS", "120"))
OPEN_BROWSER = os.environ.get("CHEM_NO_BROWSER") != "1"


def _run_ui(url: str, port: int, server, server_error: list[str], desktop) -> None:
    import time

    import objc
    from PyObjCTools import AppHelper
    from AppKit import (
        NSApp, NSApplication, NSApplicationActivationPolicyRegular, NSBackingStoreBuffered,
        NSBezelStyleRounded, NSButton, NSFont, NSImage, NSMakeRect, NSMenu, NSMenuItem,
        NSStatusBar, NSTextField, NSTimer, NSVariableStatusItemLength, NSWindow,
        NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskTitled,
    )
    from Foundation import NSBundle, NSObject

    state = {"ready": False, "opened": False, "idle_since": None}
    desktop.on_quit = lambda: AppHelper.callAfter(NSApp.terminate_, None)

    class Controller(NSObject):
        def applicationDidFinishLaunching_(self, _note):  # noqa: N802
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, objc.selector(self.tick_, signature=b"v@:@"), None, True
            )

        def applicationShouldTerminateAfterLastWindowClosed_(self, _app):  # noqa: N802
            return True

        def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _visible):  # noqa: N802
            window.makeKeyAndOrderFront_(None)
            if state["ready"]:
                webbrowser.open(url)
            return True

        def applicationWillTerminate_(self, _note):  # noqa: N802
            server.should_exit = True

        def applicationDockMenu_(self, _app):  # noqa: N802
            return dock_menu

        def tick_(self, _timer):
            if server_error:
                status.setStringValue_("Lỗi khi khởi động. Xem log: ~/Library/Logs/ChemImage")
                return
            if state["ready"]:
                # quit by itself once every ChemImage tab has been closed for a while
                if desktop.last_tab_seen is not None and desktop.open_tabs() == 0:
                    if state["idle_since"] is None:
                        state["idle_since"] = time.monotonic()
                    elif time.monotonic() - state["idle_since"] > IDLE_QUIT_SECONDS:
                        NSApp.terminate_(None)
                else:
                    state["idle_since"] = None
                return
            h = _health(port)
            if h and h.get("ready"):
                state["ready"] = True
                status.setStringValue_("Đang chạy — giao diện mở trong trình duyệt.\n" + url)
                open_btn.setEnabled_(True)
                if not state["opened"]:
                    state["opened"] = True
                    if OPEN_BROWSER:
                        webbrowser.open(url)
            elif h:
                status.setStringValue_("Đang nạp mô hình nhận dạng… (khoảng 10–20 giây)")

        def openUI_(self, _sender):  # noqa: N802
            webbrowser.open(url)

        def quit_(self, _sender):
            NSApp.terminate_(None)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    icon_path = NSBundle.mainBundle().pathForResource_ofType_("AppIcon", "icns")
    if icon_path:
        app.setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(icon_path))
    controller = Controller.alloc().init()
    app.setDelegate_(controller)

    # app menu with Quit (⌘Q)
    menubar = NSMenu.alloc().init()
    app_item = NSMenuItem.alloc().init()
    menubar.addItem_(app_item)
    app_menu = NSMenu.alloc().init()
    app_menu.addItemWithTitle_action_keyEquivalent_("Mở giao diện", "openUI:", "o").setTarget_(controller)
    app_menu.addItem_(NSMenuItem.separatorItem())
    app_menu.addItemWithTitle_action_keyEquivalent_(f"Thoát {APP_NAME}", "terminate:", "q")
    app_item.setSubmenu_(app_menu)
    app.setMainMenu_(menubar)

    def make_menu() -> NSMenu:
        m = NSMenu.alloc().init()
        m.setAutoenablesItems_(False)
        m.addItemWithTitle_action_keyEquivalent_("Mở giao diện ChemImage", "openUI:", "").setTarget_(controller)
        m.addItem_(NSMenuItem.separatorItem())
        m.addItemWithTitle_action_keyEquivalent_(f"Thoát {APP_NAME}", "quit:", "").setTarget_(controller)
        return m

    # right-click on the Dock icon
    dock_menu = make_menu()
    # always-visible icon in the menu bar (top right of the screen)
    status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    status_item.button().setTitle_("⌬")
    status_item.button().setToolTip_("ChemImage đang chạy")
    status_item.setMenu_(make_menu())

    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 440, 200), style, NSBackingStoreBuffered, False
    )
    window.setTitle_("ChemImage → ChemDraw")
    window.center()
    content = window.contentView()

    title = NSTextField.labelWithString_("ChemImage → ChemDraw")
    title.setFont_(NSFont.boldSystemFontOfSize_(17))
    title.setFrame_(NSMakeRect(24, 156, 400, 26))
    content.addSubview_(title)

    status = NSTextField.wrappingLabelWithString_(
        "Đang khởi động… Lần đầu mở có thể mất 1–2 phút (macOS kiểm tra ứng dụng). "
        "Các lần sau chỉ khoảng 10 giây."
    )
    status.setFrame_(NSMakeRect(24, 88, 400, 62))
    content.addSubview_(status)

    hint = NSTextField.wrappingLabelWithString_(
        "Tắt: bấm Thoát, đóng cửa sổ này, hoặc biểu tượng ⌬ trên thanh menu → Thoát. "
        "Đóng trang ChemImage trên trình duyệt thì chương trình tự tắt sau 2 phút."
    )
    hint.setFont_(NSFont.systemFontOfSize_(11))
    hint.setTextColor_(__import__("AppKit").NSColor.secondaryLabelColor())
    hint.setFrame_(NSMakeRect(24, 52, 400, 30))
    content.addSubview_(hint)

    open_btn = NSButton.buttonWithTitle_target_action_("Mở giao diện", controller, "openUI:")
    open_btn.setBezelStyle_(NSBezelStyleRounded)
    open_btn.setFrame_(NSMakeRect(196, 14, 130, 32))
    open_btn.setKeyEquivalent_("\r")
    open_btn.setEnabled_(False)
    content.addSubview_(open_btn)

    quit_btn = NSButton.buttonWithTitle_target_action_("Thoát", controller, "quit:")
    quit_btn.setBezelStyle_(NSBezelStyleRounded)
    quit_btn.setFrame_(NSMakeRect(330, 14, 90, 32))
    content.addSubview_(quit_btn)

    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
