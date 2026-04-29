from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import os

app = FastAPI()

# Liberação de segurança para o navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ROTA RAIZ: É aqui que resolvemos o "Not Found"
@app.get("/")
async def principal():
    # Busca o caminho exato onde o arquivo index.html está no servidor
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho):
        return FileResponse(caminho)
    return {"erro": "O arquivo index.html não foi encontrado na raiz do servidor."}

# ROTA DE BUSCA: Conversa com o Governo
@app.get("/buscar")
def buscar(produto: str = Query(...)):
    url = f"https://pncp.gov.br{produto}&pagina=1"
    try:
        response = requests.get(url, timeout=15)
        dados = response.json()
        
        lista_final = []
        for item in dados.get('resultado', []):
            lista_final.append({
                "id": item.get('id'),
                "preco": float(item.get('valorTotal', 0)),
                "orgao": item.get('orgaoEntidade', {}).get('razaoSocial', 'Órgão não identificado'),
                "esfera": "Federal" if item.get('orgaoEntidade', {}).get('esferaId') == 'F' else "Estadual/Muni",
                "data": item.get('dataPublicacao', '')[:10],
                "fornecedor": "Ver no Edital",
                "cnpj": "-"
            })
            
        return {"sucesso": True, "mais_opcoes": lista_final, "sugestao_ideal": lista_final[:3]}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
