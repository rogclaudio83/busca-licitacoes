from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# --- BUSCA PNCP ---
def buscar_pncp(termo: str):
    url = "https://pncp.gov.br/api/consulta/v1/contratacoes/itens"
    # Pegamos as 2 primeiras páginas para garantir volume
    resultados = []
    for pagina in [1, 2]:
        params = {"pagina": pagina, "tamanhoPagina": 50, "descricao": termo}
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                itens = resp.json().get("data", [])
                for i in itens:
                    valor = i.get("valorUnitario") or i.get("valorEstimado") or 0
                    if float(valor) > 0.1:
                        resultados.append({
                            "fonte": "PNCP",
                            "preco": round(float(valor), 2),
                            "descricao": i.get("descricaoItem", "").upper(),
                            "orgao": i.get("orgaoEntidade", {}).get("razaoSocial", "N/I"),
                            "uf": i.get("ufSigla", "N/I"),
                            "link": f"https://pncp.gov.br/app/editais/{i.get('orgaoEntidade', {}).get('cnpj')}/{i.get('anoContratacao')}/{i.get('sequencialContratacao')}"
                        })
        except:
            continue
    return resultados

# --- ENDPOINT DE BUSCA ---
@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    # Limpeza simples do termo para aumentar alcance
    palavras = [p for p in produto.split() if len(p) > 2]
    termo_busca = " ".join(palavras[:2]) if palavras else produto
    
    # Executa a busca
    resultados = buscar_pncp(termo_busca)
    
    # Ordena por preço
    resultados.sort(key=lambda x: x["preco"])
    
    return {
        "termo_pesquisado": termo_busca,
        "total": len(resultados),
        "itens": resultados[:50]
    }

# --- ROTA DE BOAS-VINDAS (Para evitar o 404 na raiz) ---
@app.get("/")
async def root():
    return {
        "status": "Online",
        "instrucoes": "Para buscar um produto, adicione no final da URL: /buscar?produto=nome-do-item",
        "exemplo": "http://127.0.0.1:8000/buscar?produto=notebook"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
