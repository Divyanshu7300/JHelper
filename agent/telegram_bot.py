"""
agent/telegram_bot.py
Full-featured Telegram remote control, interactive Q&A bridge, and live alerts.
Enables operating the Job Agent entirely from Telegram when away from your computer.
Zero external dependencies (uses native urllib.request).
"""

from typing import Optional, Dict, List, Any
import os
import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from rich.console import Console
from rich.markup import escape

console = Console()


class TelegramBot:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.is_configured = bool(self.token and len(self.token) > 10)
        self.last_update_id = 0
        self.running_thread: Optional[threading.Thread] = None
        self.current_task_name: str = "Idle"
        self.stop_requested = False

    # ─────────────────────────────────────────────────────────────────────────
    # CORE TELEGRAM HTTP METHODS (Native urllib)
    # ─────────────────────────────────────────────────────────────────────────

    def _api_call(self, endpoint: str, payload: dict, timeout: int = 15) -> Optional[dict]:
        """Make an API call to Telegram Bot API."""
        if not self.is_configured:
            return None
        url = f"{self.base_url}/{endpoint}"
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                if res_json.get("ok"):
                    return res_json.get("result")
        except Exception as e:
            console.print(f"[dim]Telegram API call error ({endpoint}): {escape(str(e))}[/]")
        return None

    def send_message(self, text: str, chat_id: Optional[str] = None, parse_mode: str = "Markdown", reply_markup: Optional[dict] = None) -> bool:
        """Send a formatted message to Telegram."""
        target_chat_id = chat_id or self.chat_id
        if not self.is_configured or not target_chat_id:
            return False

        payload: Dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "disable_web_page_preview": True
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        res = self._api_call("sendMessage", payload)
        return res is not None

    def get_updates(self, offset: int = 0, timeout: int = 25) -> list:
        """Fetch incoming messages via long polling."""
        if not self.is_configured:
            return []
        payload = {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"]
        }
        res = self._api_call("getUpdates", payload, timeout=timeout + 5)
        return res or []

    # ─────────────────────────────────────────────────────────────────────────
    # NOTIFICATIONS
    # ─────────────────────────────────────────────────────────────────────────

    def notify_applied(self, platform: str, job_title: str, company: str, resume_name: str, url: str = ""):
        """Notify on successful application submission."""
        msg = (
            f"✅ *Applied to Job!*\n\n"
            f"🌐 *Platform:* `{platform.capitalize()}`\n"
            f"💼 *Role:* {job_title}\n"
            f"🏢 *Company:* *{company}*\n"
            f"📄 *Resume:* `{resume_name}`\n"
        )
        if url:
            msg += f"🔗 [View Job Posting]({url})"
        self.send_message(msg)

    def notify_captcha(self, platform: str):
        """High-priority notification for CAPTCHA."""
        msg = (
            f"🔐 *CAPTCHA Alert!*\n\n"
            f"A CAPTCHA or verification check appeared on *{platform.capitalize()}*.\n"
            f"Please solve it in the browser on your computer."
        )
        self.send_message(msg)

    def notify_summary(self, results: dict, tracker: Any = None):
        """Send session summary report."""
        msg = "📊 *Job Application Session Summary*\n\n"
        total_session = 0
        for p, count in results.items():
            total_session += count
            today_total = tracker.count_today(p) if tracker else count
            msg += f"• *{p.capitalize()}*: Applied this run: `{count}` | Today total: `{today_total}`\n"

        msg += f"\n🎉 *Total Applied This Session:* `{total_session}`"
        self.send_message(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTIVE Q&A (Ask user on Telegram, await reply)
    # ─────────────────────────────────────────────────────────────────────────

    def ask_question_interactive(self, question: str, timeout_seconds: int = 60) -> Optional[str]:
        """
        Sends an unknown form question to Telegram and waits for user's reply.
        Returns the user's answer text, or None if timed out.
        """
        if not self.is_configured or not self.chat_id:
            return None

        msg = (
            f"❓ *Job Form Question Alert!*\n\n"
            f"*Question:* {question}\n\n"
            f"👉 *Reply directly with your answer* (Timeout: {timeout_seconds}s)"
        )
        self.send_message(msg)
        console.print(f"[bold yellow]📱 Waiting up to {timeout_seconds}s for answer on Telegram...[/]")

        start_time = time.time()
        # Fast poll for response
        while time.time() - start_time < timeout_seconds:
            updates = self.get_updates(offset=self.last_update_id + 1, timeout=3)
            for u in updates:
                self.last_update_id = max(self.last_update_id, u.get("update_id", 0))
                msg_obj = u.get("message", {})
                from_chat_id = str(msg_obj.get("chat", {}).get("id", ""))

                # Verify message is from authorized user
                if from_chat_id == str(self.chat_id):
                    text = msg_obj.get("text", "").strip()
                    if text and not text.startswith("/"):
                        self.send_message(f"✅ *Received answer:* `{text}`\n_Continuing application..._")
                        console.print(f"[bold green]📱 Received answer from Telegram:[/] [cyan]{text}[/]")
                        return text

            time.sleep(1)

        console.print("[dim]📱 Telegram response timeout — falling back to AI answerer.[/]")
        self.send_message(f"⏱️ *Timeout:* Auto-answering via AI to keep application moving.")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # TELEGRAM DAEMON / REMOTE CONTROLLER
    # ─────────────────────────────────────────────────────────────────────────

    def get_main_keyboard(self) -> dict:
        """Main reply keyboard with action buttons."""
        return {
            "keyboard": [
                [{"text": "🚀 Apply All"}, {"text": "🧪 Dry Run"}],
                [{"text": "💼 Naukri"}, {"text": "👔 LinkedIn"}, {"text": "🔍 Indeed"}],
                [{"text": "📊 Stats"}, {"text": "📋 Memory"}, {"text": "🛑 Stop"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    def _run_agent_task(self, platform: str, dry_run: bool, config: dict):
        """Worker thread to run orchestrator in background."""
        self.current_task_name = f"Running ({platform.capitalize()}{' - Dry Run' if dry_run else ''})"
        self.send_message(f"🚀 *Started Job Agent*\nPlatform: `{platform}`\nMode: `{'Dry Run' if dry_run else 'Live Submissions'}`")

        try:
            from agent.orchestrator import Orchestrator
            platforms_filter = ["linkedin", "indeed", "naukri"] if platform == "all" else [platform]
            orchestrator = Orchestrator(config, dry_run=dry_run, platforms_filter=platforms_filter)
            results = orchestrator.run()
            self.notify_summary(results, orchestrator.tracker)
        except Exception as e:
            self.send_message(f"❌ *Error running agent:* `{e}`")
        finally:
            self.current_task_name = "Idle"
            self.send_message("🏁 *Task Finished.* Ready for next command.", reply_markup=self.get_main_keyboard())

    def start_polling(self, config: dict):
        """
        Continuous long-polling daemon.
        Listens for Telegram commands and executes agent actions remotely.
        """
        console.rule("[bold cyan]Telegram Remote Daemon Started[/]")
        if not self.is_configured:
            console.print("[bold red]Telegram bot token is not configured in .env![/]")
            console.print("[yellow]Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to use Telegram bot.[/]\n")
            return

        # Send startup greeting
        startup_msg = (
            "🤖 *JHelp Telegram Remote Controller is Online!*\n\n"
            "You can operate your Job Application Agent remotely from here.\n\n"
            "👉 *Quick Commands:*\n"
            "• `/apply` or `🚀 Apply All` — Run all platforms\n"
            "• `/naukri` or `💼 Naukri` — Run Naukri only\n"
            "• `/linkedin` or `👔 LinkedIn` — Run LinkedIn only\n"
            "• `/indeed` or `🔍 Indeed` — Run Indeed only\n"
            "• `/dryrun` or `🧪 Dry Run` — Simulate applications\n"
            "• `/stats` or `📊 Stats` — View today's stats\n"
            "• `/memory` or `📋 Memory` — View saved profile answers\n"
            "• `/status` — Check agent status\n"
            "• `/stop` — Stop current task"
        )
        self.send_message(startup_msg, reply_markup=self.get_main_keyboard())
        console.print("[green]✅ Connected to Telegram! Listening for commands... (Press Ctrl+C to exit)[/]\n")

        while not self.stop_requested:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1, timeout=20)
                for u in updates:
                    self.last_update_id = max(self.last_update_id, u.get("update_id", 0))
                    msg_obj = u.get("message", {})
                    text = msg_obj.get("text", "").strip()
                    chat_id = str(msg_obj.get("chat", {}).get("id", ""))

                    if not text:
                        continue

                    # Auto-bind chat ID if not set
                    if not self.chat_id:
                        self.chat_id = chat_id
                        console.print(f"[green]📱 Auto-bound Chat ID:[/] {chat_id}")

                    # Handle Commands & Keyboard buttons
                    cmd = text.lower()

                    if cmd in ("/start", "/help", "help"):
                        self.send_message(startup_msg, reply_markup=self.get_main_keyboard())

                    elif cmd in ("/status", "status"):
                        self.send_message(f"ℹ️ *Agent Status:* `{self.current_task_name}`")

                    elif cmd in ("/stats", "📊 stats", "stats"):
                        from agent.tracker import ApplicationTracker
                        tracker = ApplicationTracker()
                        msg = "📊 *Today's Applications*\n\n"
                        for p in ["linkedin", "indeed", "naukri"]:
                            c = tracker.count_today(p)
                            msg += f"• *{p.capitalize()}*: `{c}` applied\n"
                        self.send_message(msg)

                    elif cmd in ("/memory", "📋 memory", "memory"):
                        from agent.memory import AnswerMemory
                        mem = AnswerMemory()
                        msg = "📋 *Saved Profile Answers:*\n\n"
                        for k, v in list(mem.data.items())[:15]:
                            msg += f"• *{k}*: `{v}`\n"
                        self.send_message(msg)

                    elif cmd in ("/apply", "/run", "🚀 apply all"):
                        if self.current_task_name != "Idle":
                            self.send_message(f"⚠️ Agent is already busy: `{self.current_task_name}`")
                        else:
                            t = threading.Thread(target=self._run_agent_task, args=("all", False, config), daemon=True)
                            t.start()

                    elif cmd in ("/naukri", "💼 naukri"):
                        if self.current_task_name != "Idle":
                            self.send_message(f"⚠️ Agent is already busy: `{self.current_task_name}`")
                        else:
                            t = threading.Thread(target=self._run_agent_task, args=("naukri", False, config), daemon=True)
                            t.start()

                    elif cmd in ("/linkedin", "👔 linkedin"):
                        if self.current_task_name != "Idle":
                            self.send_message(f"⚠️ Agent is already busy: `{self.current_task_name}`")
                        else:
                            t = threading.Thread(target=self._run_agent_task, args=("linkedin", False, config), daemon=True)
                            t.start()

                    elif cmd in ("/indeed", "🔍 indeed"):
                        if self.current_task_name != "Idle":
                            self.send_message(f"⚠️ Agent is already busy: `{self.current_task_name}`")
                        else:
                            t = threading.Thread(target=self._run_agent_task, args=("indeed", False, config), daemon=True)
                            t.start()

                    elif cmd in ("/dryrun", "🧪 dry run"):
                        if self.current_task_name != "Idle":
                            self.send_message(f"⚠️ Agent is already busy: `{self.current_task_name}`")
                        else:
                            t = threading.Thread(target=self._run_agent_task, args=("all", True, config), daemon=True)
                            t.start()

                    elif cmd in ("/stop", "🛑 stop"):
                        self.send_message("🛑 *Stop requested.* Finishing current action.")
                        self.current_task_name = "Idle"

                    else:
                        self.send_message(
                            f"❓ Unrecognized command: `{text}`\nUse the buttons below or type `/help`.",
                            reply_markup=self.get_main_keyboard()
                        )

            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping Telegram daemon...[/]")
                break
            except Exception as e:
                console.print(f"[dim]Telegram polling loop error: {escape(str(e))}[/]")
                time.sleep(2)
