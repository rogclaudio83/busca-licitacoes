from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/buscar")
def buscar(produto: str = Query(...)):
    # URL da API do Governo (PNCP)
    url = f"https://pncp.gov.br{produto}&pagina=1"
    
    try:
        response = requests.get(url, timeout=10)
        dados = response.json()
        
        # Estrutura básica para o seu HTML ler
        return {
            "sucesso": True,
            "mais_opcoes": [
                {
                    "id": i,
                    "preco": float(item.get('valorTotal', 0)),
                    "orgao": item.get('orgaoEntidade', {}).get('razaoSocial'),
                    "esfera": "Federal",
                    "data": item.get('dataPublicacao', '')[:10],
                    "fornecedor": "Ver no Edital",
                    "cnpj": "-"
                } for i, item in enumerate(dados.get('resultado', []))
            ],
            "sugestao_ideal": []
        }
    except:
        return {"sucesso": False, "erro": "Falha ao acessar governo"}
