"""
agent/memory.py
Persistent Q&A memory — stores user answers to form questions.
Checks memory before asking the user, saves new answers for future use.
"""

from typing import Optional

import json
import os
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

console = Console()

MEMORY_FILE = "memory.json"


class AnswerMemory:
    def __init__(self, memory_path: str = MEMORY_FILE):
        self.memory_path = Path(memory_path)
        self.data: dict = self._load()

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

    def _normalize_key(self, question: str) -> str:
        """Normalize question text to a consistent key."""
        return question.strip().lower().replace("  ", " ")

    def get(self, question: str) -> Optional[str]:
        """Return saved answer for a question, or None if not known."""
        key = self._normalize_key(question)
        return self.data.get(key)

    def ask_and_save(self, question: str, field_type: str = "text") -> str:
        """
        Ask the user for an answer in the terminal, save it, and return it.
        field_type: 'text', 'number', 'yesno'
        """
        key = self._normalize_key(question)

        # Check memory first
        if key in self.data:
            saved = self.data[key]
            console.print(f"\n[dim]💾 Memory:[/] [cyan]{question}[/] → [green]{saved}[/] (using saved answer)")
            return saved

        # Ask user
        console.print(f"\n[bold yellow]❓ Form is asking:[/] [cyan]{question}[/]")
        console.print("[dim](This answer will be saved — you won't be asked again)[/]")

        if field_type == "yesno":
            answer = Prompt.ask("Your answer", choices=["yes", "no", "y", "n"], default="yes")
            answer = "Yes" if answer.lower() in ("yes", "y") else "No"
        elif field_type == "number":
            while True:
                answer = Prompt.ask("Your answer (number)")
                if answer.strip().isdigit():
                    break
                console.print("[red]Please enter a number.[/]")
        else:
            answer = Prompt.ask("Your answer")

        # Save
        self.data[key] = answer
        self._save()
        console.print(f"[green]✅ Saved to memory.[/]\n")
        return answer

    def show_all(self):
        """Print all saved answers."""
        if not self.data:
            console.print("[dim]Memory is empty.[/]")
            return
        from rich.table import Table
        table = Table(title="📋 Saved Answers (memory.json)", show_header=True, header_style="bold cyan")
        table.add_column("Question", style="cyan")
        table.add_column("Your Answer", style="green")
        for q, a in self.data.items():
            table.add_row(q, a)
        console.print(table)

    def delete(self, question: str):
        """Remove a saved answer so it gets asked again."""
        key = self._normalize_key(question)
        if key in self.data:
            del self.data[key]
            self._save()
            console.print(f"[yellow]Deleted answer for:[/] {question}")
        else:
            console.print(f"[dim]Not found in memory:[/] {question}")
