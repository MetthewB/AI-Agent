import os
from smolagents import CodeAgent, DuckDuckGoSearchTool, InferenceClientModel, tool
from pymongo import MongoClient

# --- Database Setup ---
client = MongoClient("mongodb://mongodb:27017/")
collection = client["research_swarm"]["knowledge_base"]

# --- AI Model Setup ---
model = InferenceClientModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct")

# --- Custom Tools ---
@tool
def save_research_to_db(topic: str, summary: str) -> str:
    """Saves the research summary to the database."""
    collection.insert_one({"topic": topic, "summary": summary})
    return f"Successfully saved research on '{topic}' to MongoDB."

@tool
def read_research_from_db(topic: str) -> str:
    """Reads the research summary from the database for a given topic."""
    document = collection.find_one({"topic": topic})
    return document["summary"] if document else "No research found for this topic."

@tool
def save_report_to_file(topic: str, content: str) -> str:
    """Saves a markdown report to the local file system."""
    os.makedirs("/app/output", exist_ok=True)
    filename = f"/app/output/{topic.replace(' ', '_').lower()}_report.md"
    
    with open(filename, "w") as f:
        f.write(content)
    return f"Report successfully saved as {filename}"

# --- Agent Initialization ---
searcher_agent = CodeAgent(
    tools=[DuckDuckGoSearchTool(), save_research_to_db],
    model=model,
    add_base_tools=True
)

analyst_agent = CodeAgent(
    tools=[read_research_from_db, save_report_to_file],
    model=model,
    add_base_tools=True
)

# ==========================================
# --- CONFIGURATION & EXECUTION PIPELINE ---
# ==========================================
if __name__ == "__main__":
    
    # 1. Change your research topic here
    TOPIC = "SpaceX Starship Recent Flight"

    # 2. Adjust the Searcher's instructions
    search_task = f"""
    1. Search the web for the most recent test flight of the {TOPIC}.
    2. Find out if it was successful and what the main achievements were.
    3. Pass a concise summary of the facts into the `save_research_to_db` tool using the topic '{TOPIC}'.
    """

    # 3. Adjust the Analyst's instructions
    analyst_task = f"""
    1. Use the `read_research_from_db` tool to get the raw facts about '{TOPIC}'.
    2. Write a professional, 3-paragraph news report in Markdown format based on those facts. Use bullet points for achievements.
    3. Save the final markdown string using the `save_report_to_file` tool using the topic '{TOPIC}'.
    """

    print(f"Initiating Swarm Pipeline for: {TOPIC}...")
    searcher_agent.run(search_task)
    analyst_agent.run(analyst_task)
    print("Pipeline complete. Check the output folder!")