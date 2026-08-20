"""
agent/platforms/indeed.py
Indeed job application automation using Playwright.
"""

import time
from pathlib import Path
from playwright.sync_api import Page
from rich.console import Console

from agent.stealth import (
    apply_stealth_scripts,
    human_delay,
    human_move_and_click,
    human_scroll,
    save_session
)
from agent.form_filler import FormFiller
from agent.memory import AnswerMemory

console = Console()


class IndeedAgent:
    PLATFORM = "indeed"

    def __init__(self, page: Page, config: dict, tracker, router, dry_run: bool = False, memory: AnswerMemory = None):
        self.page = page
        self.config = config
        self.tracker = tracker
        self.router = router
        self.dry_run = dry_run
        self.delays = config.get("delays", {})
        self.daily_limit = config.get("daily_limit", 20)
        self.location = config.get("location", "")
        self.date_posted = config.get("date_posted", "week")
        self.experience_level = config.get("experience_level", "entry")
        self.memory = memory or AnswerMemory()
        self.form_filler = FormFiller(self.memory)
        apply_stealth_scripts(self.page)

    def login(self, email: str = "", password: str = ""):
        """
        Indeed uses Google OAuth / OTP — auto email+password login doesn't work.
        Session must be set up manually once via:
            python main.py setup-session --platform indeed
        """
        try:
            self.page.goto("https://in.indeed.com/", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded")
            human_delay(1000, 1500)
        except Exception:
            pass

        # Check if already logged in via saved session
        logged_in = (
            self.page.query_selector('[data-gnav-element-name="MyJobs"]') or
            self.page.query_selector('a[href*="myjobs"]') or
            self.page.query_selector('[aria-label="My Jobs"]') or
            self.page.query_selector('[data-gnav-element-name="Account"]') or
            "dashboard" in self.page.url
        )

        if logged_in:
            console.print("[bold yellow]Indeed:[/] ✅ Using saved session")
            return

        # No session found — can't auto-login (Google OAuth / OTP)
        console.print("\n[bold red]Indeed:[/] ❌ No saved session found!")
        console.print("[yellow]Indeed uses Google / OTP login — run this once to set it up:[/]")
        console.print("\n  [bold cyan]python main.py setup-session --platform indeed[/]\n")
        raise SystemExit(0)

    def run(self, email: str = "", password: str = ""):
        self.login()
        applied = 0
        searches = self.router.get_search_keywords()

        for search in searches:
            if applied >= self.daily_limit:
                console.print(f"[yellow]Indeed:[/] Daily limit of {self.daily_limit} reached.")
                break

            keyword = search["keyword"]
            role_name = search["role_name"]
            resume_path = search["resume"]

            console.print(f"\n[bold yellow]Indeed:[/] Searching → [cyan]{keyword}[/]")
            applied += self._search_and_apply(keyword, role_name, resume_path, applied)

        console.print(f"\n[bold yellow]Indeed:[/] Done. Applied to {applied} jobs.")
        return applied

    def _build_search_url(self, keyword: str) -> str:
        encoded = keyword.replace(" ", "+")
        url = f"https://in.indeed.com/jobs?q={encoded}&iafilter=1"
        if self.location:
            loc = self.location.replace(" ", "+")
            url += f"&l={loc}"
        
        # Date posted filter:
        # fromage=1 (1 day), fromage=7 (1 week)
        if self.date_posted == "24h":
            url += "&fromage=1"
        elif self.date_posted == "week":
            url += "&fromage=7"

        # Experience level filter:
        if self.experience_level == "entry":
            url += "&sc=0kf%3Aexplvl(ENTRY_LEVEL)%3B"

        return url

    def _search_and_apply(self, keyword: str, role_name: str, resume_path: str, already_applied: int) -> int:
        count = 0
        url = self._build_search_url(keyword)
        try:
            self.page.goto(url, timeout=35000)
            self.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            console.print(f"[red]Indeed:[/] Failed to load search: {e}")
            return 0

        # Scroll page smoothly
        human_scroll(self.page, 450)
        human_delay(800, 1500)

        try:
            self.page.wait_for_selector(
                '.job_seen_beacon, div.cardOutline, td.resultContent, a[data-jk], div[data-jk]',
                timeout=12000
            )
        except Exception:
            pass

        job_cards = (
            self.page.query_selector_all(".job_seen_beacon") or
            self.page.query_selector_all("div.cardOutline") or
            self.page.query_selector_all("td.resultContent") or
            self.page.query_selector_all("div[data-jk]") or
            self.page.query_selector_all("a[data-jk]")
        )
        console.print(f"[yellow]Indeed:[/] Found {len(job_cards)} job cards for '{keyword}'")

        for card in job_cards:
            if already_applied + count >= self.daily_limit:
                break
            try:
                count += self._apply_to_card(card, role_name, resume_path)
                human_delay(
                    self.delays.get("between_applications", 5) * 1000,
                    self.delays.get("between_applications", 5) * 1000 + 2000
                )
            except Exception as e:
                console.print(f"[red]Indeed:[/] Error on card: {e}")

        return count

    def _apply_to_card(self, card, role_name: str, resume_path: str) -> int:
        try:
            title_el = (
                card.query_selector("h2.jobTitle span") or
                card.query_selector("h2.jobTitle a") or
                card.query_selector("h2.jobTitle") or
                card.query_selector("a[data-jk]") or
                card.query_selector("a[id*='job_']")
            )
            job_title_text = title_el.inner_text().strip() if title_el else "Unknown"
            company_el = (
                card.query_selector('[data-testid="company-name"]') or
                card.query_selector(".companyName") or
                card.query_selector('[class*="companyName"]')
            )
            company_text = company_el.inner_text().strip() if company_el else "Unknown"

            # Click to open job
            link = (
                card.query_selector("h2.jobTitle a") or
                card.query_selector("a[data-jk]") or
                card.query_selector("a")
            )
            if link:
                link.scroll_into_view_if_needed()
                human_move_and_click(self.page, link)
                human_delay(1500, 2500)
        except Exception:
            job_title_text, company_text = "Unknown", "Unknown"

        job_url = self.page.url

        if self.tracker.already_applied(self.PLATFORM, job_url):
            console.print(f"[dim]Indeed:[/] Already applied → {job_title_text}, skipping.")
            return 0

        # Extract Job Description text from right pane
        jd_text = ""
        try:
            jd_el = (
                self.page.query_selector('#jobDescriptionText') or
                self.page.query_selector('.jobsearch-JobComponent-description') or
                self.page.query_selector('.jobsearch-jobDescriptionText')
            )
            if jd_el:
                jd_text = jd_el.inner_text().strip()
        except Exception:
            pass

        # Evaluate job for paid status, non-tech/CA exclusions, and tech relevance
        is_valid, actual_role, actual_resume, skip_reason = self.router.evaluate_job(job_title_text, jd_text)
        if not is_valid:
            console.print(f"[dim]Indeed:[/] 🚫 Skipping ({skip_reason}) → [yellow]{job_title_text}[/]")
            return 0

        # Look for Indeed Apply button
        apply_btn = (
            self.page.query_selector('button[id="indeedApplyButton"]') or
            self.page.query_selector('span[id="indeedApplyButton"]') or
            self.page.query_selector('button:has-text("Apply now")') or
            self.page.query_selector('button[aria-label*="Apply"]') or
            self.page.query_selector('#indeedApplyButton')
        )

        if not apply_btn:
            console.print(f"[dim]Indeed:[/] No Indeed Apply button for '{job_title_text}', skipping.")
            return 0

        console.print(f"[yellow]Indeed:[/] Applying → [cyan]{job_title_text}[/] at [green]{company_text}[/] | Resume: [magenta]{Path(actual_resume).name}[/]")

        if self.dry_run:
            self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, "DRY_RUN", job_url)
            console.print(f"[dim]Indeed:[/] [DRY RUN] Would apply ✓")
            return 1

        try:
            apply_btn.scroll_into_view_if_needed()
            human_move_and_click(self.page, apply_btn)
            human_delay(2000, 3000)
        except Exception as e:
            console.print(f"[red]Indeed:[/] Failed to click apply button: {e}")
            return 0

        submitted = self._complete_indeed_apply(actual_resume)
        status = "APPLIED" if submitted else "FAILED"
        self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, status, job_url)

        if submitted:
            console.print(f"[green]Indeed:[/] ✅ Applied → {job_title_text}")
            return 1
        else:
            console.print(f"[red]Indeed:[/] ❌ Failed → {job_title_text}")
            return 0

    def _complete_indeed_apply(self, resume_path: str) -> bool:
        max_steps = 10
        for _ in range(max_steps):
            human_delay(1500, 2500)

            # Upload resume if prompted
            file_input = self.page.query_selector('input[type="file"]')
            if file_input and Path(resume_path).exists():
                file_input.set_input_files(resume_path)
                human_delay(800, 1500)

            # Smart form fill
            self.form_filler.fill_form_fields(self.page)

            # Submit
            submit_btn = (
                self.page.query_selector('button[aria-label="Submit your application"]') or
                self.page.query_selector('button:has-text("Submit application")') or
                self.page.query_selector('button:has-text("Submit")')
            )
            if submit_btn:
                submit_btn.click()
                human_delay(2000, 3000)
                return True

            continue_btn = (
                self.page.query_selector('button:has-text("Continue")') or
                self.page.query_selector('button[aria-label="Continue"]') or
                self.page.query_selector('button:has-text("Review your application")')
            )
            if continue_btn:
                continue_btn.click()
                continue

            break
        return False
