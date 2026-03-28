# Multi-Agent Research Swarm (MLOps Pipeline)

This project implements a multi-agent AI pipeline using Hugging Face's `smolagents`, Docker, MongoDB, and Kubernetes. The system utilizes two distinct AI agents that communicate asynchronously through a stateful database to research topics and generate markdown reports.

## Architecture
- **Inference:** Cloud-based execution via Hugging Face Serverless API (Qwen 32B).
- **Searcher Agent:** Navigates the web, extracts facts, and saves summaries to MongoDB.
- **Analyst Agent:** Reads raw facts from MongoDB and generates a formatted Markdown report.
- **Infrastructure:** Fully containerized using Docker Compose, with production-ready Kubernetes manifests.

## Prerequisites
1. Docker Desktop installed and running.
2. A free [Hugging Face Access Token](https://huggingface.co/settings/tokens) with Inference permissions.
3. A `.env` file in the root directory containing your token:
   `HF_TOKEN=hf_your_actual_token_here`

## How to Customize the Prompt
To change the research topic or the agent instructions, open `agent_with_memory.py` and scroll to the bottom **CONFIGURATION & EXECUTION PIPELINE** section. Modify the `TOPIC`, `search_task`, or `analyst_task` variables.

## How to Run (Docker Compose)
This is the recommended method for local testing and development.

1. Build and start the swarm:
   ```bash
   docker compose up --build
   ```
2. Wait for the terminal to output `Pipeline complete`.
3. Locate your generated report inside the newly created `output/` folder on your local machine.
4. Stop the containers when finished:
   ```bash
   docker compose down
   ```

## How to Run (Kubernetes)
This project includes manifests to run the swarm as a Kubernetes `StatefulSet` and `Job`. Ensure Kubernetes is enabled in your Docker Desktop settings.

1. Create the secure secret for your Hugging Face token:
   ```bash
   kubectl create secret generic hf-secret --from-literal=HF_TOKEN="hf_your_actual_token_here"
   ```
2. Deploy the MongoDB database:
   ```bash
   kubectl apply -f k8s/mongodb.yaml
   ```
3. Build the local image and launch the Agent Job:
   ```bash
   docker build -t swarm-agent:v1 .
   kubectl apply -f k8s/agent-job.yaml
   ```
4. Extract the generated report from the sleeping pod:
   ```bash
   kubectl cp YOUR_POD_NAME:/app/output ./k8s-output
   ```
5. Tear down the cluster resources:
   ```bash
   kubectl delete -f k8s/agent-job.yaml
   kubectl delete -f k8s/mongodb.yaml
   ```