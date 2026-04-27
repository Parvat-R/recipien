from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from .tools import recipe_tools
from .prompt import system_prompt

# Separate checkpointers per agent so their conversation histories don't mix
groq_checkpointer = InMemorySaver()
gemini_checkpointer = InMemorySaver()

groq_model = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    max_tokens=4096,
    timeout=None,
    max_retries=2,
)

gemini_model = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro-preview-03-25",
    temperature=1.0,
    max_tokens=8192,
    timeout=None,
    max_retries=2,
)

groq_agent = create_agent(
    model=groq_model,
    tools=recipe_tools,
    system_prompt=system_prompt,
    checkpointer=groq_checkpointer,
)

gemini_agent = create_agent(
    model=gemini_model,
    tools=recipe_tools,
    system_prompt=system_prompt,
    checkpointer=gemini_checkpointer,
)