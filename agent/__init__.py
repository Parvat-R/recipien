import getpass
import os
import dotenv

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")

if "GROQ_API_KEY" not in os.environ:
    os.environ["GROQ_API_KEY"] = getpass.getpass("Enter your Groq API key: ")


from .agents import groq_agent, gemini_agent  # import AFTER env is set
from .vision_agent import extract_ingredients_from_image
from langchain_core.messages import AIMessage


def ask_agent(prompt: str, thread_id: str = "default"):
    inputs = {"messages": [{"role": "user", "content": prompt}]}
    config = {"configurable": {"thread_id": thread_id}}
    for chunk in groq_agent.stream(inputs, config, stream_mode="updates"): # type: ignore
        for node_output in chunk.values():
            messages = node_output.get("messages", [])
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.content:
                    yield msg.content