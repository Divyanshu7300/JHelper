"""
agent/resume_router.py
Evaluates job relevance, filters out unpaid/free internships, senior roles,
and non-tech positions (CA, Articleship, Sales, BPO, etc.).
Routes valid jobs to the matching resume PDF.
"""

from typing import Tuple, List, Dict, Optional
import re
import yaml
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


class ResumeRouter:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self.roles = self.config.get("roles", [])
        self.paid_only = self.config.get("paid_only", True)
        self.require_tech_domain = self.config.get("require_tech_domain_match", True)
        self.exclude_keywords = [
            k.lower() for k in self.config.get("exclude_keywords", [])
        ]
        self.resume_dir = Path("resumes")

    def evaluate_job(self, job_title: str, jd_text: str = "") -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Evaluates a job listing:
        1. Checks for unpaid/free internship markers
        2. Checks for excluded keywords (CA, Articleship, Sales, Senior, etc.)
        3. Checks for positive match in target tech domains (Backend, AI/ML, DS/DA)

        Returns: (is_valid, role_name, resume_path, reason)
        """
        combined_text = f"{job_title} {jd_text}".lower()
        title_lower = job_title.lower()

        # 1. Unpaid / Free check (Regex word boundaries — allows "Not Disclosed", "Undisclosed", "Competitive", etc.)
        if self.paid_only:
            unpaid_patterns = [
                r"\bunpaid\b",
                r"\bno\s*stipend\b",
                r"\bwithout\s*stipend\b",
                r"\bzero\s*stipend\b",
                r"\b0\s*stipend\b",
                r"\bnon[\s\-]paid\b",
                r"\bfree\s*internship\b",
                r"\bstipend\s*[\:\-]\s*(unpaid|nil|none|0|na|n\/a|no|zero)\b",
                r"\bexpenses\s*only\b",
                r"\bcertificate\s*(only|and\s*lor\s*only)\b",
                r"\bonly\s*certificate\b",
                r"\bno\s*(salary|pay|compensation|remuneration)\b",
                r"\bvolunteer\b",
                r"\bcommission\s*only\b",
                r"\bperformance\s*based\s*only\b",
                r"\b0\s*-\s*0\s*(pa|lacs|k|inr|per\s*month)\b",
                r"\b₹\s*0\b",
                r"\b0\s*inr\b",
                r"\b0\s*lpa\b",
                r"\b0\s*per\s*month\b"
            ]
            for pat in unpaid_patterns:
                if re.search(pat, combined_text):
                    return False, None, None, f"Unpaid internship detected"

        # 2. Excluded keywords check (in title or prominent in JD)
        for kw in self.exclude_keywords:
            if kw in title_lower:
                return False, None, None, f"Excluded keyword in title ('{kw}')"

        # 3. Match against tech roles
        best_role = None
        best_resume = None
        highest_score = 0

        for role in self.roles:
            score = 0
            for keyword in role.get("match_keywords", []):
                kw_lower = keyword.lower()
                # Higher weight if keyword is in title
                if kw_lower in title_lower:
                    score += 3
                # Normal weight if keyword is in JD
                elif jd_text and kw_lower in jd_text.lower():
                    score += 1

            if score > highest_score:
                highest_score = score
                best_role = role["name"]
                best_resume = str(self.resume_dir / role["resume"])

        if highest_score > 0 and best_role and best_resume:
            return True, best_role, best_resume, "Matched tech profile"

        # If strict tech domain matching is enabled and no tech keywords matched
        if self.require_tech_domain:
            return False, None, None, "Irrelevant role (Does not match Backend, AI/ML, or Data domain)"

        # Fallback if allowed
        fallback = self.config.get("fallback_resume", "resume_backend.pdf")
        return True, "Fallback", str(self.resume_dir / fallback), "Fallback applied"

    def should_skip_title(self, job_title: str) -> bool:
        """Quick title check for negative keywords."""
        title_lower = job_title.lower()
        for kw in self.exclude_keywords:
            if kw in title_lower:
                return True
        return False

    def route(self, job_title: str, jd_text: str = "") -> Tuple[str, str]:
        """Convenience route method."""
        is_valid, role, resume, _ = self.evaluate_job(job_title, jd_text)
        if is_valid and role and resume:
            return role, resume
        fallback = self.config.get("fallback_resume", "resume_backend.pdf")
        return "Backend Developer", str(self.resume_dir / fallback)

    def get_search_keywords(self) -> List[Dict]:
        """
        Returns list of {role_name, keyword, resume} dicts
        for all search terms across all roles.
        """
        searches = []
        for role in self.roles:
            for keyword in role.get("keywords", []):
                searches.append({
                    "role_name": role["name"],
                    "keyword": keyword,
                    "resume": str(self.resume_dir / role["resume"]),
                })
        return searches
