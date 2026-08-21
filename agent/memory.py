"""
agent/memory.py
Persistent Q&A memory & smart answer resolution.
Integrates with ProfileManager and AIAnswerer to ensure the user is NEVER
asked for the same information twice, and twisted/open-ended questions
are intelligently answered by AI.
"""

from typing import Optional, Dict
import json
import re
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

from agent.profile_manager import ProfileManager
from agent.ai_answerer import AIAnswerer

console = Console()

MEMORY_FILE = "memory.json"


class AnswerMemory:
    def __init__(self, memory_path: str = MEMORY_FILE):
        self.memory_path = Path(memory_path)
        self.profile_mgr = ProfileManager()
        self.ai_answerer = AIAnswerer(self.profile_mgr)
        from agent.telegram_bot import TelegramBot
        self.telegram = TelegramBot()
        self.data: dict = self._load()
        self._seed_from_profile()

    def _load(self) -> dict:
        if self.memory_path.exists():
            try:
                with open(self.memory_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save(self):
        with open(self.memory_path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _seed_from_profile(self):
        """Seed memory from profile.json for common questions."""
        p = self.profile_mgr.get_raw_profile()
        if not p:
            return

        defaults = {
            "first_name": p.get("personal", {}).get("first_name", "Divyanshu"),
            "last_name": p.get("personal", {}).get("last_name", "Nagar"),
            "full_name": p.get("personal", {}).get("full_name", "Divyanshu Nagar"),
            "email": p.get("personal", {}).get("email", "divyanshunagar0000@gmail.com"),
            "phone": p.get("personal", {}).get("phone", "7300257595"),
            "location": p.get("location", {}).get("city", "Jaipur"),
            "current_city": p.get("location", {}).get("city", "Jaipur"),
            "expected_ctc": p.get("compensation_and_notice", {}).get("expected_ctc", "6 LPA"),
            "current_ctc": p.get("compensation_and_notice", {}).get("current_ctc", "0"),
            "notice_period": p.get("compensation_and_notice", {}).get("notice_period", "0 days"),
            "experience": p.get("experience", {}).get("years_of_experience", "0"),
            "portfolio": p.get("links", {}).get("portfolio", "https://portfolio-lime-eta-60.vercel.app/"),
            "linkedin": p.get("links", {}).get("linkedin", "https://linkedin.com/in/divyanshu0000"),
            "github": p.get("links", {}).get("github", "https://github.com/Divyanshu7300"),
            "college": p.get("education", {}).get("college", "Manipal University Jaipur"),
            "degree": p.get("education", {}).get("highest_degree", "Master of Computer Applications (MCA)"),
            "graduation_year": p.get("education", {}).get("graduation_year", "2026"),
        }
        for k, v in defaults.items():
            if k not in self.data or not self.data[k]:
                self.data[k] = v
        self._save()

    def _normalize_key(self, question: str) -> str:
        """Strip punctuation, asterisks, brackets, and extra whitespace."""
        clean = question.strip().lower()
        clean = re.sub(r"[\*\:\(\)\[\]\{\}\-\_\,\.\?\/]", " ", clean)
        return re.sub(r"\s+", " ", clean).strip()

    def get(self, question: str) -> Optional[str]:
        """
        Multi-tier answer resolution:
        1. Canonical profile lookup
        2. Normalized memory lookup
        3. Fuzzy key match
        """
        # Tier 1: Canonical profile matching
        profile_val = self.profile_mgr.match_field(question)
        if profile_val is not None and str(profile_val).strip():
            return str(profile_val).strip()

        # Tier 2: Normalized exact memory lookup
        norm_key = self._normalize_key(question)
        if norm_key in self.data and self.data[norm_key]:
            return self.data[norm_key]

        # Tier 3: Substring / Fuzzy match in memory
        for k, v in self.data.items():
            if v and (k in norm_key or norm_key in k):
                return v

        return None

    def resolve_or_ask(self, question: str, field_type: str = "text", auto_ai: bool = True) -> str:
        """
        Full resolution pipeline:
        1. Profile/Memory check
        2. Telegram interactive ask (if user configured TelegramBot and is away)
        3. AI generation (if auto_ai is True and open-ended question)
        4. Terminal prompt to user (saves to memory)
        """
        saved = self.get(question)
        if saved is not None and str(saved).strip():
            return str(saved).strip()

        # Check if Telegram interactive ask is configured
        if self.telegram and self.telegram.is_configured and self.telegram.chat_id:
            telegram_ans = self.telegram.ask_question_interactive(question, timeout_seconds=45)
            if telegram_ans:
                norm_key = self._normalize_key(question)
                self.data[norm_key] = telegram_ans
                self._save()
                return telegram_ans

        # Check if AI can answer
        if auto_ai:
            ai_ans = self.ai_answerer.answer_question(question, field_type)
            if ai_ans and len(ai_ans.strip()) > 0:
                norm_key = self._normalize_key(question)
                self.data[norm_key] = ai_ans
                self._save()
                return ai_ans

        # Fallback to interactive ask
        return self.ask_and_save(question, field_type)

    def ask_and_save(self, question: str, field_type: str = "text") -> str:
        """Ask user in terminal, save, and return answer."""
        norm_key = self._normalize_key(question)

        saved = self.get(question)
        if saved is not None and str(saved).strip():
            return str(saved).strip()

        console.print(f"\n[bold yellow]❓ Form Question:[/] [bold cyan]{question}[/]")
        console.print("[dim](Your answer will be permanently remembered)[/]")

        if field_type == "yesno":
            answer = Prompt.ask("Your answer", choices=["yes", "no", "y", "n"], default="yes")
            answer = "Yes" if answer.lower() in ("yes", "y") else "No"
        elif field_type == "number":
            while True:
                answer = Prompt.ask("Your answer (number)")
                if answer.strip().isdigit():
                    break
                console.print("[red]Please enter a valid number.[/]")
        else:
            answer = Prompt.ask("Your answer")

        self.data[norm_key] = answer
        self._save()
        console.print(f"[green]✅ Saved to memory permanently.[/]\n")
        return answer

    def show_all(self):
        """Print all saved answers."""
        if not self.data:
            console.print("[dim]Memory is empty.[/]")
            return
        from rich.table import Table
        table = Table(title="📋 Saved Answers & Profile (memory.json)", show_header=True, header_style="bold cyan")
        table.add_column("Question / Key", style="cyan")
        table.add_column("Your Answer", style="green")
        for q, a in self.data.items():
            table.add_row(q, str(a))
        console.print(table)

    def delete(self, question: str):
        """Remove a saved answer."""
        norm_key = self._normalize_key(question)
        if norm_key in self.data:
            del self.data[norm_key]
            self._save()
            console.print(f"[yellow]Deleted answer for:[/] {question}")
        else:
            console.print(f"[dim]Not found in memory:[/] {question}")
