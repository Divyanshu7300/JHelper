#!/usr/bin/env python3
"""
main.py — CLI entry point for the Job Application Agent.

Usage:
  python main.py                          # Run all platforms (live)
  python main.py --dry-run                # Simulate without submitting
  python main.py --platform linkedin      # Only LinkedIn
  python main.py --platform naukri --dry-run
  python main.py --export                 # Export applications.db → applications.csv
  python main.py --stats                  # Show today's application stats
"""

import click
import yaml
from rich.console import Console
from rich.table import Table
from pathlib import Path

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


@click.group(invoke_without_command=True)
@click.option("--platform", "-p", default="all",
              type=click.Choice(["all", "linkedin", "indeed", "naukri"], case_sensitive=False),
              help="Which platform to run (default: all)")
@click.option("--dry-run", "-d", is_flag=True, default=False,
              help="Simulate applications without submitting")
@click.option("--headed", "--visible", is_flag=True, default=False,
              help="Show the browser window (default is background/headless)")
@click.option("--config", "-c", default="config.yaml",
              help="Path to config file (default: config.yaml)")
@click.pass_context
def cli(ctx, platform, dry_run, headed, config):
    """🤖 Job Application Agent — auto-applies with the right resume per role."""
    if ctx.invoked_subcommand is not None:
        return

    # Validate resumes exist
    cfg = load_config(config)
    _check_resumes(cfg)

    if headed:
        if "browser" not in cfg:
            cfg["browser"] = {}
        cfg["browser"]["headless"] = False

    platforms_filter = ["linkedin", "indeed", "naukri"] if platform == "all" else [platform]

    from agent.orchestrator import Orchestrator
    orchestrator = Orchestrator(cfg, dry_run=dry_run, platforms_filter=platforms_filter)
    orchestrator.run()


@cli.command()
def stats():
    """Show today's application statistics."""
    from agent.tracker import ApplicationTracker
    tracker = ApplicationTracker()

    table = Table(title="Today's Applications", show_header=True, header_style="bold cyan")
    table.add_column("Platform")
    table.add_column("Applied Today", justify="right")

    for p in ["linkedin", "indeed", "naukri"]:
        count = tracker.count_today(p)
        table.add_row(p.capitalize(), str(count))

    console.print(table)


@cli.command()
@click.option("--output", "-o", default="applications.csv", help="Output CSV filename")
def export(output):
    """Export all applications to CSV."""
    from agent.tracker import ApplicationTracker
    tracker = ApplicationTracker()
    path = tracker.export_csv(output)
    console.print(f"✅ Exported to [bold]{path}[/]")


def _check_resumes(cfg: dict):
    resume_dir = Path("resumes")
    if not resume_dir.exists():
        resume_dir.mkdir()
        console.print("[yellow]⚠  Created resumes/ folder. Place your PDF files there.[/]")

    roles = cfg.get("roles", [])
    missing = []
    for role in roles:
        resume_file = resume_dir / role["resume"]
        if not resume_file.exists():
            missing.append(str(resume_file))

    if missing:
        console.print("[bold red]⚠  Missing resume files:[/]")
        for m in missing:
            console.print(f"   • {m}")
        console.print("\nPlace your PDFs in the [bold]resumes/[/] folder and re-run.\n")


@cli.command()
def memory():
    """View all saved Q&A answers (used to auto-fill forms)."""
    from agent.memory import AnswerMemory
    mem = AnswerMemory()
    mem.show_all()


@cli.command("forget")
@click.argument("question", required=False)
def forget(question):
    """Delete a saved answer so the agent asks you again.
    
    Usage:
      python main.py forget                          # Clear ALL saved answers
      python main.py forget "What is your notice period?"
    """
    from agent.memory import AnswerMemory
    mem = AnswerMemory()
    
    if question:
        mem.delete(question)
    else:
        # Clear all
        if click.confirm("⚠  Delete ALL saved answers from memory?"):
            mem.data = {}
            mem._save()
            console.print("[yellow]Memory cleared.[/]")


@cli.command("clear-sessions")
@click.option("--platform", "-p", default="all",
              type=click.Choice(["all", "linkedin", "indeed", "naukri"], case_sensitive=False))
def clear_sessions(platform):
    """Delete saved login sessions (forces re-login on next run)."""
    from agent.stealth import clear_session
    platforms = ["linkedin", "indeed", "naukri"] if platform == "all" else [platform]
    for p in platforms:
        clear_session(p)
    console.print("[green]Done.[/]")


# ─────────────────────────────────────────────────────────────────────────────
# MANUAL SESSION SETUP
# Use this when a platform uses Google OAuth, OTP, or any login you can't
# automate. The browser opens, you login yourself, agent saves cookies.
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_URLS = {
    "linkedin": "https://www.linkedin.com/login",
    "indeed":   "https://secure.indeed.com/auth?hl=en_IN&co=IN",
    "naukri":   "https://www.naukri.com/nlogin/login",
}

PLATFORM_READY_CHECK = {
    "linkedin": "https://www.linkedin.com/feed",
    "indeed":   "https://in.indeed.com/",
    "naukri":   "https://www.naukri.com/",
}


@cli.command("setup-session")
@click.option("--platform", "-p", required=True,
              type=click.Choice(["linkedin", "indeed", "naukri"], case_sensitive=False),
              help="Which platform to setup the session for")
def setup_session(platform):
    """
    Manually login to a platform and save the session.

    Opens a real browser window — you login however you want
    (Google, OTP, email+password). Once you're on the home page,
    press ENTER in this terminal and the session is saved permanently.

    Usage:
      python main.py setup-session --platform indeed
      python main.py setup-session --platform linkedin
      python main.py setup-session --platform naukri
    """
    from playwright.sync_api import sync_playwright
    from agent.stealth import apply_stealth_scripts, save_session, STEALTH_BROWSER_ARGS
    from pathlib import Path

    console.rule(f"[bold cyan]Manual Session Setup — {platform.capitalize()}[/]")
    console.print(f"\n[bold]A browser will open.[/] Log in to [cyan]{platform}[/] however you like:")
    console.print("  • Google login ✅")
    console.print("  • Email OTP ✅")
    console.print("  • Email + Password ✅\n")
    console.print("Once you're fully logged in and on the home/feed page,")
    console.print("[bold green]come back here and press ENTER.[/]\n")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                channel="chrome",
                headless=False,
                slow_mo=100,
                args=STEALTH_BROWSER_ARGS + ["--start-maximized"],
            )
        except Exception:
            browser = pw.chromium.launch(
                headless=False,
                slow_mo=100,
                args=STEALTH_BROWSER_ARGS + ["--start-maximized"],
            )

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kolkata",
            permissions=["geolocation", "notifications"],
        )
        page = context.new_page()
        apply_stealth_scripts(page)

        login_url = PLATFORM_URLS.get(platform, PLATFORM_READY_CHECK[platform])
        page.goto(login_url)

        # Wait for user to login manually
        input("\n>>> Press ENTER after you're fully logged in <<<\n")

        # Save cookies + localStorage
        save_session(context, platform)
        console.print(f"\n[bold green]✅ Session saved for {platform.capitalize()}![/]")
        console.print(f"[dim]Stored at: sessions/{platform}_session.json[/]")
        console.print("\nNext time you run the agent, it will [bold]skip login automatically.[/]")

        browser.close()


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Path to config file")
def telegram(config):
    """🤖 Start the Telegram Remote Bot to operate the agent from your phone."""
    cfg = load_config(config)
    from agent.telegram_bot import TelegramBot
    bot = TelegramBot()
    bot.start_polling(cfg)


if __name__ == "__main__":
    cli()
