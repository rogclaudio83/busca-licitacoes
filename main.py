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
    # Buscamos no endpoint de itens de contratações para pegar valores unitários reais
    url = f"https://pncp.gov.br{produto}&pagina=1&tamanhoPagina=10"
    
    try:
        headers = {'accept': '*/*'}
        response = requests.get(url, headers=headers, timeout=20)
        dados = response.json()
        
        # O PNCP retorna os dados dentro de 'resultado'
        itens_brutos = dados.get('resultado', [])
        
        lista_final = []
        for item in itens_brutos:
            # Pegamos o valor total da contratação como base de preço aplicável
            valor = float(item.get('valorTotal', 0))
            if valor > 0:
                lista_final.append({
                    "id": item.get('id'),
                    "preco": valor,
                    "orgao": item.get('orgaoEntidade', {}).get('razaoSocial', 'Órgão não identificado'),
                    "esfera": "Federal" if item.get('orgaoEntidade', {}).get('esferaId') == 'F' else "Estadual/Muni",
                    "data": item.get('dataPublicacao', '')[:10],
                    "fornecedor": "Consulte o Edital no PNCP",
                    "cnpj": "-"
                })
        
        # Ordenamos do menor para o maior para a regra dos 20%
        lista_final.sort(key=lambda x: x['preco'])
            
        return {
            "sucesso": True, 
            "mais_opcoes": lista_final, 
            "sugestao_ideal": lista_final[:3]
        }
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}
