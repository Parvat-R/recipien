from langchain_openrouter import ChatOpenRouter
from langchain_core.messages import HumanMessage
import time
import dotenv
import getpass
from pydantic.types import SecretStr
dotenv.load_dotenv()

import os

vision_model = ChatOpenRouter(
    model="openai/gpt-5.5",  # free + vision support
    temperature=0,
    max_tokens=512,
    max_retries=3,
    api_key=SecretStr(os.environ.get("OPENROUTER_API_KEY", getpass.getpass("OPENROUTER_API_KEY > ")))
)


def extract_ingredients_from_image(image_base64: str, media_type: str) -> str:
    """
    One-shot vision call. Returns a plain ingredient sentence.
    No tools, no memory — just image → text.
    """
    message = HumanMessage(content=[
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
        },
        {
            "type": "text",
            "text": (
                "Look at this image and list all the food ingredients or items you can see. "
                "Respond with a single, natural sentence like: "
                "'I have eggs, butter, milk, spinach, and cheddar cheese.' "
                "Only list food items. Do not add any explanation or extra text."
            ),
        },
    ])

    response = vision_model.invoke([message])

    if isinstance(response.content, str):  # no quotes around str
        return response.content.strip()
    return str(response.content)