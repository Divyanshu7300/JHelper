"""
agent/orchestrator.py
Main orchestrator — coordinates all platforms with stealth and session management.
"""

import time
import os
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.markup import escape

from agent.resume_router import ResumeRouter
from agent.tracker import ApplicationTracker
from agent.memory import AnswerMemory
from agent.telegram_bot import TelegramBot
from agent.stealth import (
    STEALTH_BROWSER_ARGS,
    get_session_storage_state,
    apply_stealth_scripts
)
from agent.platforms.linkedin import LinkedInAgent
from agent.platforms.indeed import IndeedAgent
from agent.platforms.naukri import NaukriAgent

console = Console()
load_dotenv()


class Orchestrator:
    def __init__(self, config: dict, dry_run: bool = False, platforms_filter: list = None):
        self.config = config
        self.dry_run = dry_run
        self.platforms_filter = platforms_filter or ["linkedin", "indeed", "naukri"]
        self.tracker = ApplicationTracker()
        self.router = ResumeRouter()
        self.memory = AnswerMemory()
        self.telegram = TelegramBot()
        self.browser_cfg = config.get("browser", {})

    def _get_context_options(self, platform: str) -> dict:
        """Constructs an anti-detect context configuration."""
        saved_session = get_session_storage_state(platform)
        opts = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "Asia/Kolkata",
            "geolocation": {"latitude": 12.9716, "longitude": 77.5946},
            "permissions": ["geolocation", "notifications"],
            "device_scale_factor": 2,
            "has_touch": False,
            "is_mobile": False,
        }
        if saved_session:
            opts["storage_state"] = saved_session
        return opts

    def run(self):
        console.rule("[bold green]Job Application Agent Starting[/]")
        if self.dry_run:
            console.print("[bold yellow]⚠  DRY RUN MODE — No applications will be submitted[/]\n")

        results = {}
        platforms_cfg = self.config.get("platforms", {})
        delays = self.config.get("delays", {})

        with sync_playwright() as pw:
            # Launch Chrome with stealth arguments
            try:
                browser = pw.chromium.launch(
                    channel="chrome",
                    headless=self.browser_cfg.get("headless", False),
                    slow_mo=self.browser_cfg.get("slow_mo_ms", 100),
                    args=STEALTH_BROWSER_ARGS,
                )
                console.print("[dim]🌐 Using Google Chrome (Stealth Enabled)[/]")
            except Exception:
                console.print("[dim]🌐 Chrome not found, using Chromium (Stealth Enabled)[/]")
                browser = pw.chromium.launch(
                    headless=self.browser_cfg.get("headless", False),
                    slow_mo=self.browser_cfg.get("slow_mo_ms", 100),
                    args=STEALTH_BROWSER_ARGS,
                )

            # ── LinkedIn ──────────────────────────────────────────────────
            if "linkedin" in self.platforms_filter and platforms_cfg.get("linkedin", True):
                email = os.getenv("LINKEDIN_EMAIL", "")
                password = os.getenv("LINKEDIN_PASSWORD", "")
                
                ctx_opts = self._get_context_options("linkedin")
                ctx = browser.new_context(**ctx_opts)
                page = ctx.new_page()
                apply_stealth_scripts(page)

                agent = LinkedInAgent(page, self.config, self.tracker, self.router, self.dry_run, self.memory)
                try:
                    count = agent.run(email, password)
                    results["linkedin"] = count
                except SystemExit:
                    results["linkedin"] = 0
                except Exception as e:
                    console.print(f"[red]LinkedIn crashed:[/] {escape(str(e))}")
                    results["linkedin"] = 0
                finally:
                    ctx.close()
                time.sleep(delays.get("between_platforms", 30))

            # ── Indeed ────────────────────────────────────────────────────
            if "indeed" in self.platforms_filter and platforms_cfg.get("indeed", True):
                ctx_opts = self._get_context_options("indeed")
                ctx = browser.new_context(**ctx_opts)
                page = ctx.new_page()
                apply_stealth_scripts(page)

                agent = IndeedAgent(page, self.config, self.tracker, self.router, self.dry_run, self.memory)
                try:
                    count = agent.run()
                    results["indeed"] = count
                except SystemExit:
                    results["indeed"] = 0
                except Exception as e:
                    console.print(f"[red]Indeed crashed:[/] {escape(str(e))}")
                    results["indeed"] = 0
                finally:
                    ctx.close()
                time.sleep(delays.get("between_platforms", 30))

            # ── Naukri ────────────────────────────────────────────────────
            if "naukri" in self.platforms_filter and platforms_cfg.get("naukri", True):
                email = os.getenv("NAUKRI_EMAIL", "")
                password = os.getenv("NAUKRI_PASSWORD", "")
                
                ctx_opts = self._get_context_options("naukri")
                ctx = browser.new_context(**ctx_opts)
                page = ctx.new_page()
                apply_stealth_scripts(page)

                agent = NaukriAgent(page, self.config, self.tracker, self.router, self.dry_run, self.memory)
                try:
                    count = agent.run(email, password)
                    results["naukri"] = count
                except SystemExit:
                    results["naukri"] = 0
                except Exception as e:
                    console.print(f"[red]Naukri crashed:[/] {escape(str(e))}")
                    results["naukri"] = 0
                finally:
                    ctx.close()

            browser.close()

        self._print_summary(results)
        return results

    def _print_summary(self, results: dict):
        console.rule("[bold green]Session Summary[/]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Platform", style="bold")
        table.add_column("Applied This Session", justify="right")
        table.add_column("Applied Today (Total)", justify="right")

        for platform, count in results.items():
            today_total = self.tracker.count_today(platform)
            table.add_row(platform.capitalize(), str(count), str(today_total))

        console.print(table)
        csv_path = self.tracker.export_csv()
        console.print(f"\n📄 Full log exported → [link]{csv_path}[/link]")
        self.telegram.notify_summary(results, self.tracker)
