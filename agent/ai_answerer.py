"""
agent/ai_answerer.py
AI-Powered Smart Answer Generator.
Handles twisted, open-ended, and complex recruiter questions using Google Gemini API
with a built-in offline smart heuristic fallback.
"""

from typing import Optional, Dict
import os
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from rich.console import Console

from agent.profile_manager import ProfileManager

console = Console()


class AIAnswerer:
    def __init__(self, profile_manager: Optional[ProfileManager] = None):
        self.profile_manager = profile_manager or ProfileManager()
        self.profile = self.profile_manager.get_raw_profile()
        self.api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

    def answer_question(self, question: str, field_type: str = "text") -> str:
        """
        Answers any recruiter or application question using AI or smart heuristics.
        """
        # If API key is available, try Gemini
        if self.api_key:
            try:
                gemini_ans = self._call_gemini(question, field_type)
                if gemini_ans and len(gemini_ans.strip()) > 0:
                    console.print(f"[dim]✨ AI Generated Answer:[/] [green]{gemini_ans}[/]")
                    return gemini_ans.strip()
            except Exception as e:
                console.print(f"[dim]Gemini API fallback to offline AI engine: {e}[/]")

        # Built-in Smart Heuristic AI Engine
        return self._heuristic_ai_answer(question, field_type)

    def _call_gemini(self, question: str, field_type: str) -> Optional[str]:
        """Calls Google Gemini REST API using native urllib (0 external dependencies)."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"

        system_instruction = (
            f"You are an AI assistant answering job application form questions on behalf of candidate {self.profile.get('personal', {}).get('full_name', 'Divyanshu Nagar')}.\n"
            f"Candidate Profile: {json.dumps(self.profile)}\n"
            f"Instructions:\n"
            f"1. Answer the question concisely, professionally, and truthfully based on the candidate's background (MCA student at Manipal University Jaipur, skilled in Python, FastAPI, Node.js, PyTorch, GenAI/RAG, 0 YOE Fresher looking for Intern/Junior roles).\n"
            f"2. Keep the answer brief (1-3 sentences maximum). If the question is yes/no or a number, return just that.\n"
            f"3. Do not include markdown formatting, quotes, or conversational filler like 'Here is your answer:'. Return only the plain answer text."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\nQuestion: {question}\nExpected Type: {field_type}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 150
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip().strip('"').strip("'")

    def _heuristic_ai_answer(self, question: str, field_type: str = "text") -> str:
        """
        Smart Contextual Heuristic AI:
        Recognizes question intents and crafts high-quality professional responses.
        """
        # 1. Experience in ANY skill or general experience (Always 0 for fresher)
        if any(k in q_lower for k in ["experience", "years of", "how many years", "how much experience", "work exp", "years in", "years with"]):
            return "0"

        # 2. Why should we hire you / Why join us / About yourself
        if any(k in q_lower for k in ["why should we hire you", "why do you want to join", "why this role", "tell us about yourself", "about yourself", "cover letter"]):
            return (
                "I am a passionate software and AI engineer pursuing my MCA at Manipal University Jaipur. "
                "I have strong hands-on experience building backend APIs (Python, FastAPI, Node.js) and ML models (PyTorch, YOLOv8, GenAI). "
                "I am eager to contribute fresh energy, strong problem-solving skills, and rapid learning to your team."
            )

        # 2. Technical Strengths & Skills
        if any(k in q_lower for k in ["core strength", "strengths", "skills", "technologies you know", "tech stack"]):
            return "My core strengths include Python, FastAPI, Node.js, REST API design, PyTorch, SQL databases (PostgreSQL/MongoDB), and Git version control."

        # 3. Project / Challenging problem solved
        if any(k in q_lower for k in ["challenging project", "difficult problem", "project you are proud of", "recent project"]):
            return (
                "I built an end-to-end full-stack and AI project featuring modular FastAPI architecture, "
                "JWT authentication, and deep learning computer vision pipelines with robust error handling and deployment."
            )

        # 4. Experience with Python / Backend
        if "python" in q_lower or "backend" in q_lower or "api" in q_lower:
            return "I have extensive project experience in Python and Node.js building RESTful APIs, async workflows with FastAPI, and database integrations."

        # 5. Experience with AI / ML / Deep Learning
        if any(k in q_lower for k in ["machine learning", "deep learning", "ai", "pytorch", "genai", "rag", "yolo"]):
            return "I have hands-on experience implementing computer vision (YOLOv8), RAG pipelines, prompt engineering, and PyTorch deep learning models."

        # 6. Availability & Full-time commitment
        if any(k in q_lower for k in ["immediate", "start date", "can you start", "available", "full time", "internship"]):
            return "Yes, I am available immediately and ready to commit to a full-time role or 6-month internship."

        # 7. Relocation & Work mode
        if any(k in q_lower for k in ["relocate", "remote", "hybrid", "in-office", "work from office"]):
            return "Yes, I am open and willing to relocate as well as work in remote, hybrid, or in-office setups."

        # 8. Rate yourself / Skill rating (1-5 or 1-10)
        if any(k in q_lower for k in ["rate yourself", "rating", "scale of 1", "out of 5", "out of 10"]):
            if "10" in q_lower:
                return "8"
            return "4"

        # 9. Generic Yes/No questions
        if field_type == "yesno" or any(q_lower.startswith(w) for w in ["are you", "do you", "can you", "will you", "is your", "have you"]):
            if "criminal" in q_lower or "disciplinary" in q_lower or "sponsorship" in q_lower or "break" in q_lower:
                return "No"
            return "Yes"

        # Default smart response
        return "Yes, I am fully prepared and enthusiastic to take on this responsibility with my technical skills and dedication."
