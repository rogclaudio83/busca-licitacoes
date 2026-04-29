from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}

@app.get("/buscar")
def buscar(produto: str = Query(...)):
    # Aumentamos a abrangência da busca removendo filtros restritivos de data inicial
    # O PNCP retornará as publicações mais recentes primeiro por padrão
    url = f"https://pncp.gov.br{produto}&pagina=1&tamanhoPagina=10"
    
    try:
        response = requests.get(url, timeout=20)
        dados = response.json()
        
        lista = []
        # O PNCP retorna os dados dentro da chave 'data' ou 'resultado' dependendo do endpoint
        itens = dados.get('resultado', [])
        
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
            
        return {
            "sucesso": True, 
            "mais_opcoes": lista, 
            "sugestao_ideal": lista[:3]
        }
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
