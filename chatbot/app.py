import os

import streamlit as st
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.azure_openai import AzureOpenAI

st.set_page_config(
    page_title="Chat with the PDM docs",
    page_icon="📝",
    layout="centered",
    initial_sidebar_state="auto",
    menu_items=None,
)
st.title("Chat with the PDM docs 💬🦙")
st.info(
    "PDM - A modern Python package and dependency manager. "
    "Check out the full documentation at [PDM docs](https://pdm-project.org).",
    icon="📃",
)
Settings.llm = AzureOpenAI(
    api_key=st.secrets.get("aoai_key"),
    azure_endpoint=st.secrets.get("aoai_endpoint"),
    engine="gpt-35-turbo",
    api_version="2024-02-15-preview",
    temperature=0.5,
    system_prompt="You are an expert on PDM and your job is to answer technical questions. "
    "Assume that all questions are related to PDM. Keep your answers technical and based on facts - do not hallucinate features.",
)
Settings.embed_model = AzureOpenAIEmbedding(
    azure_deployment="embedding",
    api_key=st.secrets.get("aoai_key"),
    api_version="2023-05-15",
    azure_endpoint=st.secrets.get("aoai_endpoint"),
)

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs/")

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
        index = VectorStoreIndex.from_documents(docs)
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
