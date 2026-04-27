import streamlit as st
from agent import ask_agent, extract_ingredients_from_image
import uuid
import base64

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

st.title("Recipien: Your AI Recipe Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay stored messages on rerun
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("image"):
            st.image(msg["image"], caption="Ingredients image", use_container_width=True)
        st.markdown(msg["content"])

# Optional image upload
uploaded_file = st.file_uploader(
    "Upload a photo of your fridge or ingredients (optional)",
    type=["jpg", "jpeg", "png", "webp"],
)

if prompt := st.chat_input("What ingredients do you have?"):
    final_prompt = prompt

    # If image uploaded, extract ingredients and prepend to prompt
    image_bytes = None
    if uploaded_file:
        image_bytes = uploaded_file.read()
        media_type = uploaded_file.type
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        with st.spinner("Scanning your image for ingredients..."):
            detected = extract_ingredients_from_image(image_b64, media_type)

        # Merge: image-detected ingredients + any extra text the user typed
        if prompt.strip():
            final_prompt = f"{detected} Also, {prompt}"
        else:
            final_prompt = detected

    # Display user message
    with st.chat_message("user"):
        if image_bytes:
            st.image(image_bytes, caption="Ingredients image", use_container_width=True)
        st.markdown(final_prompt)
    st.session_state.messages.append({
        "role": "user",
        "content": final_prompt,
        "image": image_bytes,
    })

    # Stream agent response
    with st.chat_message("assistant"):
        response = st.write_stream(
            ask_agent(final_prompt, thread_id=st.session_state.thread_id)
        )
    st.session_state.messages.append({"role": "assistant", "content": response})