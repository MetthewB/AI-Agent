import os
from smolagents import CodeAgent, DuckDuckGoSearchTool, InferenceClientModel, tool
from pymongo import MongoClient

# --- 1. Database Setup ---
client = MongoClient("mongodb://mongodb:27017/")
db = client["research_swarm"]
collection = db["knowledge_base"]

# --- 2. Define the Cloud Model ---
# Both agents will share this brain
model = InferenceClientModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct")

# --- 3. Define the Tools ---
@tool
def save_research_to_db(topic: str, summary: str) -> str:
    """Saves the research summary to the database.
    Args:
        topic: The main subject of the research.
        summary: The summarized facts found during research.
    """
    collection.insert_one({"topic": topic, "summary": summary})
    return f"Successfully saved research on '{topic}' to MongoDB."

@tool
def read_research_from_db(topic: str) -> str:
    """Reads the research summary from the database for a given topic.
    Args:
        topic: The main subject of the research to retrieve.
    """
    document = collection.find_one({"topic": topic})
    if document:
        return document["summary"]
    return "No research found for this topic."

@tool
def save_report_to_file(topic: str, content: str) -> str:
    """Saves a beautifully formatted markdown report to the local file system.
    Args:
        topic: The topic, which will be used for the filename.
        content: The full markdown content of the report.
    """
    # We save this in an 'output' folder that Docker will map to your Mac
    os.makedirs("/app/output", exist_ok=True) 
    filename = f"/app/output/{topic.replace(' ', '_').lower()}_report.md"
    
    with open(filename, "w") as f:
        f.write(content)
    return f"Report successfully saved as {filename}"

# --- 4. Create the Agents ---
search_tool = DuckDuckGoSearchTool()

print("--- INITIALIZING SWARM ---")
searcher_agent = CodeAgent(
    tools=[search_tool, save_research_to_db],
    model=model,
    add_base_tools=True
)

analyst_agent = CodeAgent(
    tools=[read_research_from_db, save_report_to_file],
    model=model,
    add_base_tools=True
)

# --- 5. Run the Pipeline ---
topic = "SpaceX Starship Recent Flight"

print(f"\n>>> PHASE 1: Waking up the Searcher Agent to research '{topic}'...")
search_task = f"""
1. Search the web for the most recent test flight of the SpaceX Starship.
2. Find out if it was successful and what the main achievements were.
3. Pass a concise summary of the facts into the `save_research_to_db` tool using the topic '{topic}'.
"""
searcher_agent.run(search_task)


print(f"\n>>> PHASE 2: Waking up the Analyst Agent to write the report on '{topic}'...")
analyst_task = f"""
1. Use the `read_research_from_db` tool to get the raw facts about '{topic}'.
2. Write a professional, 3-paragraph news report in Markdown format based on those facts. Use bullet points for achievements.
3. Save the final markdown string using the `save_report_to_file` tool using the topic '{topic}'.
"""
analyst_agent.run(analyst_task)

print("\n--- PIPELINE COMPLETE ---")