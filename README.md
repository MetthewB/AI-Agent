# Automated Swiss Job Market & Finance Swarm (MLOps Pipeline)

This project implements an automated, cyclic multi-agent AI pipeline using LangGraph, Docker, MongoDB, and Kubernetes. The system utilizes three distinct AI agents working in a feedback loop to research the latest global financial trends and the Swiss engineering job market, perform quality assurance, and email a structured daily briefing directly to the user.

## Architecture
- **Inference:** Cloud-based execution via Hugging Face Serverless API (Qwen 32B).
- **Searcher Agent:** Intelligent 3-tier fallback system (searches the last 24 hours of news $\rightarrow$ falls back to a monthly web search $\rightarrow$ falls back to unfiltered search to prevent API crashes).
- **Analyst Agent:** Synthesizes raw data into a strictly formatted Markdown report detailing Global Markets, specific Stock Buy/Sell signals, and Swiss Engineering trends.
- **Editor Agent (QA):** A strict review node that forces the Searcher to find new data if the draft lacks specific stock tickers or Swiss-specific hiring news (up to 3 revisions).
- **Delivery:** Automated SMTP email dispatch via secure credentials.
- **Infrastructure:** Fully containerized using Docker Compose for local testing, with production-ready Kubernetes manifests (`StatefulSet` & timezone-aware `CronJob`) for automated daily execution.

## Prerequisites
1. Docker Desktop installed and running (with Kubernetes enabled).
2. A free [Hugging Face Access Token](https://huggingface.co/settings/tokens) with Inference permissions.
3. A Gmail account with a [16-letter App Password](https://myaccount.google.com/apppasswords) for automated SMTP email delivery.
4. A `.env` file in the root directory for local Docker testing:
   ```env
   HF_TOKEN=hf_your_actual_token_here
   SENDER_EMAIL=your_email@gmail.com
   SENDER_PASSWORD=your_16_letter_app_password
   RECEIVER_EMAIL=where_to_send@email.com
   ```

## How to Customize the Swarm
To change the research topic, open `multi_agents.py`, scroll to the bottom **EXECUTION PIPELINE** section, and modify the `topic` variable. You can also adjust the Analyst's strict Markdown formatting instructions in the `analyst_node`.

## How to Run (Docker Compose - Local Testing)
This is the recommended method for testing changes to the AI logic.

1. Build and start the swarm:
   ```bash
   docker compose up --build
   ```
2. Wait for the terminal to output `✅ Pipeline complete`.
3. Check your email inbox for the delivered report, or locate the local copy inside the newly created `output/` folder on your machine.
4. Stop the containers when finished:
   ```bash
   docker compose down
   ```

## How to Run (Kubernetes - Automated Production)
This project includes manifests to run the database as a Kubernetes `StatefulSet` and the AI Swarm as a scheduled `CronJob` (currently configured to run daily at 10:00 AM local time).

1. Inject your Hugging Face token securely into the cluster:
   ```bash
   kubectl create secret generic hf-secret --from-literal=HF_TOKEN="hf_your_actual_token_here"
   ```
2. Inject your Email credentials securely into the cluster:
   ```bash
   kubectl create secret generic email-secret \
     --from-literal=SENDER_EMAIL="your_email@gmail.com" \
     --from-literal=SENDER_PASSWORD="your_16_letter_app_password" \
     --from-literal=RECEIVER_EMAIL="where_to_send@email.com"
   ```
3. Deploy the MongoDB database:
   ```bash
   kubectl apply -f k8s/mongodb.yaml
   ```
4. Build the local image and deploy the automated CronJob:
   ```bash
   docker build -t swarm-agent:v1 .
   kubectl apply -f k8s/cronjob.yaml
   ```
5. **(Optional)** Trigger a manual test run immediately without waiting for the morning schedule:
   ```bash
   kubectl create job --from=cronjob/daily-finance-swarm swiss-test-run
   ```
6. **(Optional)** Extract the generated report from the pod manually (if email delivery fails):
   ```bash
   kubectl get pods
   kubectl cp YOUR_POD_NAME:/app/output ./k8s-output
   ```
7. Tear down the cluster resources when finished:
   ```bash
   kubectl delete -f k8s/cronjob.yaml
   kubectl delete -f k8s/mongodb.yaml
   ```