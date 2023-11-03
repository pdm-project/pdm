import os

import openai
import streamlit as st
from llama_index import ServiceContext, SimpleDirectoryReader, VectorStoreIndex
from llama_index.llms import OpenAI

st.set_page_config(
    page_title="Chat with the PDM docs, powered by LlamaIndex",
    page_icon="📝",
    layout="centered",
    initial_sidebar_state="auto",
    menu_items=None,
)
openai.api_key = st.secrets.openai_key
st.title("Chat with the PDM docs, powered by LlamaIndex 💬🦙")
st.info(
    "PDM - A modern Python package and dependency manager. "
    "Check out the full documentation at [PDM docs](https://pdm.fming.dev).",
    icon="📃",
)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs/docs")

if "messages" not in st.session_state.keys():  # Initialize the chat messages history
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Ask me a question about PDM!",
        }
    ]


@st.cache_resource(show_spinner=False)
def load_data():
    with st.spinner(text="Loading and indexing the PDM docs - hang tight! This should take 1-2 minutes."):
        reader = SimpleDirectoryReader(input_dir=DATA_PATH, recursive=True, required_exts=[".md"])
        docs = reader.load_data()
        service_context = ServiceContext.from_defaults(
            llm=OpenAI(
                model="gpt-3.5-turbo",
                temperature=0.5,
                system_prompt="You are an expert on PDM and your job is to answer technical questions. "
                "Assume that all questions are related to PDM. Keep your answers technical and based on facts - do not hallucinate features.",
            )
        )
        index = VectorStoreIndex.from_documents(docs, service_context=service_context)
        return index


index = load_data()

if "chat_engine" not in st.session_state.keys():  # Initialize the chat engine
    st.session_state.chat_engine = index.as_chat_engine(chat_mode="condense_question", verbose=True)

if prompt := st.chat_input("Your question"):  # Prompt for user input and save to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

for message in st.session_state.messages:  # Display the prior chat messages
    with st.chat_message(message["role"]):
        st.write(message["content"])

# If last message is not from assistant, generate a new response
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = st.session_state.chat_engine.chat(prompt)
            st.write(response.response)
            message = {"role": "assistant", "content": response.response}
            st.session_state.messages.append(message)  # Add response to message history
