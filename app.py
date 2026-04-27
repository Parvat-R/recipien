import streamlit as st
from agent import ask_agent
import uuid

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

st.title("Recipien: Your AI Recipe Assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay stored messages on rerun
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("What ingredients do you have?"):
    # Display and store user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display and store assistant response
    with st.chat_message("assistant"):
        response = st.write_stream(ask_agent(prompt, thread_id=st.session_state.thread_id))
    st.session_state.messages.append({"role": "assistant", "content": response})