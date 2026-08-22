"""
agent/platforms/linkedin.py
LinkedIn Easy Apply automation using Playwright.
"""

import time
from pathlib import Path
from playwright.sync_api import Page
from rich.console import Console
from rich.markup import escape

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


class LinkedInAgent:
    PLATFORM = "linkedin"

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
        self.browser_cfg = config.get("browser", {})
        self.memory = memory or AnswerMemory()
        self.form_filler = FormFiller(self.memory)
        apply_stealth_scripts(self.page)

    # ─────────────────────────────────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────────────────────────────────

    def _is_logged_in(self) -> bool:
        """
        Reliable login check — strictly looks for DOM elements that ONLY exist
        when an account is authenticated.
        """
        try:
            # If sign-in or join buttons are present, definitely not logged in
            not_logged_in_selectors = [
                'a[href*="login"]',
                'a[href*="checkpoint/rm/sign-in"]',
                'a[href*="signup"]',
                'button.sign-in-form__submit-btn',
                '#username',
                'input[name="session_key"]'
            ]
            for sel in not_logged_in_selectors:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return False

            # Strictly authenticated elements
            indicators = [
                '.global-nav__me-photo',
                '.feed-identity-module',
                'button[id*="global-nav-icon--me"]',
                '.share-box-feed-entry',
                'a.global-nav__primary-link--active',
                'button.global-nav__primary-link-me-menu-trigger'
            ]
            for sel in indicators:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return True
        except Exception:
            pass
        return False

    def login(self, email: str, password: str):
        console.print("[bold blue]LinkedIn:[/] Checking session...")
        try:
            self.page.goto("https://www.linkedin.com/feed", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded")
            human_delay(2000, 3000)
        except Exception as e:
            console.print(f"[dim]LinkedIn:[/] Session check notice: {e}")

        if self._is_logged_in():
            console.print("[bold blue]LinkedIn:[/] ✅ Already logged in")
            save_session(self.page.context, self.PLATFORM)
            return

        console.print("[bold blue]LinkedIn:[/] Logging in with credentials...")
        try:
            self.page.goto("https://www.linkedin.com/login", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded")
            human_delay(1500, 2500)
        except Exception as e:
            console.print(f"[red]LinkedIn:[/] Failed to open login page: {e}")
            return

        # Attempt to fill email in visible input
        email_filled = False
        email_selectors = [
            'input#username',
            'input#session_key',
            'input[name="session_key"]',
            'input[name="username"]',
            'input[type="email"]',
            'input[autocomplete="username"]'
        ]
        for sel in email_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    human_delay(200, 400)
                    el.fill(email)
                    human_delay(300, 600)
                    email_filled = True
                    break
            except Exception:
                continue

        # Attempt to fill password in visible input
        password_filled = False
        pwd_selectors = [
            'input#password',
            'input#session_password',
            'input[name="session_password"]',
            'input[name="password"]',
            'input[type="password"]'
        ]
        for sel in pwd_selectors:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    human_delay(200, 400)
                    el.fill(password)
                    human_delay(300, 600)
                    password_filled = True
                    break
            except Exception:
                continue

        if email_filled and password_filled:
            try:
                submit_btn = (
                    self.page.query_selector('button[type="submit"]') or
                    self.page.query_selector('button[data-litms-control-urn="login-submit"]') or
                    self.page.query_selector('.btn__primary--large')
                )
                if submit_btn and submit_btn.is_visible():
                    submit_btn.click(timeout=3000)
                else:
                    self.page.keyboard.press("Enter")

                self.page.wait_for_load_state("domcontentloaded")
                human_delay(3000, 5000)
            except Exception as e:
                console.print(f"[dim]LinkedIn:[/] Submit notice: {e}")

        # Handle CAPTCHA if shown
        self.form_filler.wait_for_captcha_if_needed(self.page)

        # Check if 2FA pin verification or checkpoint appears
        checkpoint = (
            self.page.query_selector('input[name="pin"]') or
            self.page.query_selector('input[id*="verification"]') or
            self.page.query_selector('#input__phone_verification_pin') or
            "challenge" in self.page.url or
            "checkpoint" in self.page.url
        )
        if checkpoint:
            console.print("\n[bold yellow]🔐 LinkedIn Verification / 2FA detected![/]")
            console.print("[yellow]Please complete the verification in the browser window.[/]")
            from rich.prompt import Prompt
            Prompt.ask("[bold]Press ENTER after you have completed verification in browser[/]")
            human_delay(2000, 3000)

        # Wait for feed or auth elements
        try:
            self.page.wait_for_selector(
                '.global-nav__me-photo, .feed-identity-module, button[id*="global-nav-icon--me"], .share-box-feed-entry',
                timeout=8000
            )
        except Exception:
            pass

        if self._is_logged_in():
            save_session(self.page.context, self.PLATFORM)
            console.print("[bold blue]LinkedIn:[/] ✅ Logged in successfully")
        else:
            console.print("\n[bold red]LinkedIn:[/] ❌ Login could not complete automatically.")
            console.print("[yellow]LinkedIn has bot protection on login forms. Please run this ONCE to login manually:[/]")
            console.print("\n  [bold cyan]python main.py setup-session --platform linkedin[/]\n")
            raise SystemExit(0)

    # ─────────────────────────────────────────────────────────────────────
    # MAIN RUN LOOP
    # ─────────────────────────────────────────────────────────────────────

    def run(self, email: str, password: str):
        self.login(email, password)
        applied = 0
        searches = self.router.get_search_keywords()

        for search in searches:
            if applied >= self.daily_limit:
                console.print(f"[yellow]LinkedIn:[/] Daily limit of {self.daily_limit} reached.")
                break

            keyword   = search["keyword"]
            role_name = search["role_name"]
            resume_path = search["resume"]

            console.print(f"\n[bold blue]LinkedIn:[/] Searching → [cyan]{keyword}[/]")
            applied += self._search_and_apply(keyword, role_name, resume_path, applied)

        console.print(f"\n[bold blue]LinkedIn:[/] Done. Applied to {applied} jobs.")
        return applied

    # ─────────────────────────────────────────────────────────────────────
    # JOB SEARCH
    # ─────────────────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str) -> str:
        encoded = keyword.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={encoded}&f_AL=true"
        if self.location:
            loc = self.location.replace(" ", "%20")
            url += f"&location={loc}"
        
        # Date posted filter:
        # r86400 = Past 24 hours (1 day), r604800 = Past week (7 days)
        if self.date_posted == "24h":
            url += "&f_TPR=r86400"
        elif self.date_posted == "week":
            url += "&f_TPR=r604800"

        # Experience level filter:
        # f_E=1 (Internship), f_E=2 (Entry level / 0-1 YOE)
        if self.experience_level == "entry":
            url += "&f_E=1,2"

        return url

    def _search_and_apply(self, keyword: str, role_name: str, resume_path: str, already_applied: int) -> int:
        count = 0
        url = self._build_search_url(keyword)
        try:
            self.page.goto(url, timeout=35000)
            self.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            console.print(f"[red]LinkedIn:[/] Failed to load search page: {e}")
            return 0

        # Scroll left pane / window to trigger job list loading
        human_scroll(self.page, 450)
        try:
            self.page.evaluate("""
                () => {
                    const list = document.querySelector('.jobs-search-results-list') || 
                                 document.querySelector('.scaffold-layout__list') ||
                                 document.querySelector('.jobs-search__left-rail');
                    if (list) list.scrollTop += 400;
                }
            """)
            human_delay(1200, 2200)
        except Exception:
            pass

        # Wait up to 12s for cards
        try:
            self.page.wait_for_selector(
                'li[data-occludable-job-id], .job-card-container, [data-job-id], a[href*="/jobs/view/"], a.job-card-list__title',
                timeout=12000
            )
        except Exception:
            pass

        # Query all possible card selectors
        job_cards = (
            self.page.query_selector_all("li[data-occludable-job-id]") or
            self.page.query_selector_all("li.jobs-search-results__list-item") or
            self.page.query_selector_all(".scaffold-layout__list-item") or
            self.page.query_selector_all(".job-card-container") or
            self.page.query_selector_all("[data-job-id]") or
            self.page.query_selector_all('a[href*="/jobs/view/"]')
        )

        console.print(f"[blue]LinkedIn:[/] Found {len(job_cards)} job cards for '{keyword}'")

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
                console.print(f"[red]LinkedIn:[/] Error on card: {e}")
                self._close_modal()

        return count

    # ─────────────────────────────────────────────────────────────────────
    # APPLY TO SINGLE JOB
    # ─────────────────────────────────────────────────────────────────────

    def _apply_to_card(self, card, role_name: str, resume_path: str) -> int:
        job_title_text = "Unknown"
        company_text = "Unknown"

        # 1. First extract title and company from the card element directly
        try:
            card_title_el = (
                card.query_selector("a.job-card-list__title") or
                card.query_selector("a.job-card-container__link") or
                card.query_selector(".job-card-list__title") or
                card.query_selector("strong") or
                card.query_selector("a[href*='/jobs/view/']")
            )
            if card_title_el:
                job_title_text = card_title_el.inner_text().strip()

            card_comp_el = (
                card.query_selector(".job-card-container__primary-description") or
                card.query_selector(".artdeco-entity-lockup__subtitle") or
                card.query_selector(".job-card-container__company-name") or
                card.query_selector(".job-card-list__company-name")
            )
            if card_comp_el:
                company_text = card_comp_el.inner_text().strip()
        except Exception:
            pass

        # Click card to open details pane
        try:
            card.scroll_into_view_if_needed()
            human_move_and_click(self.page, card)
            human_delay(1500, 2500)
        except Exception:
            return 0

        # Refine title and company from details pane if available
        try:
            pane_title_el = (
                self.page.query_selector(".job-details-jobs-unified-top-card__job-title h1") or
                self.page.query_selector(".jobs-unified-top-card__job-title h1") or
                self.page.query_selector(".job-details-jobs-unified-top-card__job-title") or
                self.page.query_selector(".jobs-unified-top-card__job-title") or
                self.page.query_selector(".jobs-search__job-details h2")
            )
            if pane_title_el:
                t = pane_title_el.inner_text().strip()
                if t and "jobs in" not in t.lower():
                    job_title_text = t

            pane_comp_el = (
                self.page.query_selector(".jobs-unified-top-card__company-name a") or
                self.page.query_selector(".job-details-jobs-unified-top-card__company-name a") or
                self.page.query_selector(".jobs-unified-top-card__company-name") or
                self.page.query_selector(".jobs-unified-top-card__subtitle-primary-grouping a") or
                self.page.query_selector('[data-control-name="jobdetails_topcard_company_url"]')
            )
            if pane_comp_el:
                c = pane_comp_el.inner_text().strip()
                if c:
                    company_text = c
        except Exception:
            pass

        job_url = self.page.url

        if self.tracker.already_applied(self.PLATFORM, job_url):
            console.print(f"[dim]LinkedIn:[/] Already applied → {job_title_text}, skipping.")
            return 0

        # Extract Job Description text from right pane
        jd_text = ""
        try:
            jd_el = (
                self.page.query_selector('.jobs-description__content') or
                self.page.query_selector('.jobs-box__html-content') or
                self.page.query_selector('#job-details') or
                self.page.query_selector('.jobs-description')
            )
            if jd_el:
                jd_text = jd_el.inner_text().strip()
        except Exception:
            pass

        # Evaluate job for paid status, non-tech/CA exclusions, and tech relevance
        is_valid, actual_role, actual_resume, skip_reason = self.router.evaluate_job(job_title_text, jd_text)
        if not is_valid:
            console.print(f"[dim]LinkedIn:[/] 🚫 Skipping ({skip_reason}) → [yellow]{job_title_text}[/]")
            return 0

        # Find Easy Apply button
        easy_apply_btn = (
            self.page.query_selector('button.jobs-apply-button[aria-label*="Easy Apply"]') or
            self.page.query_selector('button[aria-label*="Easy Apply"]') or
            self.page.query_selector('button:has-text("Easy Apply")') or
            self.page.query_selector('.jobs-apply-button')
        )

        if not easy_apply_btn:
            console.print(f"[dim]LinkedIn:[/] No Easy Apply → '{job_title_text}', skipping.")
            return 0

        console.print(
            f"[blue]LinkedIn:[/] Applying → [cyan]{escape(job_title_text)}[/] "
            f"at [green]{escape(company_text)}[/] | Resume: [magenta]{Path(actual_resume).name}[/]"
        )

        if self.dry_run:
            self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, "DRY_RUN", job_url)
            console.print(f"[dim]LinkedIn:[/] [DRY RUN] Would apply ✓")
            return 1

        try:
            easy_apply_btn.scroll_into_view_if_needed()
            human_move_and_click(self.page, easy_apply_btn)
            human_delay(1500, 2500)
        except Exception as e:
            console.print(f"[red]LinkedIn:[/] Failed to click apply button: {escape(str(e))}")
            return 0

        submitted = self._complete_easy_apply_modal(actual_resume)
        status = "APPLIED" if submitted else "FAILED"
        self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, status, job_url)

        if submitted:
            console.print(f"[green]LinkedIn:[/] ✅ Applied → {escape(job_title_text)}")
            return 1
        else:
            console.print(f"[red]LinkedIn:[/] ❌ Failed → {escape(job_title_text)}")
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # EASY APPLY MODAL
    # ─────────────────────────────────────────────────────────────────────

    def _complete_easy_apply_modal(self, resume_path: str) -> bool:
        max_steps = 12
        for _ in range(max_steps):
            human_delay(1200, 2000)

            # CAPTCHA
            self.form_filler.wait_for_captcha_if_needed(self.page)

            # Resume upload
            file_input = self.page.query_selector('input[type="file"]')
            if file_input and Path(resume_path).exists():
                file_input.set_input_files(resume_path)
                human_delay(800, 1500)

            # Smart form fill
            self.form_filler.fill_form_fields(self.page)
            self.form_filler.handle_checkbox_questions(self.page)

            # Submit
            submit_btn = (
                self.page.query_selector('button[aria-label="Submit application"]') or
                self.page.query_selector('button:has-text("Submit application")')
            )
            if submit_btn:
                human_delay(300, 700)
                submit_btn.click()
                human_delay(2000, 3000)
                self._close_modal()
                return True

            # Review
            review_btn = self.page.query_selector('button[aria-label="Review your application"]')
            if review_btn:
                human_delay(200, 500)
                review_btn.click()
                continue

            # Next step
            next_btn = (
                self.page.query_selector('button[aria-label="Continue to next step"]') or
                self.page.query_selector('button:has-text("Next")')
            )
            if next_btn:
                human_delay(200, 500)
                next_btn.click()
                continue

            # Fallback primary button
            primary = self.page.query_selector('.artdeco-button--primary')
            if primary:
                label = (primary.get_attribute("aria-label") or primary.inner_text() or "").lower()
                if "close" in label or "dismiss" in label or "not now" in label:
                    break
                human_delay(200, 500)
                primary.click()
                continue

            break

        return False

    def _close_modal(self):
        try:
            for sel in ['button[aria-label="Dismiss"]', 'button[aria-label="Close"]']:
                btn = self.page.query_selector(sel)
                if btn:
                    btn.click()
                    human_delay(800, 1200)
                    discard = self.page.query_selector('button[data-control-name="discard_application_confirm_btn"]')
                    if discard:
                        discard.click()
                    break
        except Exception:
            pass
