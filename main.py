from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import os

app = FastAPI()

# Libera o acesso para o seu navegador não bloquear o site
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ESTA É A CHAVE: Faz o link do Render abrir o seu index.html
@app.get("/")
async def principal():
    return FileResponse('index.html')

@app.get("/buscar")
def buscar(produto: str = Query(...)):
    # Busca real no Governo Federal (PNCP) dos últimos 5 meses
    url = f"https://pncp.gov.br{produto}&pagina=1"
    
    try:
        response = requests.get(url, timeout=15)
        dados = response.json()
        
        resultado_final = []
        for item in dados.get('resultado', []):
            resultado_final.append({
                "id": item.get('id'),
                "preco": float(item.get('valorTotal', 0)),
                "orgao": item.get('orgaoEntidade', {}).get('razaoSocial', 'Órgão não identificado'),
                "esfera": "Federal" if item.get('orgaoEntidade', {}).get('esferaId') == 'F' else "Estadual/Muni",
                "data": item.get('dataPublicacao', '')[:10],
                "fornecedor": "Ver no Edital",
                "cnpj": "-"
            })
            
        return {"sucesso": True, "mais_opcoes": resultado_final, "sugestao_ideal": resultado_final[:3]}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
