"""
agent/form_filler.py
Smart form filler — handles standard forms, multi-step ATS modals (Workday, Greenhouse,
Lever, SmartRecruiters, Ashby), Naukri recruiter chatbots, and company career pages.
Resolves answers via permanent profile.json, memory.json, and AIAnswerer.
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
from agent.profile_manager import ProfileManager
from agent.ai_answerer import AIAnswerer
from agent.stealth import human_delay, human_type, human_move_and_click

console = Console()

# Input field labels / placeholders that belong to page search bars or navigation — MUST BE IGNORED
IGNORED_FIELD_PATTERNS = [
    r"search\s*by\s*keyword",
    r"search\s*by\s*location",
    r"search\s*jobs",
    r"add\s*new\s*skill",
    r"add\s*skill",
    r"find\s*jobs",
    r"filter\s*by",
    r"keyword",
    r"nav\s*search",
    r"site\s*search",
    r"newsletter",
    r"subscribe",
    r"search\s*candidate",
    r"search\s*companies",
    r"enter\s*keyword",
    r"location\s*search"
]


class FormFiller:
    def __init__(self, memory: AnswerMemory):
        self.memory = memory
        self.profile_mgr = ProfileManager()
        self.ai_answerer = AIAnswerer(self.profile_mgr)

    def is_ignored_field(self, label: str, placeholder: str, name: str) -> bool:
        """Check if an input field is a search bar or navigation filter."""
        combined = f"{label} {placeholder} {name}".lower()
        for pat in IGNORED_FIELD_PATTERNS:
            if re.search(pat, combined):
                return True
        return False

    def fill_form_fields(self, page: Page) -> int:
        """
        Scans all visible input/select/textarea fields on the page.
        Resolves answers via profile -> memory -> AI answerer -> prompt user.
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

                # Skip search bars / navigation inputs
                placeholder = field.get_attribute("placeholder") or ""
                name = field.get_attribute("name") or ""
                label = self._get_label(page, field)

                if self.is_ignored_field(label, placeholder, name):
                    continue

                # Skip already filled fields
                current_value = self._get_field_value(field)
                if current_value and current_value.strip():
                    continue

                if not label and placeholder:
                    label = placeholder
                if not label:
                    continue

                answer = self._resolve_answer(label, field)
                if answer:
                    self._fill_field(field, str(answer))
                    filled += 1
                    human_delay(150, 300)

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

            # 2. associated <label for="...">
            field_id = field.get_attribute("id")
            if field_id:
                label_el = page.query_selector(f'label[for="{field_id}"]')
                if label_el and label_el.inner_text().strip():
                    return label_el.inner_text().strip()

            # 3. placeholder
            placeholder = field.get_attribute("placeholder")
            if placeholder and len(placeholder.strip()) > 1:
                return placeholder.strip()

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
        Multi-tier answer resolution pipeline:
        1. ProfileManager (Instant canonical profile lookup from profile.json)
        2. AnswerMemory (memory.json normalized lookup)
        3. AIAnswerer (Contextual AI answer for open-ended questions)
        4. Interactive prompt to user (Permanent save)
        """
        # Tier 1: Profile Manager
        profile_ans = self.profile_mgr.match_field(label)
        if profile_ans is not None:
            return str(profile_ans)

        # Tier 2: Answer Memory
        mem_ans = self.memory.get(label)
        if mem_ans:
            return str(mem_ans)

        # Determine expected type
        field_type = "text"
        if field:
            try:
                ft = field.get_attribute("type") or ""
                if ft in ("number", "tel"):
                    field_type = "number"
            except Exception:
                pass

        # Tier 3: AI Answerer / Fallback
        console.print(f"[dim]🤖 Resolving via AI/Memory:[/] [cyan]{label}[/]")
        answer = self.memory.resolve_or_ask(label, field_type, auto_ai=True)
        return answer if answer else None

    def _fill_field(self, field: ElementHandle, value: str):
        """Fill an input/select/textarea field using human typing physics."""
        try:
            tag = field.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                try:
                    # Select option matching label
                    field.select_option(label=value)
                    return
                except Exception:
                    pass

                try:
                    # Select option matching value
                    field.select_option(value=value)
                    return
                except Exception:
                    pass

                # Try selecting first non-empty option
                try:
                    field.evaluate("""
                        el => {
                            for (let i = 0; i < el.options.length; i++) {
                                if (el.options[i].text.toLowerCase().includes('yes') || 
                                    el.options[i].text.toLowerCase().includes('immediate') || 
                                    el.options[i].value) {
                                    el.selectedIndex = i;
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    break;
                                }
                            }
                        }
                    """)
                    return
                except Exception:
                    pass
                return

            field.scroll_into_view_if_needed()
            field.click()
            time.sleep(random.uniform(0.08, 0.18))
            field.fill("")
            time.sleep(random.uniform(0.04, 0.10))

            # Fast human typing
            for char in value:
                delay = random.randint(25, 75)
                field.type(char, delay=delay)
            time.sleep(random.uniform(0.08, 0.20))

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

                # Check if group already has a checked radio
                is_checked = page.evaluate(f'document.querySelector(\'input[type="radio"][name="{name}"]:checked\') !== null')
                if not is_checked:
                    # Look for positive options like "Yes", "Immediate", "0", "Fresher", "Authorized"
                    group_radios = page.query_selector_all(f'input[type="radio"][name="{name}"]')
                    clicked = False
                    for gr in group_radios:
                        label_text = gr.evaluate("""
                            el => {
                                const lbl = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                                return lbl ? lbl.innerText.trim().toLowerCase() : (el.value || '').toLowerCase();
                            }
                        """)
                        if any(pos in label_text for pos in ["yes", "immediate", "fresher", "0", "agree", "authorized", "100", "full time"]):
                            gr.click()
                            clicked = True
                            break
                    if not clicked and group_radios:
                        group_radios[0].click()

            # Handle required checkboxes (Terms & Conditions, Privacy Policy, Confirmation)
            checkboxes = page.query_selector_all('input[type="checkbox"]')
            for cb in checkboxes:
                try:
                    if cb.is_visible() and not cb.is_checked():
                        cb_label = cb.evaluate("""
                            el => {
                                const lbl = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                                return lbl ? lbl.innerText.trim().toLowerCase() : '';
                            }
                        """)
                        if any(k in cb_label for k in ["agree", "terms", "consent", "authorize", "confirm", "acknowledge", "certify"]):
                            cb.click()
                except Exception:
                    pass

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
        Reads bot prompts, checks chips/options or inputs, auto-fills with profile/memory/AI.
        """
        chatbot_drawer = (
            page.query_selector('.chatbot_drawer') or
            page.query_selector('.chat-drawer') or
            page.query_selector('[class*="chatbot"]') or
            page.query_selector('[class*="chat-container"]') or
            page.query_selector('.layer-content')
        )
        if not chatbot_drawer or not chatbot_drawer.is_visible():
            return False

        console.print("[bold yellow]Naukri:[/] 🤖 Recruiter Chatbot detected — auto-answering questions...")

        max_interactions = 15
        for step in range(max_interactions):
            human_delay(1200, 2000)

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

            # 1. Quick-reply option chips (e.g. Yes/No, Notice Period, CTC, Experience)
            chips = page.query_selector_all(
                '.chip, button[class*="chip"], div[class*="chip"], '
                '.chatbot-options button, .bot-options button, li[class*="option"]'
            )
            visible_chips = [c for c in chips if c.is_visible()]

            if visible_chips:
                bot_msg_el = page.query_selector_all('.msg_bot, .bot-msg, .message_text, [class*="botText"], div[class*="msg"]')
                question_text = bot_msg_el[-1].inner_text().strip() if bot_msg_el else "Question"

                chip_texts = [c.inner_text().strip() for c in visible_chips]
                console.print(f"\n[bold cyan]Naukri Bot asks:[/] {question_text}")

                # Resolve answer via Profile / Memory / AI
                answer = self._resolve_answer(question_text)
                clicked_chip = False

                if answer:
                    for i, chip_el in enumerate(visible_chips):
                        if answer.lower() in chip_texts[i].lower() or chip_texts[i].lower() in answer.lower():
                            human_move_and_click(page, chip_el)
                            console.print(f"[dim]Auto-selected option:[/] [green]{chip_texts[i]}[/]")
                            clicked_chip = True
                            break

                if not clicked_chip:
                    # Select first logical positive chip or first option
                    for i, chip_el in enumerate(visible_chips):
                        if any(pos in chip_texts[i].lower() for pos in ["yes", "immediate", "0", "fresher", "jaipur"]):
                            human_move_and_click(page, chip_el)
                            clicked_chip = True
                            break

                    if not clicked_chip and visible_chips:
                        human_move_and_click(page, visible_chips[0])

                human_delay(1200, 2000)
                continue

            # 2. Text input inside chatbot
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
                    human_delay(150, 300)
                    chat_input.fill("")
                    for char in str(answer):
                        chat_input.type(char, delay=random.randint(25, 75))
                    human_delay(200, 400)

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

                human_delay(1500, 2500)
                continue

            # 3. Submit / Done / Apply button in chatbot
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
        console.print(f"[bold cyan]ATS Form Filler:[/] Auto-filling company portal on [dim]{page.url[:60]}...[/]")
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
