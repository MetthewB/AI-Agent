from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel

# 1. Connect to your local Ollama instance
# We use the "ollama_chat/" prefix so LiteLLM knows how to format the request
model = LiteLLMModel(
    model_id="ollama_chat/qwen2.5-coder:3b", 
    api_base="http://localhost:11434", 
    num_ctx=8192 # Gives the model enough memory/context to read search results
)

# 2. Initialize the DuckDuckGo Search Tool
search_tool = DuckDuckGoSearchTool()

# 3. Create the Agent
# We pass our tool and the local model to the CodeAgent
agent = CodeAgent(
    tools=[search_tool], 
    model=model,
    add_base_tools=True,
    additional_authorized_imports=["requests", "bs4"]
)

# 4. Give the Agent a task!
print("Starting the research task...\n")
task = """
Search the web to find out who won the 2018 football world cup final match and summarize the final score. 
Rules:
1. Rely primarily on the search snippets provided by your search tool.
2. Do not write custom web scrapers unless absolutely necessary.
3. Once you have the winner and the score, return the final answer immediately and stop execution.
"""

# Run the agent and print the final result
result = agent.run(task)

print("\n--- Final Result ---")
print(result)