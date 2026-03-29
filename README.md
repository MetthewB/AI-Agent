# Automated Daily Finance Swarm (MLOps Pipeline)

This project implements an automated, cyclic multi-agent AI pipeline using LangGraph, Docker, MongoDB, and Kubernetes. The system utilizes three distinct AI agents working in a feedback loop to research the latest financial news, draft a daily briefing, and perform quality assurance before saving the final report.

## Architecture
- **Inference:** Cloud-based execution via Hugging Face Serverless API (Qwen 32B).
- **Searcher Agent:** Scrapes the web for the last 24 hours of news on a given topic.
- **Analyst Agent:** Synthesizes the raw news into a formatted Markdown daily briefing.
- **Editor Agent (QA):** Reviews the draft and either approves it or kicks it back to the Searcher with specific feedback for improvement (up to 3 revisions).
- **Infrastructure:** Fully containerized using Docker Compose for local testing, with production-ready Kubernetes manifests (StatefulSet & CronJob) for automated daily execution.

## Prerequisites
1. Docker Desktop installed and running (with Kubernetes enabled).
2. A free [Hugging Face Access Token](https://huggingface.co/settings/tokens) with Inference permissions.
3. A `.env` file in the root directory containing your token:
   `HF_TOKEN=hf_your_actual_token_here`

## How to Customize the Swarm
To change the research topic, open `multi_agents.py`, scroll to the bottom **EXECUTION PIPELINE** section, and modify the `topic` variable.

## How to Run (Docker Compose - Local Testing)
This is the recommended method for testing changes to the AI logic.

1. Build and start the swarm:
   ```bash
   docker compose up --build
   ```
2. Wait for the terminal to output `✅ Pipeline complete`.
3. Locate your generated report inside the newly created `output/` folder on your local machine.
4. Stop the containers when finished:
   ```bash
   docker compose down
   ```

## How to Run (Kubernetes - Automated Production)
This project includes manifests to run the database as a Kubernetes `StatefulSet` and the AI Swarm as a scheduled `CronJob` (running daily at 8:00 AM).

1. Inject your Hugging Face token securely into the cluster:
   ```bash
   kubectl create secret generic hf-secret --from-literal=HF_TOKEN="hf_your_actual_token_here"
   ```
2. Deploy the MongoDB database:
   ```bash
   kubectl apply -f k8s/mongodb.yaml
   ```
3. Build the local image and deploy the automated CronJob:
   ```bash
   docker build -t swarm-agent:v1 .
   kubectl apply -f k8s/cronjob.yaml
   ```
4. **(Optional)** Trigger a manual test run immediately without waiting for the morning schedule:
   ```bash
   kubectl create job --from=cronjob/daily-finance-swarm finance-test-run
   ```
5. Extract the generated report from the completed pod:
   ```bash
   # Find your pod name
   kubectl get pods
   
   # Copy the report to your machine
   kubectl cp YOUR_POD_NAME:/app/output ./k8s-output
   ```
6. Tear down the cluster resources when finished:
   ```bash
   kubectl delete -f k8s/cronjob.yaml
   kubectl delete -f k8s/mongodb.yaml
   ```