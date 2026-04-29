from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import os

app = FastAPI()

# 🛡️ CORREÇÃO DO CORS: Isso libera o acesso para o seu navegador
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho):
        return FileResponse(caminho)
    return {"erro": "index.html nao encontrado"}

@app.get("/buscar")
def buscar(produto: str = Query(...)):
    # URL oficial do PNCP
    url = f"https://pncp.gov.br{produto}&pagina=1"
    
    try:
        response = requests.get(url, timeout=20)
        dados = response.json()
        itens = dados.get('resultado', [])
        
        lista = []
        for item in itens:
            lista.append({
                "id": item.get('id'),
                "preco": float(item.get('valorTotal', 0)),
                "orgao": item.get('orgaoEntidade', {}).get('razaoSocial', 'Órgão não identificado'),
                "esfera": "Federal" if item.get('orgaoEntidade', {}).get('esferaId') == 'F' else "Estadual/Muni",
                "data": item.get('dataPublicacao', '')[:10],
                "fornecedor": "Disponível no Edital",
                "cnpj": "-"
            })
            
        # Ordena por preço para a regra dos 20% funcionar
        lista.sort(key=lambda x: x['preco'])
            
        return {"sucesso": True, "mais_opcoes": lista}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
