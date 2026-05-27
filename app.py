import os
import streamlit as st

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.environ.get("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = "nutritionist-agent"

from langchain_groq import ChatGroq
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langsmith import traceable

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SYSTEM_PROMPT = """Ты — профессиональный нутрициолог-ассистент. 
Помогаешь клиентам с вопросами питания, анализируешь рационы, 
даёшь рекомендации по здоровому питанию. 
Отвечай на русском языке, будь конкретным и полезным."""

st.set_page_config(page_title="Агент нутрициолога", page_icon="🥗")
st.title("🥗 Агент нутрициолога")
st.caption("Задайте вопрос о питании")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    with st.chat_message(role):
        st.write(msg.content)

if prompt := st.chat_input("Ваш вопрос..."):
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.write(prompt)

    llm = ChatGroq(api_key=GROQ_API_KEY, model="llama-3.3-70b-versatile") 
    all_messages = [SystemMessage(content=SYSTEM_PROMPT)] + st.session_state.messages
    response = llm.invoke(all_messages)
    st.session_state.messages.append(AIMessage(content=response.content))
    with st.chat_message("assistant"):
        st.write(response.content)
