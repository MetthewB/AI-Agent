from smolagents import CodeAgent, DuckDuckGoSearchTool, InferenceClientModel, tool
from pymongo import MongoClient

# 1. Connect to our Dockerized MongoDB
client = MongoClient("mongodb://mongodb:27017/")
db = client["research_swarm"]
collection = db["knowledge_base"]

# 2. Define our Custom Tool
@tool
def save_research_to_db(topic: str, summary: str) -> str:
    """Saves the research summary to the database.
    
    Args:
        topic: The main subject of the research (e.g., '2022 World Cup').
        summary: The summarized facts found during research.
    """
    document = {"topic": topic, "summary": summary}
    collection.insert_one(document)
    return f"Successfully saved research on '{topic}' to MongoDB."

# 3. Initialize the massive Hugging Face Cloud Model
model = InferenceClientModel(model_id="Qwen/Qwen2.5-Coder-32B-Instruct")
search_tool = DuckDuckGoSearchTool()

# 4. Create the Agent
agent = CodeAgent(
    tools=[search_tool, save_research_to_db],
    model=model,
    add_base_tools=True
)

# 5. The Task
print("Starting the cloud-powered research task...\n")
task = """
1. Use the web search tool to find out who won the 2022 FIFA World Cup.
2. Use the web search tool to find out the final score of that match.
3. CAREFULLY READ the results of your searches. 
4. EXTRACT ONLY the name of the winning team and the final score. Do not include raw search results.
5. Create a concise summary string, for example: "Argentina beat France with a score of 3-3 (4-2 on penalties)."
6. Pass that concise summary string into the `save_research_to_db` tool with the topic '2022 World Cup'.
7. Return a success message as your final answer.
"""

result = agent.run(task)

print("\n--- Final Result ---")
print(result)

print("\n--- Verifying Database Contents ---")
for doc in collection.find():
    print(f"Found in DB -> Topic: {doc['topic']} | Summary: {doc['summary']}")