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
BASE    = "https://pncp.gov.br/api/consulta/v1"

# Modalidades: 6=Pregão Eletrônico, 8=Dispensa, 1=Concorrência
MODALIDADES = [6, 8, 1]

# UFs brasileiras para varrer
UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT",
       "PA","PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"]


def formatar_data(data_str: str) -> str:
    if not data_str:
        return "N/I"
    try:
        p = data_str[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return data_str[:10]


def buscar_itens_compra(cnpj: str, ano: int, sequencial: int, termo: str) -> list:
    """Busca os itens de uma compra específica e filtra pelo termo."""
    url = f"{BASE}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        itens = resp.json()
        if not isinstance(itens, list):
            itens = itens.get("data", [])

        encontrados = []
        for item in itens:
            descricao = (item.get("descricao") or "").lower()
            if termo not in descricao:
                continue
            valor = item.get("valorUnitarioEstimado") or item.get("valorUnitario")
            if not valor or float(valor) <= 0:
                continue
            encontrados.append({
                "descricao": item.get("descricao", "N/I"),
                "preco":     round(float(valor), 2),
                "unidade":   item.get("unidadeMedida", "UN"),
                "quantidade": item.get("quantidade", 1),
            })
        return encontrados
    except Exception:
        return []


def buscar_pagina(uf: str, modalidade: int, data_ini: str, data_fim: str,
                  pagina: int, termo: str) -> list:
    """Busca uma página de contratações e filtra pelo termo no objeto."""
    url = f"{BASE}/contratacoes/publicacao"
    params = {
        "dataInicial":                data_ini,
        "dataFinal":                  data_fim,
        "codigoModalidadeContratacao": modalidade,
        "uf":                         uf,
        "pagina":                     pagina,
        "tamanhoPagina":              50,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        contratacoes = resp.json().get("data", [])
        resultados = []

        for c in contratacoes:
            objeto = (c.get("objetoCompra") or "").lower()
            info   = (c.get("informacaoComplementar") or "").lower()

            # Filtra pelo termo no objeto da compra
            if termo not in objeto and termo not in info:
                continue

            cnpj       = c.get("orgaoEntidade", {}).get("cnpj", "")
            ano        = c.get("anoCompra")
            sequencial = c.get("sequencialCompra")
            orgao      = c.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
            esfera_map = {"F": "Federal", "E": "Estadual", "M": "Municipal"}
            esfera     = esfera_map.get(c.get("orgaoEntidade", {}).get("esferaId", ""), "N/I")
            data       = formatar_data(c.get("dataPublicacaoGlobal") or c.get("dataAberturaProposta", ""))
            municipio  = c.get("unidadeOrgao", {}).get("municipioNome", "")

            # Tenta buscar itens individuais com preço unitário
            if cnpj and ano and sequencial:
                itens = buscar_itens_compra(cnpj, ano, sequencial, termo)
                for item in itens:
                    resultados.append({
                        "preco":           item["preco"],
                        "orgao":           orgao,
                        "esfera":          esfera,
                        "data":            data,
                        "descricao":       item["descricao"],
                        "unidade":         item["unidade"],
                        "quantidade":      item["quantidade"],
                        "modalidade":      c.get("modalidadeNome", "N/I"),
                        "numero_processo": c.get("numeroCompra") or c.get("processo", "N/I"),
                        "uf":              uf,
                        "municipio":       municipio,
                    })

            # Se não achou itens, usa o valor total da contratação como fallback
            if not resultados or not cnpj:
                valor = c.get("valorTotalEstimado") or c.get("valorTotalHomologado")
                if valor and float(valor) > 0:
                    resultados.append({
                        "preco":           round(float(valor), 2),
                        "orgao":           orgao,
                        "esfera":          esfera,
                        "data":            data,
                        "descricao":       c.get("objetoCompra", termo),
                        "unidade":         "VB",
                        "quantidade":      1,
                        "modalidade":      c.get("modalidadeNome", "N/I"),
                        "numero_processo": c.get("numeroCompra") or c.get("processo", "N/I"),
                        "uf":              uf,
                        "municipio":       municipio,
                    })

        return resultados
    except Exception:
        return []


@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}


@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    termo  = produto.strip().lower()
    hoje   = datetime.today()
    data_fim = hoje.strftime("%Y%m%d")
    data_ini = (hoje - timedelta(days=60)).strftime("%Y%m%d")

    # Monta tarefas: (uf, modalidade, pagina)
    tarefas = []
    for uf in UFS:
        for modalidade in MODALIDADES:
            for pagina in [1, 2]:  # 2 páginas × 50 = 100 por UF/modalidade
                tarefas.append((uf, modalidade, data_ini, data_fim, pagina, termo))

    resultados = []

    # Executa em paralelo
    with ThreadPoolExecutor(max_workers=30) as executor:
        futuros = {
            executor.submit(buscar_pagina, *t): t for t in tarefas
        }
        for futuro in as_completed(futuros):
            resultados.extend(futuro.result())
            if len(resultados) >= 50:
                break

    # Deduplica por orgao + preco + descricao
    vistos = set()
    unicos = []
    for r in resultados:
        chave = (r["orgao"], r["preco"], r["descricao"][:40])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)

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
