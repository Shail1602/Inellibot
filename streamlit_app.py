import streamlit as st
from snowflake.core import Root
from snowflake.cortex import Complete
from snowflake.snowpark.session import Session

APP_NAME = "SS IntelliBot"
st.set_page_config(APP_NAME, page_icon="🤖", layout="wide")
MODELS = ["mistral-large2", "llama3.1-70b", "llama3.1-8b"]

# Snowflake session config
connection_parameters = {
    "user": st.secrets["snowflake"]["user"],
    "password": st.secrets["snowflake"]["password"],
    "account": st.secrets["snowflake"]["account"],
    "warehouse": st.secrets["snowflake"]["warehouse"],
    "database": st.secrets["snowflake"]["database"],
    "schema": st.secrets["snowflake"]["schema"],
    "role": st.secrets["snowflake"].get("role", "ACCOUNTADMIN")
}

session = Session.builder.configs(connection_parameters).create()
root = Root(session)

TOPICS = ["All Topics", "Database Concepts", "AWS Framework", "Python for Beginners", "Azure", "PostgreSQL", "Kubernetes", "Pro Git", "OWASP"]

# --- FUNCTIONS ---

def complete(model, prompt):
    return Complete(model, prompt, session=session).replace("$", "\$")

def init_messages():
    if "pinned_messages" not in st.session_state:
        st.session_state.pinned_messages = []
    if st.session_state.get("clear_conversation") or "messages" not in st.session_state:
        st.session_state.messages = []

def init_service_metadata():
    if "service_metadata" not in st.session_state:
        services = session.sql("SHOW CORTEX SEARCH SERVICES;").collect()
        metadata = []
        for s in services:
            svc_name = s["name"]
            search_col = session.sql(f"DESC CORTEX SEARCH SERVICE {svc_name};").collect()[0]["search_column"]
            metadata.append({"name": svc_name, "search_column": search_col})
        st.session_state.service_metadata = metadata

def get_chat_history():
    return st.session_state.messages[-st.session_state.num_chat_messages:-1]

def summarize_chat(chat_history, question):
    prompt = f"""
    [INST]
    Extend the user question using the chat history.
    <chat_history>{chat_history}</chat_history>
    <question>{question}</question>
    [/INST]
    """
    return complete(st.session_state.model_name, prompt)

def build_prompt(question):
    chat_history = get_chat_history() if st.session_state.use_chat_history else []
    chat_text = "\n".join([msg["content"] for msg in chat_history if msg["role"] == "user"])
    summary = summarize_chat(chat_text, question) if chat_history else question
    context = query_cortex(summary)
    prompt = f"""
    [INST]
    You are SS IntelliBot, a helpful AI assistant with access to PDF-based knowledge.
    Use the provided <context> and <chat_history> to answer user questions.
    Respond clearly, briefly, and helpfully.

    <chat_history>{chat_text}</chat_history>
    <context>{context}</context>
    <question>{question}</question>
    [/INST]
    Answer:
    """
    return prompt

def query_cortex(query, columns=[], filter={}):
    db, schema = session.get_current_database(), session.get_current_schema()
    svc = root.databases[db].schemas[schema].cortex_search_services[st.session_state.selected_cortex_search_service]
    results = svc.search(query, columns=columns, filter=filter, limit=st.session_state.num_retrieved_chunks).results
    search_col = next(s["search_column"] for s in st.session_state.service_metadata if s["name"] == st.session_state.selected_cortex_search_service).lower()
    context = "\n\n".join([f"Context {i+1}: {r[search_col]}" for i, r in enumerate(results)])
    if st.session_state.debug:
        st.sidebar.text_area("📄 Context Documents", context, height=300)
    return context

def apply_theme():
    if st.session_state.get("dark_mode"):
        st.markdown("""
            <style>
            body, .stApp {
                background-color: #0e1117;
                color: #fafafa;
            }
            </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <style>
            body, .stApp {
                background-color: #f2f2f2;
                color: #000000;
            }
            </style>
        """, unsafe_allow_html=True)

def init_config():
    with st.sidebar:
        st.toggle("🌓 Dark Mode", key="dark_mode", value=False)
        apply_theme()
        st.title("⚙️ Configuration")
        st.selectbox("Cortex Search Service", [s["name"] for s in st.session_state.service_metadata], key="selected_cortex_search_service")
        st.button("🧹 Clear Chat", key="clear_conversation")
        st.toggle("🐞 Debug Mode", key="debug", value=False)
        st.toggle("🕘 Use Chat History", key="use_chat_history", value=True)
        st.selectbox("📂 Filter by Topic", TOPICS, key="selected_topic")

        with st.expander("🧠 Advanced Options"):
            st.selectbox("Select Model", MODELS, key="model_name")
            st.slider("Context Chunks", 1, 10, 5, key="num_retrieved_chunks")
            st.slider("Chat History Messages", 1, 10, 5, key="num_chat_messages")

def handle_uploaded_pdf():
    uploaded_file = st.sidebar.file_uploader("📥 Upload PDF", type=["pdf"], key="pdf_uploader")
    if uploaded_file is not None:
        st.session_state.uploaded_pdf = uploaded_file.name
        st.sidebar.success(f"Uploaded: {uploaded_file.name}")

def generate_summary():
    full_history = st.session_state.messages
    formatted_history = ""
    for m in full_history:
        role = "User" if m["role"] == "user" else "Assistant"
        formatted_history += f"{role}: {m['content']}\n"
    prompt = f"""
    [INST]
    You are an expert summarizer. Summarize the following chat conversation into 5-7 key bullet points that capture the main ideas and solutions shared by the assistant. Be concise, and do not repeat.
    <chat_history>
    {formatted_history}
    </chat_history>
    Your output should look like:
    - Point 1
    - Point 2
    ...
    [/INST]
    """
    summary = complete(st.session_state.model_name, prompt)
    return summary.strip()

def main():
    st.markdown("<h1 style='text-align: center;'>🤖 SS IntelliBot</h1>", unsafe_allow_html=True)
    add_custom_css()
    handle_uploaded_pdf()
    init_service_metadata()
    init_config()
    init_messages()

    if len(st.session_state.messages) == 0:
        st.info("👋 Welcome to SS IntelliBot! Ask any question based on our uploaded documents or the topics below:")
        st.markdown("""
        - 🔍 What is the difference between RDS and Redshift?
        - 🤖 How do I deploy a model in Kubernetes?
        - 🔐 What are OWASP Top 10 vulnerabilities?
        - 🐘 How to connect Python to PostgreSQL?
        - ☁️ What are key services in AWS Framework?
        """)

    for msg in st.session_state.messages:
        css_class = "chat-left" if msg["role"] == "assistant" else "chat-right"
        st.markdown(f"<div class='{css_class}'>{msg['content']}</div>", unsafe_allow_html=True)

    disable_chat = not st.session_state.service_metadata
    if question := st.chat_input("💬 Ask your question...", disabled=disable_chat):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.spinner("SS IntelliBot is typing..."):
            prompt = build_prompt(question.replace("'", ""))
            reply = complete(st.session_state.model_name, prompt)
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.markdown(f"<div class='chat-left'>{reply}</div>", unsafe_allow_html=True)

    if st.session_state.messages:
        with st.expander("📊 Generate Summary"):
            if st.button("Generate Insight Summary"):
                summary = generate_summary()
                st.markdown(f"**🔎 Summary:**\n\n{summary}", unsafe_allow_html=True)

        with st.expander("⬇️ Download Chat History"):
            full_chat = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in st.session_state.messages])
            st.download_button("Download .txt", full_chat, file_name="chat_history.txt")

        with st.expander("📢 Feedback"):
            st.radio("How helpful was the response?", ["👍 Excellent", "👌 Good", "👎 Needs Improvement"])

def add_custom_css():
    st.markdown("""
    <style>
        .chat-left {
            background-color: #f4f4f4;
            padding: 14px;
            border-radius: 14px;
            margin: 12px 0;
            text-align: left;
            font-size: 15px;
            border-left: 4px solid #1f77b4;
        }
        .chat-right {
            background-color: #dcf4ea;
            padding: 14px;
            border-radius: 14px;
            margin: 12px 0;
            text-align: right;
            font-size: 15px;
            border-right: 4px solid #2a9d8f;
        }
    </style>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
