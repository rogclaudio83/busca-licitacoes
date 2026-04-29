from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
BASE = "https://pncp.gov.br/api/consulta/v1"


# ── Helpers ──────────────────────────────────────────────────────────────────

def formatar_data(data_str: str) -> str:
    if not data_str:
        return "N/I"
    try:
        p = data_str[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return data_str[:10]


def extrair_item(c: dict, produto: str) -> dict | None:
    """Extrai e normaliza um item de contratação. Retorna None se inválido."""
    valor = c.get("valorTotalEstimado") or c.get("valorTotalHomologado")
    if not valor or float(valor) <= 0:
        return None

    esfera_map = {"F": "Federal", "E": "Estadual", "M": "Municipal"}
    esfera_cod = c.get("orgaoEntidade", {}).get("esferaId", "")

    return {
        "preco":           round(float(valor), 2),
        "orgao":           c.get("orgaoEntidade", {}).get("razaoSocial") or c.get("unidadeOrgao", {}).get("nomeUnidade") or "N/I",
        "esfera":          esfera_map.get(esfera_cod, esfera_cod or "N/I"),
        "data":            formatar_data(c.get("dataPublicacaoGlobal") or c.get("dataAberturaProposta", "")),
        "descricao":       c.get("objetoCompra", produto),
        "modalidade":      c.get("modalidadeNome", "N/I"),
        "numero_processo": c.get("numeroCompra") or c.get("processo", "N/I"),
        "uf":              c.get("unidadeOrgao", {}).get("ufSigla", ""),
        "municipio":       c.get("unidadeOrgao", {}).get("municipioNome", ""),
    }


def buscar_pagina(url: str, params: dict, termo: str) -> list:
    """Busca uma página e filtra pelo termo. Retorna lista de itens encontrados."""
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []

        data = resp.json()
        itens = data.get("data", [])
        encontrados = []

        for c in itens:
            objeto = (c.get("objetoCompra") or "").lower()
            info   = (c.get("informacaoComplementar") or "").lower()

            if termo in objeto or termo in info:
                item = extrair_item(c, termo)
                if item:
                    encontrados.append(item)

        return encontrados
    except Exception:
        return []


# ── Rotas ────────────────────────────────────────────────────────────────────

@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}


@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    termo = produto.strip().lower()
    resultados = []
    hoje = datetime.today()

    # Monta lista de tarefas: (url, params)
    # Cobre os últimos 12 meses em janelas mensais, 5 páginas cada = ~60 requisições paralelas
    tarefas = []

    for meses_atras in range(0, 12):
        data_fim = hoje - timedelta(days=30 * meses_atras)
        data_ini = hoje - timedelta(days=30 * (meses_atras + 1))

        for pagina in range(1, 6):  # páginas 1 a 5
            params = {
                "dataInicial":   data_ini.strftime("%Y%m%d"),
                "dataFinal":     data_fim.strftime("%Y%m%d"),
                "pagina":        pagina,
                "tamanhoPagina": 50,
            }
            tarefas.append((f"{BASE}/contratacoes/publicacao", params))

    # Executa em paralelo (máximo 20 threads simultâneas)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futuros = {
            executor.submit(buscar_pagina, url, params, termo): (url, params)
            for url, params in tarefas
        }
        for futuro in as_completed(futuros):
            resultados.extend(futuro.result())
            if len(resultados) >= 30:
                break  # Já temos dados suficientes

    # Deduplica por orgão+preço
    vistos = set()
    unicos = []
    for r in resultados:
        chave = (r["orgao"], r["preco"])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)

    # Ordena pelo menor preço e limita a 20
    unicos.sort(key=lambda x: x["preco"])
    unicos = unicos[:20]

    return {
        "sucesso":     True,
        "total":       len(unicos),
        "mais_opcoes": unicos,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
