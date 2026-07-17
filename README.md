# MattouBot: Dual-System AI Assistant & Multi-Agent Pipeline

This repository contains the source code, architecture, and deployment configurations for a comprehensive, dual-system personal AI assistant. The ecosystem integrates a continuous interactive chatbot with an automated, scheduled multi-agent swarm to handle daily task management, telemetry analysis, global financial research, media curation, and automated briefings.

---

## 💪 Core Capabilities

MattouBot is designed to feel like a real assistant rather than a rigid command-line tool. 
* **Natural Language Understanding (NLU):** No need to rely strictly on `/commands`. You can speak naturally (e.g., *"ajoute du lait à la liste"*, *"what's the weather in London in 2 days?"*, or *"give me a top 3 sci-fi movie list"*), and the bot's NLU router will parse your intent and execute the correct function.
* **Bilingual Intelligence:** Fully fluent in both English and French. The bot detects your language on the fly and replies natively.
* **Group Chat Sniffer:** In group chats, MattouBot politely stays quiet during human-to-human conversations to save API tokens, only waking up when explicitly named or when it detects a clear, implicit command.
* **Contextual Memory & State:** Media curators (Music, Movies, Books) remember your previous requests, avoid repeating suggestions for 7 days, and understand format corrections (e.g., *"No, I want a playlist instead"* or *"Give me a top 3 list instead"*).

---

## 🏗️ System Architecture

The ecosystem is divided into two primary execution environments, ensuring high availability for interactive requests while offloading heavy research tasks to a serverless CI/CD pipeline.

### 1. Interactive Application (`bot.py`)
Deployed as a continuous web service, this application acts as the central interface for on-demand tasks.
- **Smart Media Sommeliers:** Curates highly specific music, book, and movie recommendations based on vibes, genres, or activities. Dynamically handles requests for single items, playlists, trilogies, or top-tier lists using Python-enforced output formatting.
- **Dynamic Weather & Time:** Native timezone awareness combined with relative date calculations (via Regex and Python `datetime`) allows the bot to fetch accurate forecasts (via `wttr.in`) whether you ask for "today," "après-demain," "next Monday," or "in 4 days".
- **Telemetry Analysis & Coaching:** Integrates with the Strava API to parse recent activity history, calculate systemic training loads, and design fatigue-aware training plans.
- **Stateful Task Management:** Utilizes MongoDB Atlas for persistent state management, allowing authorized users to manage and synchronize shared lists (e.g., groceries) across multiple devices securely.

### 2. Automated Scheduled Swarms (`scheduled_jobs/`)
Executed autonomously via GitHub Actions utilizing cron schedules, these scripts operate independently of the main application.
- **Morning Briefing Pipeline:** Parses iCloud Calendar data, retrieves localized Open-Meteo weather data, and curates top geopolitical news into a formatted daily summary.
- **Financial Analyst Swarm:** A cyclic LangGraph AI pipeline. A *Searcher Agent* gathers live Yahoo Finance portfolio data and web news → an *Analyst Agent* drafts a concise report → an *Editor Agent* strictly reviews the draft for formatting and data accuracy.
- **Automated Media Dispatch:** A lightweight scheduled cron job that retrieves and delivers daily media content via third-party APIs.

---

## 🚀 Getting Started & Configuration

To run this ecosystem locally or in production, you must obtain API keys and configure your environment variables.

### Step 1: Obtain your Secrets
1. **Telegram Token:** Go to Telegram, search for the **@BotFather**, send `/newbot`, follow the steps, and copy the `HTTP API Token`.
2. **Telegram Chat ID:** To restrict the bot so only you (or your group) can use it, find your Chat ID. You can message **@userinfobot** or **@RawDataBot** on Telegram to get your numeric ID.
3. **Hugging Face Token:** Create an account on [Hugging Face](https://huggingface.co/), go to Settings > Access Tokens, and generate a new read/write token.

### Step 2: Environment Variables
Create a `.env` file in the root directory for local development, or inject them securely via your cloud provider's Secrets management.

```env
# Platform & Authentication
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_numeric_chat_id,another_chat_id

# AI & Third-Party APIs
HF_TOKEN=your_huggingface_token
APPLE_CALENDAR_URL=[https://pXX-caldav.icloud.com/published/](https://pXX-caldav.icloud.com/published/)...

# Database (MongoDB Atlas)
MONGO_URI=mongodb+srv://user:password@cluster0.mongodb.net/

# Strava Integration (Optional)
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_REFRESH_TOKEN=your_refresh_token
```

---

## 💻 Local Development & Testing

1. Clone the repository and navigate into the root directory.
2. Create an isolated Python virtual environment and install the required dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Ensure your `.env` file is populated.
4. **Test the Interactive App:** Run `python bot.py` to initiate the Telegram polling sequence. Send a message to your bot on Telegram to test the NLU routing.
5. **Test a Swarm Execution:** Run `python scheduled_jobs/financial_analyst.py` to observe the LangGraph nodes negotiate, draft, and QA a report in your terminal.

---

## ☁️ Cloud Deployment Guide

### Deploying the Interactive App (Render)
1. Connect your GitHub repository to a **Render Web Service**.
2. Configure the Build Command: `pip install -r requirements.txt`
3. Configure the Start Command: `python bot.py`
4. Inject all `.env` variables into the Render **Environment** tab.
5. *Database Note:* Ensure your MongoDB Atlas Network Access is configured to `0.0.0.0/0` to allow incoming connections from Render's dynamic IP pool.

### Deploying the Automated Swarm (GitHub Actions)
The scheduled jobs are completely serverless and executed via `.github/workflows/daily_swarm.yml`.
1. Navigate to your GitHub Repository → **Settings** → **Secrets and variables** → **Actions**.
2. Add your credentials (`HF_TOKEN`, `TELEGRAM_TOKEN`, etc.) as **Repository Secrets**.
3. GitHub Actions will automatically provision Ubuntu runners at the scheduled intervals, execute the Python workflows, and dispatch the payloads directly to your Telegram chat.

---

## 🐳 Advanced Infrastructure (Optional)
For users requiring self-hosted or bare-metal deployments, this repository retains legacy infrastructure manifests.
- Use `docker-compose up --build` for containerized local execution.
- The `k8s/` directory contains manifests for deploying the application and database to a Kubernetes cluster utilizing a `StatefulSet` and a timezone-aware `CronJob`.