# MattouBot: Dual-System AI Assistant & Multi-Agent Pipeline

This repository contains the source code, architecture, and deployment configurations for a comprehensive, dual-system personal AI assistant. The ecosystem integrates a continuous interactive chatbot with an automated, scheduled multi-agent swarm to handle daily task management, telemetry analysis, global financial research, and automated briefings.

## System Architecture

The ecosystem is divided into two primary execution environments, ensuring high availability for interactive requests while offloading heavy research tasks to a serverless CI/CD pipeline.

### 1. Interactive Application (`bot.py`)
Deployed as a continuous web service on Render, this application acts as the central interface for on-demand tasks and state management.
- **Telemetry Analysis & Coaching:** Integrates with the Strava API to parse recent activity history, calculate systemic training loads, and design hyper-specific, fatigue-aware training plans using LLM inference.
- **Stateful Task Management:** Utilizes MongoDB Atlas for persistent state management, allowing authorized users to manage and synchronize shared lists (e.g., groceries) across multiple devices securely.
- **On-Demand LLM Inference:** Leverages the Hugging Face Serverless API (Qwen 32B) for zero-shot tasks, including recipe generation based on available inventory, geopolitical news summaries, and weighted decision-making.

### 2. Automated Scheduled Swarms (`scheduled_jobs/`)
Executed autonomously via GitHub Actions utilizing cron schedules, these scripts operate independently of the main application.
- **Morning Briefing Pipeline:** Parses iCloud Calendar data (webcal), retrieves localized Open-Meteo weather data, and curates top geopolitical news into a formatted daily summary.
- **Financial Analyst Swarm:** A cyclic LangGraph AI pipeline. A *Searcher Agent* gathers live Yahoo Finance portfolio data and web news $\rightarrow$ an *Analyst Agent* drafts a concise report $\rightarrow$ an *Editor Agent* strictly reviews the draft for formatting and data accuracy, looping back if constraints are not met.
- **Automated Media Dispatch:** A lightweight scheduled cron job that retrieves and delivers daily media content via third-party APIs (TheCatAPI).

## Prerequisites & Environment Configuration

To run this ecosystem locally or in production, you must configure the following environment variables. Use a `.env` file for local development or inject them securely via your cloud provider's Secrets management.

```env
# Platform & Authentication
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_numeric_chat_id,another_chat_id

# AI & Third-Party APIs
HF_TOKEN=your_huggingface_token
APPLE_CALENDAR_URL=[https://pXX-caldav.icloud.com/published/](https://pXX-caldav.icloud.com/published/)...

# Database (MongoDB Atlas)
MONGO_URI=mongodb+srv://user:password@cluster0.mongodb.net/

# Strava Integration
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_REFRESH_TOKEN=your_refresh_token
```

## Local Development & Testing

1. Clone the repository and navigate into the root directory.
2. Create an isolated Python virtual environment and install the required dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory using the template provided above.
4. **Test the Interactive App:** Run `python bot.py` to initiate the Telegram polling sequence.
5. **Test a Swarm Execution:** Run `python scheduled_jobs/financial_analyst.py` to observe the LangGraph nodes negotiate, draft, and QA a report in your terminal.

## Cloud Deployment Guide

### Deploying the Interactive App (Render)
1. Connect your GitHub repository to a **Render Web Service**.
2. Configure the Build Command: `pip install -r requirements.txt`
3. Configure the Start Command: `python bot.py`
4. Inject all `.env` variables into the Render **Environment** tab.
5. *Database Note:* Ensure your MongoDB Atlas Network Access is configured to `0.0.0.0/0` to allow incoming connections from Render's dynamic IP pool.

### Deploying the Automated Swarm (GitHub Actions)
The scheduled jobs are completely serverless and executed via `.github/workflows/daily_swarm.yml`.
1. Navigate to your GitHub Repository $\rightarrow$ **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
2. Add your credentials (`HF_TOKEN`, `TELEGRAM_TOKEN`, etc.) as **Repository Secrets**.
3. GitHub Actions will automatically provision Ubuntu runners at the scheduled intervals, execute the Python workflows, and dispatch the payloads to Telegram.

## Advanced Infrastructure (Optional)
For users requiring self-hosted or bare-metal deployments, this repository retains legacy infrastructure manifests.
- Use `docker-compose up --build` for containerized local execution.
- The `k8s/` directory contains manifests for deploying the application and database to a Kubernetes cluster utilizing a `StatefulSet` and a timezone-aware `CronJob`.
