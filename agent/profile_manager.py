"""
agent/profile_manager.py
Permanent user profile manager.
Provides instant, deterministic resolution for all standard form fields
from profile.json so the user is never asked for standard personal/resume data twice.
"""

from typing import Optional, Dict, Any
import json
import re
from pathlib import Path
from rich.console import Console

console = Console()

PROFILE_FILE = "profile.json"


class ProfileManager:
    def __init__(self, profile_path: str = PROFILE_FILE):
        self.profile_path = Path(profile_path)
        self.data: dict = self._load()

    def _load(self) -> dict:
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def get_raw_profile(self) -> dict:
        return self.data

    def match_field(self, raw_label: str) -> Optional[str]:
        """
        Takes any raw field label (e.g. 'Enter your first name *', 'Notice Period (in days)', 'Location*')
        and maps it to the exact value from the profile.
        Returns the resolved string value or None.
        """
        if not raw_label:
            return None

        # Clean label: lowercase, remove asterisks, colons, brackets, and extra spaces
        label = raw_label.lower().strip()
        cleaned = re.sub(r"[\*\:\(\)\[\]\{\}\-\_\,\.\?\/]", " ", label)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Ignore search bars / utility inputs
        ignored_patterns = [
            r"^search", r"search by", r"add new skill", r"filter",
            r"keyword", r"search jobs", r"find candidates", r"nav search"
        ]
        for ip in ignored_patterns:
            if re.search(ip, cleaned):
                return None

        # 1. Names
        if re.search(r"\b(first\s*name|given\s*name|fname)\b", cleaned):
            return self.data.get("personal", {}).get("first_name", "Divyanshu")
        if re.search(r"\b(last\s*name|surname|family\s*name|lname)\b", cleaned):
            return self.data.get("personal", {}).get("last_name", "Nagar")
        if re.search(r"\b(middle\s*name)\b", cleaned):
            return ""
        if re.search(r"\b(full\s*name|your\s*name|candidate\s*name|name)\b", cleaned):
            return self.data.get("personal", {}).get("full_name", "Divyanshu Nagar")

        # 2. Email & Phone
        if re.search(r"\b(email|email\s*address|e\s*mail|email\s*id)\b", cleaned):
            return self.data.get("personal", {}).get("email", "divyanshunagar0000@gmail.com")
        if re.search(r"\b(phone|mobile|contact\s*number|phone\s*number|cell)\b", cleaned):
            return self.data.get("personal", {}).get("phone", "7300257595")

        # 3. Location / City / State / Country
        if re.search(r"\b(city|current\s*city|current\s*location|location|residence|where\s*are\s*you\s*located|home\s*location)\b", cleaned):
            return self.data.get("location", {}).get("city", "Jaipur")
        if re.search(r"\b(state|province)\b", cleaned):
            return self.data.get("location", {}).get("state", "Rajasthan")
        if re.search(r"\b(country|nationality)\b", cleaned):
            return self.data.get("location", {}).get("country", "India")
        if re.search(r"\b(relocat|willing\s*to\s*relocate|open\s*to\s*relocate)\b", cleaned):
            return self.data.get("location", {}).get("willing_to_relocate", "Yes")

        # 4. Links
        if re.search(r"\b(linkedin|linkedin\s*url|linkedin\s*profile|linkedin\s*link)\b", cleaned):
            return self.data.get("links", {}).get("linkedin", "https://linkedin.com/in/divyanshu0000")
        if re.search(r"\b(github|github\s*url|github\s*profile|github\s*link)\b", cleaned):
            return self.data.get("links", {}).get("github", "https://github.com/Divyanshu7300")
        if re.search(r"\b(portfolio|website|portfolio\s*url|personal\s*website|projects\s*link)\b", cleaned):
            return self.data.get("links", {}).get("portfolio", "https://portfolio-lime-eta-60.vercel.app/")

        # 5. Education
        if re.search(r"\b(college|university|institute|school|alma\s*mater)\b", cleaned):
            return self.data.get("education", {}).get("college", "Manipal University Jaipur")
        if re.search(r"\b(degree|highest\s*degree|qualification|highest\s*education|educational\s*qualification)\b", cleaned):
            return self.data.get("education", {}).get("highest_degree", "Master of Computer Applications (MCA)")
        if re.search(r"\b(branch|stream|field\s*of\s*study|specialization|major)\b", cleaned):
            return self.data.get("education", {}).get("branch", "Computer Science & Applications")
        if re.search(r"\b(graduation\s*year|passing\s*year|year\s*of\s*passing|year\s*of\s*graduation|completion\s*year)\b", cleaned):
            return self.data.get("education", {}).get("graduation_year", "2026")
        if re.search(r"\b(cgpa|gpa|percentage|marks|grade)\b", cleaned):
            return self.data.get("education", {}).get("cgpa", "8.5")

        # 6. Experience (Always 0 / Fresher for all general and skill-specific experience questions)
        if re.search(r"\b(experience|how\s*many\s*years|years?\s*of\s*experience|work\s*experience|relevant\s*experience|total\s*experience|experience\s*in\s*years)\b", cleaned):
            return "0"
        if re.search(r"\b(years?)\b.*\b(in|with|of|on)\b", cleaned):
            return "0"
        if re.search(r"\b(career\s*break|gap\s*in\s*education|employment\s*gap)\b", cleaned):
            return self.data.get("experience", {}).get("career_break", "No")
        if re.search(r"\b(current\s*company|current\s*employer|present\s*company)\b", cleaned):
            return self.data.get("experience", {}).get("current_company", "None (Student / Fresher)")
        if re.search(r"\b(current\s*designation|current\s*title|current\s*role|designation)\b", cleaned):
            return self.data.get("experience", {}).get("current_designation", "Student / Fresher Developer")

        # 7. Compensation & Notice Period
        if re.search(r"\b(current\s*ctc|current\s*salary|current\s*compensation|current\s*package)\b", cleaned):
            return self.data.get("compensation_and_notice", {}).get("current_ctc", "0")
        if re.search(r"\b(expected\s*ctc|expected\s*salary|desired\s*salary|salary\s*expectation|expected\s*compensation|expected\s*package)\b", cleaned):
            return self.data.get("compensation_and_notice", {}).get("expected_ctc", "6 LPA")
        if re.search(r"\b(notice\s*period|notice|joining\s*time|how\s*soon\s*can\s*you\s*join|availability\s*to\s*join|how\s*many\s*days\s*notice)\b", cleaned):
            return self.data.get("compensation_and_notice", {}).get("notice_period", "0 days")
        if re.search(r"\b(when\s*can\s*you\s*start|start\s*date|earliest\s*start\s*date|availability|available\s*from)\b", cleaned):
            return self.data.get("compensation_and_notice", {}).get("availability", "Immediately")
        if re.search(r"\b(full\s*time|internship\s*duration|duration|6\s*months)\b", cleaned):
            return "Yes"

        # 8. Work Authorization / Visa
        if re.search(r"\b(authorized\s*to\s*work|legally\s*authorized|work\s*authorization|eligible\s*to\s*work)\b", cleaned):
            return self.data.get("work_authorization", {}).get("legally_authorized", "Yes")
        if re.search(r"\b(sponsorship|require\s*sponsorship|visa\s*sponsorship|require\s*visa)\b", cleaned):
            return self.data.get("work_authorization", {}).get("requires_sponsorship", "No")

        # 9. Gender / Personal
        if re.search(r"\b(gender|sex)\b", cleaned):
            return self.data.get("personal", {}).get("gender", "Male")
        if re.search(r"\b(date\s*of\s*birth|dob|birth\s*date)\b", cleaned):
            return self.data.get("personal", {}).get("date_of_birth", "01/01/2002")

        return None
