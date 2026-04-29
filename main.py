from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

class SearchRequest(BaseModel):
    query: str

@app.get("/")
def serve_frontend():
    return FileResponse("index.html")

@app.post("/search")
def search(request: SearchRequest):
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Você é um assistente especialista em concursos públicos brasileiros, "
                    f"com foco em Administração Pública. Responda à seguinte pergunta de forma "
                    f"clara, objetiva e didática, como se estivesse explicando para um candidato "
                    f"estudando para um concurso:\n\n{request.query}"
                ),
            }
        ],
    )
    return {"result": message.content[0].text}
