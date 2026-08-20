# 🤖 JHelp — Automated Job Application Agent

Autonomous job application assistant for **LinkedIn**, **Indeed**, and **Naukri**.
Automatically routes the right resume based on job role keywords, bypasses bot detection with human-like interactions, solves recruiter questionnaires with a persistent memory engine, and tracks all applications in a local SQLite database.

---

## 🎯 Features

- **Multi-Platform Automation**: Supports LinkedIn Easy Apply, Indeed Apply, Naukri Direct Apply, Naukri Recruiter Chatbot, and external company ATS portals (Workday, Greenhouse, Lever, etc.).
- **Smart Resume Routing**: Maps incoming job roles to 3 targeted PDF resumes (`resume_backend.pdf`, `resume_aiml.pdf`, `resume_dsda.pdf`).
- **Persistent Q&A Memory**: Remembers custom application answers (e.g. CTC, notice period, graduation year, relocation) in `memory.json` so you never have to re-type them.
- **Anti-Bot & Stealth Engine**: Removes `navigator.webdriver`, spoofs Chrome runtime & WebGL fingerprints, uses human mouse trajectories, and supports one-time session caching.
- **Strict Relevance & Paid Filters**: Automatically skips unpaid/free internships, non-tech positions (CA, Articleship, Sales, HR), and senior/lead positions for 0-1 YOE candidates.
- **Local Application Tracking**: Stores application logs in `applications.db` (SQLite) with one-click CSV export.

---

## 📋 Setup & Installation

### 1. Clone & Install Dependencies
```bash
git clone <your-repo-url>
cd JHelp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials in `.env`:
```env
LINKEDIN_EMAIL=your_email@example.com
LINKEDIN_PASSWORD=your_password

NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password
```

### 3. Add Your Resumes
Place your PDF resumes inside the `resumes/` folder:
```
resumes/
  resume_backend.pdf
  resume_aiml.pdf
  resume_dsda.pdf
```

### 4. One-Time Session Setup (Recommended for 100% Bot Bypass)
Run session setup once for each platform to authenticate in a real browser and cache session cookies:
```bash
# Indeed (Google OAuth / OTP)
python main.py setup-session --platform indeed

# LinkedIn (Skip 2FA on future runs)
python main.py setup-session --platform linkedin

# Naukri
python main.py setup-session --platform naukri
```

---

## 🚀 Usage

### Dry Run (Test without submitting applications)
```bash
python main.py --dry-run
```

### Run All Platforms
```bash
python main.py
```

### Run a Specific Platform
```bash
python main.py --platform linkedin
python main.py --platform naukri
python main.py --platform indeed
```

### Manage Saved Memory / Answers
```bash
# View all remembered answers
python main.py memory

# Delete a specific saved answer
python main.py forget "What is your notice period?"
```

### View Application Stats & Export
```bash
# View daily summary
python main.py stats

# Export applications log to CSV
python main.py export --output my_applications.csv
```

---

## 🔒 Security & Privacy

- All sensitive files (`.env`, `sessions/`, `memory.json`, `resumes/*.pdf`, `applications.db`) are strictly ignored by `.gitignore`.
- No credentials or personal session cookies are ever uploaded to Git.
- Passwords are read strictly from environment variables or local cookie storage.

---

## 📄 License
MIT License
