from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
BASE_URL = "https://pncp.gov.br/api/consulta/v1"

def formatar_data(data_str):
    if not data_str: return "N/I"
    return data_str[:10].split('-')[::-1] if '-' in data_str else data_str[:10]

def buscar_api(termo: str, pagina: int):
    """Função core de busca no endpoint de itens"""
    url = f"{BASE_URL}/contratacoes/itens"
    # Note: O PNCP exige que o termo tenha pelo menos 3 caracteres
    params = {
        "pagina": pagina,
        "tamanhoPagina": 50,
        "descricao": termo, 
    }
    
    try:
        # Aumentei o timeout porque o PNCP as vezes demora para responder buscas amplas
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        
        dados = resp.json()
        return dados.get("data", [])
    except Exception as e:
        print(f"Erro na busca: {e}")
        return []

@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    # 1. Limpeza do termo: pega as duas primeiras palavras para ser mais amplo
    # Exemplo: "Cadeira de Escritório Preta" vira "Cadeira Escritório"
    palavras = [p for p in produto.split() if len(p) > 2]
    termo_amplo = " ".join(palavras[:2]) if palavras else produto
    
    todas_contratacoes = []
    
    # 2. Busca em paralelo para ganhar volume (páginas 1 a 6)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futuros = [executor.submit(buscar_api, termo_amplo, p) for p in range(1, 7)]
        for f in as_completed(futuros):
            todas_contratacoes.extend(f.result())

    if not todas_contratacoes:
        return {"sucesso": True, "mensagem": "Nenhum item encontrado com esse termo", "resultados": []}

    # 3. Processamento dos resultados
    vistos = set()
    final_results = []

    for item in todas_contratacoes:
        valor = item.get("valorUnitario") or item.get("valorEstimado") or 0
        if valor <= 0: continue

        # Identificador único para evitar duplicatas (Mesmo Órgão + Mesmo Preço + Mesma Descrição)
        id_unico = f"{item.get('orgaoEntidade', {}).get('cnpj')}-{valor}-{item.get('descricaoItem')[:30]}"
        
        if id_unico not in vistos:
            vistos.add(id_unico)
            
            cnpj = item.get("orgaoEntidade", {}).get("cnpj", "")
            ano = item.get("anoContratacao")
            seq = item.get("sequencialContratacao")
            
            final_results.append({
                "preco": round(float(valor), 2),
                "descricao": item.get("descricaoItem", "").upper(),
                "orgao": item.get("orgaoEntidade", {}).get("razaoSocial", "N/I"),
                "unidade": item.get("unidadeMedida", "UN"),
                "quantidade": item.get("quantidade", 0),
                "data": formatar_data(item.get("dataAtualizacao") or item.get("dataInclusao")),
                "uf": item.get("ufSigla", "N/I"),
                "municipio": item.get("municipioNome", "N/I"),
                "link": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
            })

    # 4. Ordenação por preço
    final_results.sort(key=lambda x: x["preco"])

    return {
        "sucesso": True,
        "termo_usado": termo_amplo,
        "total": len(final_results),
        "resultados": final_results[:50]
    }
