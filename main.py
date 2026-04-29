from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests
import os

app = FastAPI()

# 🛡️ PERMISSÃO TOTAL: Resolve o erro de conexão do navegador
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
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}

@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    # URL do PNCP para resultados reais
    url = f"https://pncp.gov.br{produto}&pagina=1&tamanhoPagina=10"
    
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        dados = response.json()
        itens = dados.get('resultado', [])
        
        lista = []
        for item in itens:
            valor = float(item.get('valorTotal', 0))
            if valor > 0:
                lista.append({
                    "id": item.get('id'),
                    "preco": valor,
                    "orgao": item.get('orgaoEntidade', {}).get('razaoSocial', 'Orgao nao identificado'),
                    "esfera": "Federal" if item.get('orgaoEntidade', {}).get('esferaId') == 'F' else "Estadual/Muni",
                    "data": item.get('dataPublicacao', '')[:10],
                    "fornecedor": "Consulte o Edital",
                    "cnpj": "-"
                })
        
        lista.sort(key=lambda x: x['preco'])
        return {"sucesso": True, "mais_opcoes": lista}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
