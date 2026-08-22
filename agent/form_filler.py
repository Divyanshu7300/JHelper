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
from rich.markup import escape

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
                console.print(f"[dim]FormFiller: skipping field — {escape(str(e))}[/]")

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
        Reads bot prompts, matches chips (especially 0 years for any skill experience),
        types into chat inputs, and prevents infinite question looping.
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

        seen_questions: Dict[str, int] = {}
        max_interactions = 18

        for step in range(max_interactions):
            human_delay(1200, 2000)

            # Check if chat is finished / success message
            success_el = (
                page.query_selector('div:has-text("applied successfully")') or
                page.query_selector('div:has-text("Application sent")') or
                page.query_selector('div:has-text("already applied")') or
                page.query_selector('.apply-message') or
                page.query_selector('[class*="success"]')
            )
            if success_el and success_el.is_visible():
                console.print("[bold green]Naukri:[/] ✅ Chatbot application completed successfully!")
                return True

            # Extract latest bot message
            bot_msg_el = page.query_selector_all(
                '.msg_bot, .bot-msg, .message_text, [class*="botText"], div[class*="msg"], .bot-message'
            )
            question_text = bot_msg_el[-1].inner_text().strip() if bot_msg_el else "Question"
            question_clean = re.sub(r"\s+", " ", question_text).strip()

            seen_questions[question_clean] = seen_questions.get(question_clean, 0) + 1
            repeat_count = seen_questions[question_clean]

            # If the same question has repeated 3 times, break or force submit to prevent hanging
            if repeat_count > 3:
                console.print(f"[dim]Naukri Bot: Question repeated {repeat_count} times, advancing...[/]")
                submit_btn = page.query_selector('button:has-text("Submit"), button:has-text("Apply"), button:has-text("Save & Apply")')
                if submit_btn and submit_btn.is_visible():
                    submit_btn.click()
                    human_delay(1500, 2500)
                    return True
                break

            console.print(f"\n[bold cyan]Naukri Bot asks:[/] {question_text}")

            # 1. Look for quick-reply option chips/buttons
            chips = page.query_selector_all(
                '.chip, button[class*="chip"], div[class*="chip"], '
                '.chatbot-options button, .bot-options button, li[class*="option"], '
                '[data-qa="chip"], .quick-reply, span[class*="chip"]'
            )
            visible_chips = [c for c in chips if c.is_visible()]

            # Filter chips to those having readable text
            valid_chips = []
            for c in visible_chips:
                try:
                    txt = c.inner_text().strip()
                    if txt:
                        valid_chips.append((c, txt))
                except Exception:
                    pass

            # Resolve expected answer
            # If question is about experience in ANY skill (Node.js, Python, Next.js, etc.) -> Target is 0
            is_experience_q = any(k in question_clean.lower() for k in [
                "experience", "years of", "how many years", "work exp", "years in", "years with", "how much experience"
            ])

            if is_experience_q:
                answer = "0"
            else:
                answer = self._resolve_answer(question_text) or "0"

            clicked_chip = False

            if valid_chips:
                # Experience matching: look for "0", "Fresher", "Less than 1", "0-1", "0 Year", "0 Years"
                if is_experience_q:
                    exp_zero_markers = ["0", "fresher", "less than 1", "0-1", "0 - 1", "< 1", "0 year", "0 years", "no experience", "nil", "none", "0 to 1"]
                    for chip_el, c_text in valid_chips:
                        c_lower = c_text.lower()
                        if any(marker == c_lower or marker in c_lower for marker in exp_zero_markers):
                            console.print(f"[dim]Auto-selected option:[/] [green]{c_text}[/]")
                            try:
                                chip_el.scroll_into_view_if_needed()
                                human_delay(100, 250)
                                chip_el.click(force=True)
                                chip_el.evaluate("el => el.click()")
                            except Exception:
                                pass
                            clicked_chip = True
                            break

                # General matching for other questions (Yes/No, Immediate, Location, CTC, etc.)
                if not clicked_chip and answer:
                    for chip_el, c_text in valid_chips:
                        if answer.lower() in c_text.lower() or c_text.lower() in answer.lower():
                            console.print(f"[dim]Auto-selected option:[/] [green]{c_text}[/]")
                            try:
                                chip_el.scroll_into_view_if_needed()
                                human_delay(100, 250)
                                chip_el.click(force=True)
                                chip_el.evaluate("el => el.click()")
                            except Exception:
                                pass
                            clicked_chip = True
                            break

                # Fallback: click first positive or first available chip
                if not clicked_chip and valid_chips:
                    for chip_el, c_text in valid_chips:
                        if any(pos in c_text.lower() for pos in ["yes", "immediate", "0", "fresher", "jaipur"]):
                            console.print(f"[dim]Auto-selected option:[/] [green]{c_text}[/]")
                            try:
                                chip_el.scroll_into_view_if_needed()
                                chip_el.click(force=True)
                                chip_el.evaluate("el => el.click()")
                            except Exception:
                                pass
                            clicked_chip = True
                            break

                    if not clicked_chip:
                        chip_el, c_text = valid_chips[0]
                        console.print(f"[dim]Auto-selected option:[/] [green]{c_text}[/]")
                        try:
                            chip_el.scroll_into_view_if_needed()
                            chip_el.click(force=True)
                            chip_el.evaluate("el => el.click()")
                        except Exception:
                            pass
                        clicked_chip = True

                human_delay(1500, 2500)
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
                type_val = "0" if is_experience_q else (str(answer) if answer else "0")
                console.print(f"[dim]Typing into chat:[/] [green]{type_val}[/]")
                try:
                    chat_input.click()
                    human_delay(100, 200)
                    chat_input.fill("")
                    for char in type_val:
                        chat_input.type(char, delay=random.randint(20, 60))
                    human_delay(150, 300)

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
                except Exception:
                    pass

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

    def handle_external_company_apply(self, page: Page, resume_path: str) -> bool:
        """
        Multi-Step ATS Wizard Solver for external company career portals
        (Workday, Greenhouse, Lever, SmartRecruiters, Ashby, Taleo, BambooHR, custom portals).
        Iterates through all wizard steps, uploads resume, fills fields with Profile/Memory/AI,
        handles validation errors, and completes final submission.
        """
        try:
            url_preview = escape(page.url[:65]) if page.url else ""
            console.print(f"[bold cyan]ATS Form Filler:[/] Processing multi-step application on [dim]{url_preview}...[/]")
            human_delay(2000, 3500)

            # Step 0: Click initial "Apply" / "Apply for this job" / "Apply Now" button if on landing page
            initial_apply_btn = (
                page.query_selector('a:has-text("Apply for this job")') or
                page.query_selector('button:has-text("Apply for this job")') or
                page.query_selector('a:has-text("Apply Now")') or
                page.query_selector('button:has-text("Apply Now")') or
                page.query_selector('[data-qa="btn-apply"]') or
                page.query_selector('#apply_button') or
                page.query_selector('button:has-text("Apply")') or
                page.query_selector('a:has-text("Apply")')
            )
            if initial_apply_btn and initial_apply_btn.is_visible():
                try:
                    human_move_and_click(page, initial_apply_btn)
                    human_delay(2000, 3500)
                except Exception:
                    pass

            max_steps = 12
            last_step_sig = ""
            stuck_count = 0

            for step_idx in range(1, max_steps + 1):
                human_delay(1500, 2500)

                # 1. Check for immediate success / confirmation
                success_indicators = [
                    'div:has-text("Application Submitted")',
                    'div:has-text("Application received")',
                    'div:has-text("Thank you for applying")',
                    'div:has-text("Your application was submitted")',
                    'div:has-text("Application Complete")',
                    'div:has-text("We have received your application")',
                    'h1:has-text("Thank you")',
                    'h2:has-text("Thank you")',
                    '[data-qa="msg-success"]',
                    '.application-success',
                    '.success-message'
                ]
                for succ_sel in success_indicators:
                    try:
                        succ_el = page.query_selector(succ_sel)
                        if succ_el and succ_el.is_visible():
                            console.print("[bold green]ATS Form Filler:[/] ✅ Application successfully submitted!")
                            return True
                    except Exception:
                        pass

                console.print(f"[dim]ATS Form Filler:[/] 📄 Processing Wizard Step {step_idx}...")

                # 2. Upload Resume if file inputs exist
                if Path(resume_path).exists():
                    file_inputs = page.query_selector_all('input[type="file"]')
                    for fi in file_inputs:
                        try:
                            fi.set_input_files(resume_path)
                            console.print(f"[dim]📎 Uploaded resume:[/] [magenta]{Path(resume_path).name}[/]")
                            human_delay(1200, 2000)
                            break
                        except Exception:
                            pass

                # 3. Fill all form fields on current step
                self.fill_form_fields(page)
                self.handle_checkbox_questions(page)

                # 4. Handle CAPTCHA if presented
                self.wait_for_captcha_if_needed(page)

                # 5. Look for Final Submit Button
                submit_selectors = [
                    'button[data-automation-id="bottom-navigation-submit-button"]',
                    'button[data-test="submit-button"]',
                    'button[data-qa="btn-submit"]',
                    '#submit_app',
                    '#btn-submit',
                    'button[id*="submit"]',
                    'button:has-text("Submit Application")',
                    'button:has-text("Submit application")',
                    'button:has-text("Submit")',
                    'input[type="submit"][value*="Submit"]',
                    'button:has-text("Finish Application")',
                    'button:has-text("Send Application")'
                ]
                submit_btn = None
                for sel in submit_selectors:
                    try:
                        s_el = page.query_selector(sel)
                        if s_el and s_el.is_visible() and not s_el.is_disabled():
                            submit_btn = s_el
                            break
                    except Exception:
                        pass

                # 6. Look for Next / Continue Step Button
                next_selectors = [
                    'button[data-automation-id="bottom-navigation-next-button"]',
                    'button[data-automation-id="page-navigation-next-button"]',
                    'button[data-test="next-button"]',
                    'button:has-text("Save & Continue")',
                    'button:has-text("Save and Continue")',
                    'button:has-text("Save & continue")',
                    'button:has-text("Next Step")',
                    'button:has-text("Next step")',
                    'button:has-text("Next")',
                    'button:has-text("Continue")',
                    'button:has-text("Proceed")',
                    'button:has-text("Review Application")',
                    'button:has-text("Review")',
                    'button:has-text("Save & Next")',
                    'input[type="button"][value*="Next"]',
                    'input[type="submit"][value*="Next"]',
                    'input[type="button"][value*="Continue"]'
                ]
                next_btn = None
                for sel in next_selectors:
                    try:
                        n_el = page.query_selector(sel)
                        if n_el and n_el.is_visible() and not n_el.is_disabled():
                            next_btn = n_el
                            break
                    except Exception:
                        pass

                # Priority 1: If Final Submit Button is present and we're not on intermediate step
                if submit_btn and (not next_btn or "submit" in (submit_btn.inner_text() or "").lower()):
                    console.print("[bold green]ATS Form Filler:[/] Submitting application...")
                    try:
                        human_move_and_click(page, submit_btn)
                        human_delay(3000, 5000)
                    except Exception:
                        try:
                            submit_btn.click(force=True)
                            human_delay(3000, 5000)
                        except Exception:
                            pass

                    # Check post-submit confirmation
                    for succ_sel in success_indicators:
                        try:
                            succ_el = page.query_selector(succ_sel)
                            if succ_el and succ_el.is_visible():
                                console.print("[bold green]ATS Form Filler:[/] ✅ Application successfully submitted!")
                                return True
                        except Exception:
                            pass
                    return True

                # Priority 2: Click Next / Continue button to advance to next wizard step
                if next_btn:
                    btn_name = escape(next_btn.inner_text().strip()) if next_btn.inner_text() else "Next"
                    console.print(f"[dim]ATS Form Filler:[/] ➡️ Advancing to next step ({btn_name})...")
                    try:
                        human_move_and_click(page, next_btn)
                        human_delay(2000, 3500)
                    except Exception:
                        try:
                            next_btn.click(force=True)
                            human_delay(2000, 3500)
                        except Exception:
                            pass

                    # Check if stuck on same step (e.g. required field missing)
                    current_sig = page.url
                    if current_sig == last_step_sig:
                        stuck_count += 1
                        if stuck_count >= 2:
                            console.print("[yellow]ATS Form Filler:[/] Required field missing — auto-resolving empty inputs...[/]")
                            empty_inputs = page.query_selector_all('input[required], [aria-required="true"]')
                            for ei in empty_inputs:
                                try:
                                    if ei.is_visible() and not ei.input_value():
                                        lbl = self._get_label(page, ei)
                                        val = self._resolve_answer(lbl or "field", ei) or "0"
                                        self._fill_field(ei, str(val))
                                except Exception:
                                    pass
                    else:
                        stuck_count = 0

                    last_step_sig = current_sig
                    continue

                # If neither submit nor next button was found
                console.print("[dim]ATS Form Filler:[/] Form processing complete.[/]")
                break

            return True

        except Exception as e:
            console.print(f"[dim]ATS Form Filler: error on portal — {escape(str(e))}[/]")
            return False
