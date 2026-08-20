"""
agent/form_filler.py
Smart form filler — handles standard forms, multi-step ATS modals,
Naukri recruiter chatbots, and external company site applications.
Checks memory, pauses to ask the user if needed, and saves answers permanently.
"""

from typing import Optional, List, Dict
import time
import random
import re
from pathlib import Path
from playwright.sync_api import Page, ElementHandle
from rich.console import Console
from rich.prompt import Prompt

from agent.memory import AnswerMemory
from agent.stealth import human_delay, human_type, human_move_and_click

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Comprehensive field patterns → auto-answer logic
# The agent checks these FIRST before falling back to memory/user-ask
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_FIELD_PATTERNS = {
    # Full Name / First / Last Name
    r"^(full\s*name|your\s*name|candidate\s*name)$": {"key": "full_name", "prompt": "What is your full name?"},
    r"^(first\s*name|given\s*name)$": {"key": "first_name", "prompt": "What is your first name?"},
    r"^(last\s*name|surname|family\s*name)$": {"key": "last_name", "prompt": "What is your last name?"},

    # Email & Phone
    r"^(email|email\s*address|e-mail)$": {"key": "email_address", "prompt": "What is your email address?"},
    r"(phone|mobile|contact\s*number|phone\s*number)": {"key": "phone_number", "prompt": "What is your phone/mobile number?"},

    # Notice Period
    r"notice\s*period": {"key": "notice_period", "prompt": "What is your notice period? (e.g. Immediate / 15 Days / 30 Days)"},

    # CTC / Compensation
    r"expected\s*(ctc|salary|compensation|lpa|package)": {"key": "expected_ctc", "prompt": "What is your expected CTC/salary? (e.g. 6 LPA / 8 LPA / Negotiable)"},
    r"current\s*(ctc|salary|compensation|lpa|package)": {"key": "current_ctc", "prompt": "What is your current CTC/salary? (e.g. 0 LPA / Fresher)"},

    # Experience
    r"(years?\s*of\s*experience|total\s*experience|work\s*experience|relevant\s*experience)": {"key": "years_of_experience", "prompt": "How many years of experience do you have? (e.g. 0 / Fresher)"},

    # Social Profiles
    r"linkedin\s*(url|profile|link)?": {"key": "linkedin_url", "prompt": "What is your LinkedIn profile URL?"},
    r"github\s*(url|profile|link)?": {"key": "github_url", "prompt": "What is your GitHub profile URL?"},
    r"portfolio\s*(url|link|website)?": {"key": "portfolio_url", "prompt": "What is your portfolio/website URL?"},

    # Location & Relocation
    r"(current\s*city|current\s*location|city\s*of\s*residence|where\s*are\s*you\s*located)": {"key": "current_city", "prompt": "What is your current city?"},
    r"willing\s*to\s*relocat": {"key": "willing_to_relocate", "prompt": "Are you willing to relocate?", "type": "yesno"},
    r"(work\s*authori|visa|authorized\s*to\s*work)": {"key": "work_authorization", "prompt": "Are you authorized to work in India?", "type": "yesno"},

    # Education / College
    r"(college|university|institute|school)": {"key": "college_name", "prompt": "What is your college/university name?"},
    r"(degree|qualification|highest\s*education)": {"key": "degree", "prompt": "What is your degree/qualification? (e.g. B.Tech Computer Science)"},
    r"(graduation\s*year|passing\s*year|year\s*of\s*graduation)": {"key": "graduation_year", "prompt": "What is your graduation/passing year? (e.g. 2024 / 2025)"},
    r"(branch|stream|field\s*of\s*study|specialization|major)": {"key": "branch", "prompt": "What is your branch/stream? (e.g. Computer Science Engineering)"},
    r"(cgpa|gpa|percentage|marks)": {"key": "cgpa", "prompt": "What is your CGPA / Percentage? (e.g. 8.5 CGPA)"},

    # Availability & Full-time
    r"(available|availability|start\s*date|when\s*can\s*you\s*start|can\s*you\s*join)": {"key": "availability", "prompt": "When can you start? (e.g. Immediately)"},
    r"(full\s*time|internship\s*duration|duration|commitment)": {"key": "internship_duration", "prompt": "Are you available for 6 months full-time internship?", "type": "yesno"},

    # Gender & Personal
    r"gender": {"key": "gender", "prompt": "What is your gender? (e.g. Male / Female)"},
    r"(date\s*of\s*birth|dob|birth\s*date)": {"key": "date_of_birth", "prompt": "What is your date of birth? (DD/MM/YYYY)"},
    r"cover\s*letter": {"key": "cover_letter", "prompt": "Write a short cover letter (2-3 sentences):"},
}


class FormFiller:
    def __init__(self, memory: AnswerMemory):
        self.memory = memory

    # ─────────────────────────────────────────────────────────────────────────
    # STANDARD FORM FILLING
    # ─────────────────────────────────────────────────────────────────────────

    def fill_form_fields(self, page: Page) -> int:
        """
        Scans all visible input/select/textarea fields on the page.
        Resolves answers via known patterns -> memory -> interactive terminal ask.
        """
        filled = 0
        fields = page.query_selector_all(
            'input:not([type="hidden"]):not([type="file"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), '
            'textarea, select'
        )

        for field in fields:
            try:
                if not field.is_visible():
                    continue

                # Skip already filled fields
                current_value = self._get_field_value(field)
                if current_value and current_value.strip():
                    continue

                label = self._get_label(page, field)
                if not label:
                    continue

                answer = self._resolve_answer(label, field)
                if answer:
                    self._fill_field(field, answer)
                    filled += 1
                    human_delay(150, 350)

            except Exception as e:
                console.print(f"[dim]FormFiller: skipping field — {e}[/]")

        return filled

    def _get_field_value(self, field: ElementHandle) -> str:
        try:
            tag = field.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                return field.evaluate("el => el.options[el.selectedIndex]?.text || ''")
            return field.input_value() or ""
        except Exception:
            return ""

    def _get_label(self, page: Page, field: ElementHandle) -> str:
        """Extract clean human-readable label from field attributes or nearby text."""
        try:
            # 1. aria-label
            aria_label = field.get_attribute("aria-label")
            if aria_label and len(aria_label.strip()) > 1:
                return aria_label.strip()

            # 2. placeholder
            placeholder = field.get_attribute("placeholder")
            if placeholder and len(placeholder.strip()) > 1:
                return placeholder.strip()

            # 3. associated <label for="...">
            field_id = field.get_attribute("id")
            if field_id:
                label_el = page.query_selector(f'label[for="{field_id}"]')
                if label_el and label_el.inner_text().strip():
                    return label_el.inner_text().strip()

            # 4. parent label or preceding label container
            parent_text = field.evaluate("""
                el => {
                    const label = el.closest('label') || el.closest('.form-group') || el.closest('[class*="field"]');
                    if (label) {
                        const lbl = label.querySelector('label') || label.querySelector('span');
                        if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                    }
                    return '';
                }
            """)
            if parent_text:
                return parent_text.strip()

            # 5. name attribute
            name = field.get_attribute("name")
            if name and len(name) > 1:
                return name.replace("-", " ").replace("_", " ").strip()

        except Exception:
            pass
        return ""

    def _resolve_answer(self, label: str, field: ElementHandle = None) -> Optional[str]:
        """
        Resolves answer:
        1. Checks KNOWN_FIELD_PATTERNS
        2. Checks AnswerMemory
        3. Prompts user interactively & saves to memory
        """
        label_lower = label.lower().strip()

        # 1. Match known patterns
        for pattern, meta in KNOWN_FIELD_PATTERNS.items():
            if re.search(pattern, label_lower):
                field_key = meta["key"]
                field_prompt = meta["prompt"]
                field_type = meta.get("type", "text")
                answer = self.memory.ask_and_save(field_prompt, field_type)
                return answer

        # 2. Check memory directly
        saved = self.memory.get(label)
        if saved:
            console.print(f"[dim]💾 Memory auto-fill:[/] [cyan]{label}[/] → [green]{saved}[/]")
            return saved

        # 3. Unknown field — prompt user interactively
        console.print(f"\n[bold yellow]❓ Job Application asks:[/] [bold cyan]{label}[/]")
        answer = self.memory.ask_and_save(label)
        return answer if answer else None

    def _fill_field(self, field: ElementHandle, value: str):
        """Fill an input/select/textarea field using human typing physics."""
        try:
            tag = field.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                try:
                    field.select_option(label=value)
                except Exception:
                    try:
                        field.select_option(value=value)
                    except Exception:
                        pass
                return

            field.scroll_into_view_if_needed()
            field.click()
            time.sleep(random.uniform(0.1, 0.25))
            field.fill("")
            time.sleep(random.uniform(0.05, 0.15))

            for char in value:
                delay = random.randint(40, 110)
                field.type(char, delay=delay)
            time.sleep(random.uniform(0.1, 0.25))

        except Exception:
            try:
                field.fill(value)
            except Exception:
                pass

    def handle_checkbox_questions(self, page: Page):
        """Answer radio groups and required checkboxes."""
        try:
            radios = page.query_selector_all('input[type="radio"]')
            handled_groups = set()
            for r in radios:
                name = r.get_attribute("name")
                if not name or name in handled_groups:
                    continue
                handled_groups.add(name)

                # Check if group has a checked radio
                is_checked = page.evaluate(f'document.querySelector(\'input[type="radio"][name="{name}"]:checked\') !== null')
                if not is_checked:
                    # Look for positive options like "Yes", "Immediate", "0", "Fresher"
                    group_radios = page.query_selector_all(f'input[type="radio"][name="{name}"]')
                    clicked = False
                    for gr in group_radios:
                        label_text = gr.evaluate("""
                            el => {
                                const lbl = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                                return lbl ? lbl.innerText.trim().toLowerCase() : (el.value || '').toLowerCase();
                            }
                        """)
                        if any(pos in label_text for pos in ["yes", "immediate", "fresher", "0", "agree", "authorized", "100"]):
                            gr.click()
                            clicked = True
                            break
                    if not clicked and group_radios:
                        group_radios[0].click()
        except Exception:
            pass

    def wait_for_captcha_if_needed(self, page: Page) -> bool:
        """Detects CAPTCHA and pauses for manual solve."""
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            '.g-recaptcha',
            '.h-captcha',
            '#captcha',
            '[class*="captcha"]',
            '[id*="captcha"]',
            'iframe[title*="challenge"]',
        ]

        for selector in captcha_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    console.print("\n[bold red]🔐 CAPTCHA DETECTED![/]")
                    console.print("[yellow]Please solve the CAPTCHA in the browser window.[/]")
                    Prompt.ask("[bold]Press ENTER after solving the CAPTCHA to continue[/]")
                    time.sleep(1)
                    return True
            except Exception:
                pass
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # NAUKRI RECRUITER CHATBOT / QUESTIONNAIRE HANDLER
    # ─────────────────────────────────────────────────────────────────────────

    def handle_naukri_chatbot(self, page: Page) -> bool:
        """
        Handles the Naukri Recruiter Chatbot drawer / Questionnaire step-by-step.
        Reads bot prompts, checks chips/options or inputs, auto-fills or asks user.
        """
        # Check if chatbot or questionnaire drawer exists
        chatbot_drawer = (
            page.query_selector('.chatbot_drawer') or
            page.query_selector('.chat-drawer') or
            page.query_selector('[class*="chatbot"]') or
            page.query_selector('[class*="chat-container"]') or
            page.query_selector('.layer-content')
        )
        if not chatbot_drawer or not chatbot_drawer.is_visible():
            return False

        console.print("[bold yellow]Naukri:[/] 🤖 Recruiter Chatbot / Questionnaire detected — answering questions...")

        max_interactions = 15
        for step in range(max_interactions):
            human_delay(1500, 2500)

            # Check if chat is finished / success message
            success_el = (
                page.query_selector('div:has-text("applied successfully")') or
                page.query_selector('div:has-text("Application sent")') or
                page.query_selector('.apply-message') or
                page.query_selector('[class*="success"]')
            )
            if success_el and success_el.is_visible():
                console.print("[bold green]Naukri:[/] ✅ Chatbot application completed successfully!")
                return True

            # 1. Look for quick-reply option chips/buttons (e.g. Yes/No, Notice Period options, CTC)
            chips = page.query_selector_all(
                '.chip, button[class*="chip"], div[class*="chip"], '
                '.chatbot-options button, .bot-options button, li[class*="option"]'
            )
            visible_chips = [c for c in chips if c.is_visible()]

            if visible_chips:
                # Read latest bot message text
                bot_msg_el = page.query_selector_all('.msg_bot, .bot-msg, .message_text, [class*="botText"], div[class*="msg"]')
                question_text = bot_msg_el[-1].inner_text().strip() if bot_msg_el else "Question"

                console.print(f"\n[bold cyan]Naukri Bot asks:[/] {question_text}")
                chip_texts = [c.inner_text().strip() for c in visible_chips]

                # Check if we have an answer in memory for this question
                saved_ans = self.memory.get(question_text)
                clicked_chip = False

                if saved_ans:
                    for i, chip_el in enumerate(visible_chips):
                        if saved_ans.lower() in chip_texts[i].lower() or chip_texts[i].lower() in saved_ans.lower():
                            human_move_and_click(page, chip_el)
                            console.print(f"[dim]Auto-selected option:[/] [green]{chip_texts[i]}[/]")
                            clicked_chip = True
                            break

                if not clicked_chip:
                    # Ask user to pick an option or answer
                    console.print("[yellow]Options available:[/]")
                    for idx, opt in enumerate(chip_texts, 1):
                        console.print(f"  [{idx}] {opt}")

                    chosen = Prompt.ask(
                        f"[bold]Select option number (1-{len(chip_texts)}) or type answer[/]",
                        default="1"
                    )

                    # Determine selection
                    selected_chip = None
                    if chosen.isdigit() and 1 <= int(chosen) <= len(chip_texts):
                        selected_chip = visible_chips[int(chosen) - 1]
                        self.memory.data[self.memory._normalize_key(question_text)] = chip_texts[int(chosen) - 1]
                        self.memory._save()
                    else:
                        for i, chip_el in enumerate(visible_chips):
                            if chosen.lower() in chip_texts[i].lower():
                                selected_chip = chip_el
                                self.memory.data[self.memory._normalize_key(question_text)] = chip_texts[i]
                                self.memory._save()
                                break

                    if selected_chip:
                        human_move_and_click(page, selected_chip)
                    elif visible_chips:
                        human_move_and_click(page, visible_chips[0])

                human_delay(1500, 2500)
                continue

            # 2. Look for text input inside chatbot
            chat_input = (
                page.query_selector('.chat-input') or
                page.query_selector('input[placeholder*="type"]') or
                page.query_selector('input[placeholder*="Type"]') or
                page.query_selector('input[placeholder*="answer"]') or
                page.query_selector('input[placeholder*="Enter"]') or
                page.query_selector('textarea[placeholder*="Type"]') or
                page.query_selector('.chatbot-input input') or
                page.query_selector('input[type="text"]')
            )
            if chat_input and chat_input.is_visible():
                bot_msg_el = page.query_selector_all('.msg_bot, .bot-msg, .message_text, [class*="botText"]')
                question_text = bot_msg_el[-1].inner_text().strip() if bot_msg_el else "Question"

                answer = self._resolve_answer(question_text, chat_input)
                if answer:
                    chat_input.click()
                    human_delay(200, 400)
                    chat_input.fill("")
                    for char in answer:
                        chat_input.type(char, delay=random.randint(40, 100))
                    human_delay(300, 600)

                    send_btn = (
                        page.query_selector('button.send-btn') or
                        page.query_selector('button[type="submit"]') or
                        page.query_selector('.send-icon') or
                        page.query_selector('button:has-text("Send")')
                    )
                    if send_btn and send_btn.is_visible():
                        human_move_and_click(page, send_btn)
                    else:
                        page.keyboard.press("Enter")

                human_delay(2000, 3000)
                continue

            # 3. Look for Submit / Done / Apply button in chatbot
            submit_btn = (
                page.query_selector('button:has-text("Submit")') or
                page.query_selector('button:has-text("Apply")') or
                page.query_selector('button:has-text("Save & Apply")')
            )
            if submit_btn and submit_btn.is_visible():
                human_move_and_click(page, submit_btn)
                human_delay(2000, 3000)
                return True

            break

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # EXTERNAL COMPANY SITE / ATS PORTAL HANDLER (Workday, Greenhouse, Lever, etc.)
    # ─────────────────────────────────────────────────────────────────────────

    def handle_external_company_apply(self, page: Page, resume_path: str) -> bool:
        """
        Fills and completes applications on external company career portals
        (Workday, Greenhouse, Lever, SmartRecruiters, Ashby, Taleo, company pages).
        """
        console.print(f"[bold cyan]ATS Form Filler:[/] Processing company application form on [dim]{page.url[:60]}...[/]")
        human_delay(2000, 3500)

        # 1. Click initial "Apply" or "Apply for this job" button if on landing page
        initial_apply_btn = (
            page.query_selector('a:has-text("Apply for this job")') or
            page.query_selector('button:has-text("Apply for this job")') or
            page.query_selector('a:has-text("Apply Now")') or
            page.query_selector('button:has-text("Apply Now")') or
            page.query_selector('[data-qa="btn-apply"]') or
            page.query_selector('#apply_button')
        )
        if initial_apply_btn and initial_apply_btn.is_visible():
            human_move_and_click(page, initial_apply_btn)
            human_delay(1500, 3000)

        # 2. Upload Resume
        if Path(resume_path).exists():
            file_inputs = page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                try:
                    fi.set_input_files(resume_path)
                    console.print(f"[dim]📎 Uploaded resume:[/] [magenta]{Path(resume_path).name}[/]")
                    human_delay(1500, 2500)
                    break
                except Exception:
                    pass

        # 3. Fill form inputs, textareas, and dropdowns
        self.fill_form_fields(page)
        self.handle_checkbox_questions(page)

        # 4. Handle CAPTCHA if presented
        self.wait_for_captcha_if_needed(page)

        # 5. Look for Submit Application button
        submit_btn = (
            page.query_selector('button[type="submit"]') or
            page.query_selector('input[type="submit"]') or
            page.query_selector('button:has-text("Submit Application")') or
            page.query_selector('button:has-text("Submit")') or
            page.query_selector('button:has-text("Apply Now")') or
            page.query_selector('button:has-text("Review Application")') or
            page.query_selector('button[id*="submit"]')
        )

        if submit_btn and submit_btn.is_visible():
            console.print("[bold green]ATS Form Filler:[/] Submitting application...")
            human_move_and_click(page, submit_btn)
            human_delay(3000, 5000)
            return True

        return False
