"""
agent/platforms/naukri.py
Naukri.com job application automation using Playwright.
"""

import time
import urllib.parse
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


class NaukriAgent:
    PLATFORM = "naukri"

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

    # ─────────────────────────────────────────────────────────────────────
    # LOGIN
    # ─────────────────────────────────────────────────────────────────────

    def _is_logged_in(self) -> bool:
        try:
            login_btn = self.page.query_selector('a[href*="nlogin"]')
            if login_btn and login_btn.is_visible():
                return False

            for sel in ['.nI-gNb-drawer__icon', '.user-name', '[class*="userProfile"]',
                        '.view-profile-wrapper', '[data-ga-track*="profile"]', '.nI-gNb-sb__placeholder']:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return True
        except Exception:
            pass
        return False

    def login(self, email: str, password: str):
        console.print("[bold red]Naukri:[/] Checking session...")
        try:
            self.page.goto("https://www.naukri.com/", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded")
            human_delay(2000, 3000)
        except Exception as e:
            console.print(f"[dim]Naukri:[/] Page load notice: {e}")

        if self._is_logged_in():
            console.print("[bold red]Naukri:[/] ✅ Already logged in")
            save_session(self.page.context, self.PLATFORM)
            return

        console.print("[bold red]Naukri:[/] Logging in with credentials...")
        try:
            self.page.goto("https://www.naukri.com/nlogin/login", timeout=30000)
            self.page.wait_for_load_state("domcontentloaded")
            human_delay(1500, 2500)
        except Exception as e:
            console.print(f"[red]Naukri:[/] Failed to open login page: {e}")
            return

        # Email field
        email_input = (
            self.page.query_selector('input[placeholder*="Email"]') or
            self.page.query_selector('input[placeholder*="Username"]') or
            self.page.query_selector('#usernameField') or
            self.page.query_selector('input[type="email"]')
        )
        if email_input:
            email_input.click()
            human_delay(200, 500)
            email_input.type(email, delay=80)
        else:
            console.print("[red]Naukri:[/] Could not find email field")
            return

        human_delay(400, 700)

        # Password field
        password_input = (
            self.page.query_selector('input[placeholder*="password"]') or
            self.page.query_selector('input[placeholder*="Password"]') or
            self.page.query_selector('#passwordField') or
            self.page.query_selector('input[type="password"]')
        )
        if password_input:
            password_input.click()
            human_delay(200, 400)
            password_input.type(password, delay=90)
        else:
            console.print("[red]Naukri:[/] Could not find password field")
            return

        human_delay(500, 900)

        # Submit
        login_btn = (
            self.page.query_selector('button[type="submit"]') or
            self.page.query_selector('button:has-text("Login")') or
            self.page.query_selector('.loginButton')
        )
        if login_btn:
            login_btn.click()
        else:
            self.page.keyboard.press("Enter")

        self.page.wait_for_load_state("domcontentloaded")
        human_delay(3000, 5000)

        # CAPTCHA
        self.form_filler.wait_for_captcha_if_needed(self.page)

        save_session(self.page.context, self.PLATFORM)
        console.print("[bold red]Naukri:[/] ✅ Logged in")

    # ─────────────────────────────────────────────────────────────────────
    # MAIN RUN LOOP
    # ─────────────────────────────────────────────────────────────────────

    def run(self, email: str, password: str):
        self.login(email, password)
        applied = 0
        searches = self.router.get_search_keywords()

        for search in searches:
            if applied >= self.daily_limit:
                console.print(f"[red]Naukri:[/] Daily limit of {self.daily_limit} reached.")
                break

            keyword     = search["keyword"]
            role_name   = search["role_name"]
            resume_path = search["resume"]

            console.print(f"\n[bold red]Naukri:[/] Searching → [cyan]{keyword}[/]")
            applied += self._search_and_apply(keyword, role_name, resume_path, applied)

        console.print(f"\n[bold red]Naukri:[/] Done. Applied to {applied} jobs.")
        return applied

    # ─────────────────────────────────────────────────────────────────────
    # JOB SEARCH
    # ─────────────────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str) -> str:
        slug = keyword.strip().replace(" ", "-").replace("/", "-").lower()
        url = f"https://www.naukri.com/{slug}-jobs"
        if self.location:
            loc_slug = self.location.strip().replace(" ", "-").lower()
            url += f"-in-{loc_slug}"
        
        params = []
        # Date posted filter:
        if self.date_posted == "24h":
            params.append("jobAge=1")
        elif self.date_posted == "week":
            params.append("jobAge=7")

        # Experience level filter (0 YOE / Fresher):
        if self.experience_level == "entry":
            params.append("experience=0")

        if params:
            url += "?" + "&".join(params)

        return url

    def _search_and_apply(self, keyword: str, role_name: str, resume_path: str, already_applied: int) -> int:
        count = 0
        url = self._build_search_url(keyword)

        try:
            self.page.goto(url, timeout=35000)
            self.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            console.print(f"[red]Naukri:[/] Failed to load search: {e}")
            return 0

        # Scroll to trigger lazy-loading/hydration of React components
        human_scroll(self.page, 500)
        human_delay(800, 1500)

        # Wait up to 12s for job listings to appear
        try:
            self.page.wait_for_selector(
                'a[href*="job-listings"], .srp-jobtuple-wrapper, .cust-job-tuple, article.jobTuple, [data-job-id], div[class*="tuple"]',
                timeout=12000
            )
        except Exception:
            pass

        # 1. Primary: Find all job title links directly
        title_links = self.page.query_selector_all('a[href*="job-listings"]')
        if not title_links:
            title_links = self.page.query_selector_all('a.title')

        # 2. Secondary: Card wrappers
        card_wrappers = (
            self.page.query_selector_all(".srp-jobtuple-wrapper") or
            self.page.query_selector_all(".cust-job-tuple") or
            self.page.query_selector_all("article.jobTuple") or
            self.page.query_selector_all("[data-job-id]") or
            self.page.query_selector_all("div[class*='styles_job-listing']")
        )

        job_elements = card_wrappers if card_wrappers else title_links
        console.print(f"[red]Naukri:[/] Found {len(job_elements)} job cards for '{keyword}'")

        if len(job_elements) == 0:
            title = self.page.title()
            console.print(f"[dim]Naukri:[/] Page title: '{title}' | URL: {self.page.url[:80]}")
            return 0

        for item in job_elements:
            if already_applied + count >= self.daily_limit:
                break
            try:
                count += self._apply_to_item(item, role_name, resume_path)
                human_delay(
                    self.delays.get("between_applications", 5) * 1000,
                    self.delays.get("between_applications", 5) * 1000 + 2000
                )
            except Exception as e:
                console.print(f"[red]Naukri:[/] Error on card: {e}")

        return count

    # ─────────────────────────────────────────────────────────────────────
    # APPLY TO SINGLE JOB
    # ─────────────────────────────────────────────────────────────────────

    def _apply_to_item(self, item, role_name: str, resume_path: str) -> int:
        title_el = None
        tag_name = ""
        try:
            tag_name = item.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            pass

        if tag_name == "a":
            title_el = item
            job_title_text = item.inner_text().strip()
            try:
                company_text = item.evaluate("""
                    el => {
                        const card = el.closest('.srp-jobtuple-wrapper') || el.closest('[data-job-id]') || el.closest('article') || el.parentElement.parentElement;
                        if (!card) return 'Unknown';
                        const comp = card.querySelector('.comp-name') || card.querySelector('a.comp-name') || card.querySelector('.subTitle') || card.querySelector('[class*="comp"]');
                        return comp ? comp.innerText.trim() : 'Unknown';
                    }
                """)
            except Exception:
                company_text = "Unknown"
        else:
            try:
                title_el = (
                    item.query_selector('a[href*="job-listings"]') or
                    item.query_selector("a.title") or
                    item.query_selector(".title") or
                    item.query_selector("h2 a") or
                    item.query_selector("a")
                )
                job_title_text = title_el.inner_text().strip() if title_el else "Unknown"
                comp_el = (
                    item.query_selector(".comp-name") or
                    item.query_selector("a.comp-name") or
                    item.query_selector(".subTitle") or
                    item.query_selector('[class*="comp"]')
                )
                company_text = comp_el.inner_text().strip() if comp_el else "Unknown"
            except Exception:
                job_title_text, company_text = "Unknown", "Unknown"
                title_el = None

        if not title_el:
            return 0

        # Pre-evaluate on card text (instant skip for unpaid badges / non-tech titles)
        try:
            card_text = item.inner_text() if item else ""
            is_valid_card, _, _, card_skip = self.router.evaluate_job(job_title_text, card_text)
            if not is_valid_card:
                console.print(f"[dim]Naukri:[/] 🚫 Skipping ({card_skip}) → [yellow]{job_title_text}[/]")
                return 0
        except Exception:
            pass

        # Open job detail page
        detail_page = self.page
        try:
            title_el.scroll_into_view_if_needed()
            with self.page.context.expect_page(timeout=8000) as new_page_info:
                human_move_and_click(self.page, title_el)
            detail_page = new_page_info.value
            detail_page.wait_for_load_state("domcontentloaded")
            human_delay(1500, 2500)
        except Exception:
            human_delay(1500, 2500)
            detail_page = self.page

        job_url = detail_page.url

        if self.tracker.already_applied(self.PLATFORM, job_url):
            console.print(f"[dim]Naukri:[/] Already applied → {job_title_text}, skipping.")
            if detail_page != self.page:
                detail_page.close()
            return 0

        # Extract salary info & full Job Description from detail page
        detail_text = ""
        try:
            salary_el = (
                detail_page.query_selector('.styles_jds__salary__') or
                detail_page.query_selector('.salary') or
                detail_page.query_selector('[class*="sal"]') or
                detail_page.query_selector('.top-card-layout')
            )
            sal_text = salary_el.inner_text().strip() if salary_el else ""

            jd_el = (
                detail_page.query_selector('.dang-inner-html') or
                detail_page.query_selector('.job-desc') or
                detail_page.query_selector('[class*="job-desc"]') or
                detail_page.query_selector('[class*="styles_JDC"]') or
                detail_page.query_selector('.jd-description') or
                detail_page.query_selector('.job-description')
            )
            jd_text = jd_el.inner_text().strip() if jd_el else ""
            detail_text = f"{sal_text} {jd_text}"
        except Exception:
            pass

        # Evaluate job for paid status, non-tech/CA exclusions, and tech relevance
        is_valid, actual_role, actual_resume, skip_reason = self.router.evaluate_job(job_title_text, detail_text)
        if not is_valid:
            console.print(f"[dim]Naukri:[/] 🚫 Skipping ({skip_reason}) → [yellow]{job_title_text}[/]")
            if detail_page != self.page:
                try:
                    detail_page.close()
                except Exception:
                    pass
            return 0

        # Look for Apply button
        apply_btn = (
            detail_page.query_selector('button[id="apply-button"]') or
            detail_page.query_selector('a[id="apply-button"]') or
            detail_page.query_selector('button:has-text("Apply")') or
            detail_page.query_selector('.apply-button') or
            detail_page.query_selector('[class*="apply-button"]') or
            detail_page.query_selector('button:has-text("Apply on website")') or
            detail_page.query_selector('[class*="apply"][class*="btn"]')
        )

        if not apply_btn:
            console.print(f"[dim]Naukri:[/] No Apply button for '{job_title_text}', skipping.")
            if detail_page != self.page:
                detail_page.close()
            return 0

        console.print(
            f"[red]Naukri:[/] Applying → [cyan]{escape(job_title_text)}[/] "
            f"at [green]{escape(company_text)}[/] | Resume: [magenta]{Path(actual_resume).name}[/]"
        )

        if self.dry_run:
            self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, "DRY_RUN", job_url)
            console.print(f"[dim]Naukri:[/] [DRY RUN] Would apply ✓")
            if detail_page != self.page:
                try:
                    detail_page.close()
                except Exception:
                    pass
            return 1

        # Check if button is for external company site
        btn_text = (apply_btn.inner_text() or "").strip().lower()
        is_company_site = "company site" in btn_text or "website" in btn_text or "external" in btn_text

        # Click Apply button (listening for possible new tab for external career page)
        try:
            apply_btn.scroll_into_view_if_needed()
            human_delay(200, 400)
            with detail_page.context.expect_page(timeout=5000) as company_page_info:
                human_move_and_click(detail_page, apply_btn)
            company_page = company_page_info.value
            company_page.wait_for_load_state("domcontentloaded")
            human_delay(2000, 3500)
            apply_target_page = company_page
            is_company_site = True
        except Exception:
            apply_target_page = detail_page

        # Complete application on either external ATS or Naukri internal modal/chatbot
        if is_company_site and apply_target_page != detail_page:
            submitted = self.form_filler.handle_external_company_apply(apply_target_page, actual_resume)
            try:
                apply_target_page.close()
            except Exception:
                pass
        else:
            submitted = self._complete_naukri_apply(detail_page, actual_resume)

        status = "APPLIED" if submitted else "FAILED"
        self.tracker.log(self.PLATFORM, job_title_text, company_text, actual_role, actual_resume, status, job_url)

        if detail_page != self.page:
            try:
                detail_page.close()
            except Exception:
                pass

        if submitted:
            console.print(f"[green]Naukri:[/] ✅ Applied → {escape(job_title_text)}")
            return 1
        else:
            console.print(f"[red]Naukri:[/] ❌ Failed → {escape(job_title_text)}")
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # APPLY MODAL / CHATBOT HANDLER
    # ─────────────────────────────────────────────────────────────────────

    def _complete_naukri_apply(self, page: Page, resume_path: str) -> bool:
        human_delay(1500, 2500)

        # 1. Check for immediate success banner (Direct One-Click Apply)
        immediate_success = (
            page.query_selector('div:has-text("applied successfully")') or
            page.query_selector('div:has-text("Application sent")') or
            page.query_selector('div:has-text("already applied")') or
            page.query_selector('.apply-message') or
            page.query_selector('.success-message') or
            page.query_selector('[class*="already-applied"]')
        )
        if immediate_success and immediate_success.is_visible():
            return True

        # 2. Check if Recruiter Chatbot drawer opened
        chatbot = (
            page.query_selector('.chatbot_drawer') or
            page.query_selector('.chat-drawer') or
            page.query_selector('[class*="chatbot"]') or
            page.query_selector('.layer-content')
        )
        if chatbot and chatbot.is_visible():
            return self.form_filler.handle_naukri_chatbot(page)

        # 3. Check for standard Questionnaire / Multi-step Modal
        max_steps = 8
        for _ in range(max_steps):
            human_delay(1500, 2500)

            self.form_filler.wait_for_captcha_if_needed(page)

            # Upload resume if prompted
            upload_btn = (
                page.query_selector('button:has-text("Update Resume")') or
                page.query_selector('button:has-text("Upload Resume")') or
                page.query_selector('[class*="upload"][class*="resume"]')
            )
            if upload_btn and upload_btn.is_visible():
                try:
                    upload_btn.click()
                    human_delay(800, 1200)
                    file_input = page.query_selector('input[type="file"]')
                    if file_input and Path(resume_path).exists():
                        file_input.set_input_files(resume_path)
                        human_delay(1500, 2500)
                except Exception:
                    pass

            # Smart form fill & questions
            self.form_filler.fill_form_fields(page)
            self.form_filler.handle_checkbox_questions(page)

            # Check if success message appeared
            success = (
                page.query_selector('div:has-text("applied successfully")') or
                page.query_selector('div:has-text("Application sent")') or
                page.query_selector('.apply-message') or
                page.query_selector('[class*="success"]')
            )
            if success and success.is_visible():
                return True

            # Submit / Save & Apply button
            submit_btn = (
                page.query_selector('button:has-text("Save & Apply")') or
                page.query_selector('button:has-text("Submit")') or
                page.query_selector('button[id="apply-button"]') or
                page.query_selector('button:has-text("Apply")')
            )
            if submit_btn and submit_btn.is_visible():
                try:
                    human_move_and_click(page, submit_btn)
                    human_delay(2000, 3500)
                    return True
                except Exception:
                    pass

            # If no modal / chatbot was opened, and button was clicked without errors
            break

        return True
