from langchain_groq import ChatGroq
from app.core.config import settings


LLM = ChatGroq(
    model=settings.GROQ_MODEL_NAME,
    api_key=settings.GROQ_API_KEY,
)
