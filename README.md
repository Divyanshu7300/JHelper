# 🤖 JHelp — Automated Job Application Agent

Autonomous job application assistant for **LinkedIn**, **Indeed**, and **Naukri**.
Automatically routes the right resume based on job role keywords, bypasses bot detection with human-like interactions, solves recruiter questionnaires with a persistent memory engine, supports multi-page company ATS portals, and allows **100% remote operation via Telegram**!

---

## 🎯 Features

- **📱 Remote Operation via Telegram**: Control and trigger the agent from anywhere via Telegram chat! Receive live application notifications and answer custom form questions directly from your phone.
- **Multi-Platform Automation**: Supports LinkedIn Easy Apply, Indeed Apply, Naukri Direct Apply, Naukri Recruiter Chatbot, and multi-step external company ATS portals (Workday, Greenhouse, Lever, SmartRecruiters, Ashby).
- **Smart Resume Routing**: Maps incoming job roles to 3 targeted PDF resumes (`resume_backend.pdf`, `resume_aiml.pdf`, `resume_dsda.pdf`).
- **Persistent Profile & Q&A Memory**: Instant field resolution via `profile.json` & `memory.json` so you never type personal info twice.
- **AI-Powered Form Solver**: Integrates Google Gemini & Smart Heuristic AI to answer open-ended recruiter questions intelligently.
- **Anti-Bot & Stealth Engine**: Removes `navigator.webdriver`, spoofs Chrome runtime & WebGL fingerprints, uses human mouse trajectories, and supports one-time session caching.
- **Strict Relevance & Paid Filters**: Automatically skips unpaid/free internships, non-tech positions (CA, Articleship, Sales, HR), and senior/lead positions for 0-1 YOE candidates.
- **Local Application Tracking**: Stores application logs in `applications.db` (SQLite) with one-click CSV export.

---

## 📱 Telegram Remote Setup (Operate From Your Phone)

You can operate JHelp completely from your phone while away from your computer:

### 1. Create a Telegram Bot (Takes 1 minute)
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow the instructions to get your **Bot Token**.
3. Add your credentials to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=123456789
   ```
   *(If you don't know your `CHAT_ID`, just leave it blank and send `/start` to your bot — it will auto-bind!)*

### 2. Start the Telegram Daemon
```bash
python main.py telegram
```
Now you will see interactive buttons on your phone in Telegram:
- `🚀 Apply All` — Runs all platforms
- `💼 Naukri` — Runs Naukri automation
- `👔 LinkedIn` — Runs LinkedIn automation
- `🔍 Indeed` — Runs Indeed automation
- `📊 Stats` — Shows today's application count
- `📋 Memory` — Shows saved answers
- `🧪 Dry Run` — Test simulation mode
- `🛑 Stop` — Stops running agent

*(If an unknown question appears on a job site, the bot will text you on Telegram — just reply with your answer and it will continue automatically!)*

---

## 📋 Setup & Installation

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Divyanshu7300/JHelper.git
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

### Run via Terminal
```bash
# Dry run first — simulate without submitting
python main.py --dry-run

# Run all platforms
python main.py

# Run only Naukri / LinkedIn / Indeed
python main.py --platform naukri
python main.py --platform linkedin
python main.py --platform indeed
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

- All sensitive files (`.env`, `sessions/`, `memory.json`, `profile.json`, `resumes/*.pdf`, `applications.db`) are strictly ignored by `.gitignore`.
- No credentials or personal session cookies are ever uploaded to Git.
- Passwords are read strictly from environment variables or local cookie storage.

---

## 📄 License
MIT License
