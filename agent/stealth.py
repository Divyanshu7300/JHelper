"""
agent/stealth.py
Advanced browser stealth and anti-bot bypass module.
Applies browser fingerprint masking, human interaction physics,
and session management.
"""

from typing import Optional, List, Dict
import json
import time
import random
import math
from pathlib import Path
from playwright.sync_api import BrowserContext, Page, ElementHandle
from rich.console import Console

console = Console()

SESSIONS_DIR = Path("sessions")

# ─────────────────────────────────────────────────────────────────────────────
# ANTI-DETECTION BROWSER LAUNCH ARGUMENTS
# ─────────────────────────────────────────────────────────────────────────────
STEALTH_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
    "--hide-scrollbars",
    "--mute-audio",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-extensions-with-background-pages",
    "--disable-extensions",
    "--disable-features=TranslateUI",
    "--disable-ipc-flooding-protection",
    "--disable-renderer-backgrounding",
    "--enable-features=NetworkService,NetworkServiceInProcess",
    "--force-color-profile=srgb",
]


# ─────────────────────────────────────────────────────────────────────────────
# COMPREHENSIVE STEALTH INJECTION SCRIPT
# Masks webdriver, userAgentData, plugins, webgl, notifications, canvas
# ─────────────────────────────────────────────────────────────────────────────
ADVANCED_STEALTH_JS = """
(() => {
    // 1. Remove navigator.webdriver completely
    const newProto = Object.getPrototypeOf(navigator);
    delete newProto.webdriver;
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // 2. Realistic Chrome runtime and window.chrome object
    if (!window.chrome) {
        window.chrome = {};
    }
    window.chrome.runtime = {
        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        connect: function () {},
        sendMessage: function () {}
    };
    window.chrome.loadTimes = function () {
        return {
            commitLoadTime: Date.now() / 1000 - 1.5,
            connectionInfo: 'http/1.1',
            finishDocumentLoadTime: Date.now() / 1000 - 0.5,
            finishLoadTime: Date.now() / 1000,
            firstPaintAfterLoadTime: 0,
            firstPaintTime: Date.now() / 1000 - 0.8,
            navigationType: 'Other',
            npnNegotiatedProtocol: 'unknown',
            requestTime: Date.now() / 1000 - 2.0,
            startLoadTime: Date.now() / 1000 - 1.8,
            wasAlternateProtocolAvailable: false,
            wasFetchedViaSpdy: false,
            wasNpnNegotiated: false
        };
    };
    window.chrome.csi = function () {
        return {
            startE: Date.now() - 2000,
            onloadT: Date.now() - 500,
            pageT: 1500,
            tran: 15
        };
    };
    window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
    };

    // 3. Fake realistic plugins array
    const fakePlugins = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 2 }
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => fakePlugins,
        configurable: true
    });

    // 4. Fake languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'hi'],
        configurable: true
    });

    // 5. Fake hardware concurrency & device memory
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8, configurable: true });

    // 6. Fake permissions query
    const origPermissions = window.navigator.permissions ? window.navigator.permissions.query : null;
    if (origPermissions) {
        window.navigator.permissions.query = (parameters) =>
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origPermissions(parameters);
    }

    // 7. Spoof WebGL Vendor & Renderer (Apple Silicon / Intel)
    const getParameterOrig = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Google Inc. (Apple)';
        if (parameter === 37446) return 'ANGLE (Apple, Apple M1, OpenGL 4.1)';
        return getParameterOrig.call(this, parameter);
    };
    if (window.WebGL2RenderingContext) {
        const getParameter2Orig = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (Apple)';
            if (parameter === 37446) return 'ANGLE (Apple, Apple M1, OpenGL 4.1)';
            return getParameter2Orig.call(this, parameter);
        };
    }

    // 8. Patch iframe contentWindow to propagate stealth to child frames
    const origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (origContentWindow) {
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function () {
                const win = origContentWindow.get.apply(this);
                if (win && win.navigator) {
                    try {
                        Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
                    } catch (e) {}
                }
                return win;
            }
        });
    }
})();
"""


def apply_stealth_scripts(page: Page):
    """Inject comprehensive anti-detection JS before any script runs."""
    page.add_init_script(ADVANCED_STEALTH_JS)


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN INTERACTION ENGINE (DELAYS, CURVED MOVEMENTS, TYPING, SMOOTH SCROLL)
# ─────────────────────────────────────────────────────────────────────────────

def human_delay(min_ms: int = 300, max_ms: int = 900):
    """Natural variable delay."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def human_type(page: Page, selector: str, text: str, clear_first: bool = True):
    """
    Types text character-by-character with natural human typing physics:
    - Variable delay per character (50ms - 180ms)
    - Occasional micro-pauses (simulating cognitive reading/thinking)
    """
    try:
        el = page.wait_for_selector(selector, timeout=8000)
        if not el:
            return
        el.click()
        human_delay(150, 350)

        if clear_first:
            el.fill("")
            human_delay(100, 250)

        for i, char in enumerate(text):
            # 8% chance of slightly longer pause (thinking pause)
            if random.random() < 0.08:
                human_delay(200, 450)
            
            delay = random.randint(45, 140)
            el.type(char, delay=delay)

        human_delay(200, 500)
    except Exception as e:
        try:
            page.fill(selector, text)
        except Exception:
            pass


def human_move_and_click(page: Page, element: ElementHandle):
    """
    Simulates natural human mouse movement to element with slight random offset
    and clicks.
    """
    try:
        box = element.bounding_box()
        if not box:
            element.click()
            return

        # Target a random coordinate within 30%-70% of bounding box
        target_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
        target_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)

        # Move mouse smoothly through intermediate control point
        page.mouse.move(target_x, target_y, steps=random.randint(5, 12))
        human_delay(100, 250)
        page.mouse.click(target_x, target_y)
        human_delay(200, 500)
    except Exception:
        try:
            element.click()
        except Exception:
            pass


def human_scroll(page: Page, distance_px: int = 400):
    """
    Smoothly scrolls the page in progressive human chunks rather than instant jump.
    """
    try:
        steps = random.randint(3, 6)
        chunk = distance_px // steps
        for _ in range(steps):
            jitter = random.randint(-15, 25)
            page.evaluate(f"window.scrollBy({{ top: {chunk + jitter}, behavior: 'smooth' }});")
            human_delay(150, 350)
        human_delay(400, 800)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STORAGE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def save_session(context: BrowserContext, platform: str):
    """Save browser cookies and localStorage state."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    session_file = SESSIONS_DIR / f"{platform}_session.json"
    storage = context.storage_state()
    with open(session_file, "w") as f:
        json.dump(storage, f, indent=2)
    console.print(f"[dim]🍪 Session state securely cached for {platform}[/]")


def get_session_storage_state(platform: str) -> Optional[dict]:
    """Load cached session if available."""
    session_file = SESSIONS_DIR / f"{platform}_session.json"
    if session_file.exists():
        try:
            with open(session_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def clear_session(platform: str):
    """Clear cached session for a platform."""
    session_file = SESSIONS_DIR / f"{platform}_session.json"
    if session_file.exists():
        session_file.unlink()
        console.print(f"[yellow]Session cleared for {platform}[/]")
