from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import os

app = FastAPI(title="Busca Precisa PNCP")

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
BASE_URL = "https://pncp.gov.br/api/consulta/v1"

def formatar_data(data_str: str) -> str:
    if not data_str:
        return "N/I"
    try:
        # Formato esperado: 2024-05-20T...
        p = data_str[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except:
        return data_str[:10]

def buscar_itens_no_pncp(termo: str, pagina: int) -> list:
    """
    Busca diretamente no endpoint de itens, garantindo que o termo 
    esteja na descrição do produto e já trazendo o preço unitário.
    """
    url = f"{BASE_URL}/contratacoes/itens"
    params = {
        "pagina": pagina,
        "tamanhoPagina": 50,
        "descricao": termo,
    }
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []
            
        dados = response.json()
        itens = dados.get("data", [])
        resultados_locais = []
        
        for item in itens:
            # Tenta obter o valor mais real possível (Unitário ou Estimado)
            valor = item.get("valorUnitario") or item.get("valorEstimado") or 0
            
            # Filtro de precisão: Ignora valores zerados ou irreais (ex: R$ 0,01)
            if float(valor) < 0.10:
                continue
                
            cnpj = item.get("orgaoEntidade", {}).get("cnpj", "")
            ano = item.get("anoContratacao")
            seq = item.get("sequencialContratacao")
            
            resultados_locais.append({
                "preco": round(float(valor), 2),
                "descricao": item.get("descricaoItem", "").upper(),
                "orgao": item.get("orgaoEntidade", {}).get("razaoSocial", "N/I"),
                "unidade": item.get("unidadeMedida", "UN"),
                "quantidade": item.get("quantidade", 0),
                "data": formatar_data(item.get("dataAtualizacao") or item.get("dataInclusao")),
                "municipio": item.get("municipioNome", "N/I"),
                "uf": item.get("ufSigla", ""),
                "modalidade": item.get("modalidadeNome", "N/I"),
                "link": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if cnpj else "#"
            })
        return resultados_locais
    except Exception as e:
        print(f"Erro na página {pagina}: {e}")
        return []

@app.get("/")
async def index():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(caminho):
        return FileResponse(caminho)
    return {"mensagem": "API de Busca PNCP Online. Use o endpoint /buscar?produto=nome"}

@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    termo_busca = produto.strip().lower()
    
    all_results = []
    # Consultamos as 4 primeiras páginas em paralelo para ter volume e velocidade
    # Isso cobre até 200 itens potenciais.
    paginas = [1, 2, 3, 4]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futuros = [executor.submit(buscar_itens_no_pncp, termo_busca, p) for p in paginas]
        for f in as_completed(futuros):
            all_results.extend(f.result())

    # 1. Deduplicação: evita o mesmo item no mesmo órgão com mesmo preço
    vistos = set()
    unicos = []
    for r in all_results:
        # Criamos uma chave única baseada em CNPJ do órgão (embutido no link), preço e descrição
        chave = (r["link"], r["preco"], r["descricao"][:50])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)

    # 2. Ordenação: Do mais barato para o mais caro
    unicos.sort(key=lambda x: x["preco"])

    return {
        "sucesso": True,
        "termo_pesquisado": termo_busca,
        "total_encontrado": len(unicos),
        "resultados": unicos[:40] # Retorna os 40 melhores resultados
    }

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
