from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import os
import re

app = FastAPI(title="GovPreços API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GovPrecos/3.0)",
    "Accept":     "application/json",
}

# ─────────────────────────────────────────────────────────────
#  URLS BASE DE CADA PLATAFORMA
# ─────────────────────────────────────────────────────────────
BASE_PNCP    = "https://pncp.gov.br/api/consulta/v1"
BASE_COMPRAS = "https://compras.dados.gov.br/licitacoes/v1"

# Modalidades PNCP: 6=Pregão Eletrônico, 8=Dispensa, 1=Concorrência, 2=Diálogo, 5=Concurso
MODALIDADES = [6, 8, 1, 2, 5]

UFS = [
    "AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT",
    "PA","PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO",
]

ESFERA_MAP = {"F": "Federal", "E": "Estadual", "M": "Municipal"}


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def formatar_data(data_str: str) -> str:
    if not data_str:
        return "N/I"
    try:
        p = data_str[:10].split("-")
        return f"{p[2]}/{p[1]}/{p[0]}"
    except Exception:
        return data_str[:10]


def safe_float(v) -> float:
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except Exception:
        return 0.0


def normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def get_json(url: str, params: dict = None, timeout: int = 12):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
#  FONTE 1 — PNCP: itens individuais de uma compra
# ─────────────────────────────────────────────────────────────
def pncp_itens_compra(cnpj: str, ano: int, sequencial: int, termo: str) -> list:
    url  = f"{BASE_PNCP}/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens"
    data = get_json(url)
    if not data:
        return []
    if isinstance(data, dict):
        data = data.get("data", [])

    resultados = []
    for item in (data or []):
        descricao = (item.get("descricao") or "").lower()
        if termo not in descricao:
            continue
        valor = safe_float(item.get("valorUnitarioEstimado") or item.get("valorUnitario"))
        if valor <= 0:
            continue
        resultados.append({
            "descricao": item.get("descricao", "N/I"),
            "preco":     valor,
            "unidade":   item.get("unidadeMedida", "UN"),
            "quantidade": safe_float(item.get("quantidade", 1)),
        })
    return resultados


def pncp_buscar_pagina(uf: str, modalidade: int, data_ini: str, data_fim: str,
                       pagina: int, termo: str) -> list:
    params = {
        "dataInicial":                 data_ini,
        "dataFinal":                   data_fim,
        "codigoModalidadeContratacao": modalidade,
        "uf":                          uf,
        "pagina":                      pagina,
        "tamanhoPagina":               50,
    }
    data = get_json(f"{BASE_PNCP}/contratacoes/publicacao", params)
    if not data:
        return []

    resultados = []
    for c in data.get("data", []):
        objeto = (c.get("objetoCompra") or "").lower()
        info   = (c.get("informacaoComplementar") or "").lower()
        if termo not in objeto and termo not in info:
            continue

        cnpj            = c.get("orgaoEntidade", {}).get("cnpj", "")
        ano             = c.get("anoCompra")
        sequencial      = c.get("sequencialCompra")
        orgao           = c.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
        esfera          = ESFERA_MAP.get(c.get("orgaoEntidade", {}).get("esferaId", ""), "N/I")
        data_pub        = formatar_data(c.get("dataPublicacaoGlobal") or c.get("dataAberturaProposta", ""))
        municipio       = c.get("unidadeOrgao", {}).get("municipioNome", "")
        modalidade_nome = c.get("modalidadeNome", "N/I")
        num_processo    = c.get("numeroCompra") or c.get("processo", "N/I")

        achou_itens = False
        if cnpj and ano and sequencial:
            itens = pncp_itens_compra(cnpj, ano, sequencial, termo)
            for item in itens:
                achou_itens = True
                resultados.append({
                    "preco":           item["preco"],
                    "orgao":           orgao,
                    "esfera":          esfera,
                    "data":            data_pub,
                    "descricao":       item["descricao"],
                    "unidade":         item["unidade"],
                    "quantidade":      item["quantidade"],
                    "modalidade":      modalidade_nome,
                    "numero_processo": num_processo,
                    "uf":              uf,
                    "municipio":       municipio,
                    "cnpj_orgao":      cnpj,
                    "fonte":           "PNCP",
                })

        if not achou_itens:
            valor = safe_float(c.get("valorTotalEstimado") or c.get("valorTotalHomologado"))
            if valor > 0:
                resultados.append({
                    "preco":           valor,
                    "orgao":           orgao,
                    "esfera":          esfera,
                    "data":            data_pub,
                    "descricao":       c.get("objetoCompra", termo)[:120],
                    "unidade":         "VB",
                    "quantidade":      1,
                    "modalidade":      modalidade_nome,
                    "numero_processo": num_processo,
                    "uf":              uf,
                    "municipio":       municipio,
                    "cnpj_orgao":      cnpj,
                    "fonte":           "PNCP",
                })
    return resultados


# ─────────────────────────────────────────────────────────────
#  FONTE 2 — PNCP: pesquisa global por palavra-chave
# ─────────────────────────────────────────────────────────────
def pncp_busca_global(termo: str, pagina: int = 1) -> list:
    params = {
        "q":             termo,
        "pagina":        pagina,
        "tamanhoPagina": 50,
    }
    data = get_json(f"{BASE_PNCP}/contratacoes/pesquisa", params, timeout=15)
    if not data:
        return []

    corte      = datetime.today() - timedelta(days=180)
    resultados = []

    for c in (data.get("data") or []):
        objeto = (c.get("objetoCompra") or "").lower()
        if termo not in objeto:
            continue
        valor = safe_float(c.get("valorTotalEstimado") or c.get("valorTotalHomologado"))
        if valor <= 0:
            continue

        data_raw = c.get("dataPublicacaoGlobal") or c.get("dataAberturaProposta") or ""
        try:
            if datetime.fromisoformat(data_raw[:10]) < corte:
                continue
        except Exception:
            pass

        orgao  = c.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
        cnpj   = c.get("orgaoEntidade", {}).get("cnpj", "")
        esfera = ESFERA_MAP.get(c.get("orgaoEntidade", {}).get("esferaId", ""), "N/I")
        uf     = c.get("unidadeOrgao", {}).get("ufNome") or c.get("uf", "BR")

        resultados.append({
            "preco":           valor,
            "orgao":           orgao,
            "esfera":          esfera,
            "data":            formatar_data(data_raw),
            "descricao":       c.get("objetoCompra", "N/I")[:120],
            "unidade":         "VB",
            "quantidade":      1,
            "modalidade":      c.get("modalidadeNome", "N/I"),
            "numero_processo": c.get("numeroCompra") or "N/I",
            "uf":              uf,
            "municipio":       c.get("unidadeOrgao", {}).get("municipioNome", ""),
            "cnpj_orgao":      cnpj,
            "fonte":           "PNCP (Global)",
        })
    return resultados


# ─────────────────────────────────────────────────────────────
#  FONTE 3 — COMPRAS.DADOS.GOV.BR
# ─────────────────────────────────────────────────────────────
def compras_dados_buscar(termo: str) -> list:
    params = {
        "descricao_objeto": termo,
        "_pageSize":        50,
        "_page":            1,
    }
    data = get_json(f"{BASE_COMPRAS}/licitacoes.json", params, timeout=15)
    if not data:
        return []

    resultados = []
    for item in (data.get("result") or []):
        valor = safe_float(
            item.get("licitacao_objeto_valor_estimado") or item.get("valor_licitacao")
        )
        if valor <= 0:
            continue

        descricao = item.get("licitacao_objeto") or item.get("objeto_licitacao") or termo
        orgao     = item.get("unidade_nome") or item.get("orgao_nome") or "N/I"
        data_pub  = formatar_data(
            item.get("data_publicacao") or item.get("data_abertura_proposta", "")
        )

        resultados.append({
            "preco":           valor,
            "orgao":           orgao,
            "esfera":          "Federal",
            "data":            data_pub,
            "descricao":       descricao[:120],
            "unidade":         "VB",
            "quantidade":      1,
            "modalidade":      item.get("modalidade_nome", "N/I"),
            "numero_processo": item.get("numero_licitacao") or item.get("processo", "N/I"),
            "uf":              item.get("uf", "BR"),
            "municipio":       item.get("municipio_nome", ""),
            "cnpj_orgao":      normalizar_cnpj(item.get("cnpj_orgao", "")),
            "fonte":           "Dados.gov.br",
        })
    return resultados


# ─────────────────────────────────────────────────────────────
#  FONTE 4 — PAINEL DE PREÇOS (Gov Federal — preço de referência)
# ─────────────────────────────────────────────────────────────
def painel_precos_buscar(termo: str) -> list:
    url    = "https://api.paineldeprecos.gov.br/material/consulta"
    params = {"descricao": termo, "pagina": 0, "tamanho": 30}
    data   = get_json(url, params, timeout=15)
    if not data:
        return []

    resultados = []
    for item in (data.get("content") or data.get("items") or []):
        preco = safe_float(
            item.get("precoMedio") or item.get("preco_medio") or
            item.get("valorMedio") or item.get("valorReferencia")
        )
        if preco <= 0:
            continue

        descricao = item.get("descricao") or item.get("descricaoItem") or termo
        codigo    = item.get("codigo") or item.get("codigoItem") or ""
        unidade   = item.get("unidadeMedida") or item.get("unidade") or "UN"

        resultados.append({
            "preco":           preco,
            "orgao":           "Painel de Preços (Gov Federal)",
            "esfera":          "Federal",
            "data":            formatar_data(item.get("dataReferencia") or item.get("dataAtualizacao") or ""),
            "descricao":       f"{descricao} (Cód: {codigo})" if codigo else descricao,
            "unidade":         unidade,
            "quantidade":      1,
            "modalidade":      "Preço de Referência",
            "numero_processo": codigo,
            "uf":              "BR",
            "municipio":       "",
            "cnpj_orgao":      "",
            "fonte":           "Painel de Preços",
        })
    return resultados


# ─────────────────────────────────────────────────────────────
#  DEDUPLICAÇÃO
# ─────────────────────────────────────────────────────────────
def deduplicar(resultados: list) -> list:
    vistos, unicos = set(), []
    for r in resultados:
        chave = (r.get("orgao", "")[:30], str(r.get("preco", "")), r.get("descricao", "")[:40])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(r)
    return unicos


# ─────────────────────────────────────────────────────────────
#  ROTAS
# ─────────────────────────────────────────────────────────────
@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html não encontrado"}


@app.get("/buscar")
async def buscar(
    produto:   str   = Query(..., description="Descrição do item"),
    min_preco: float = Query(None, description="Preço mínimo unitário"),
    max_preco: float = Query(None, description="Preço máximo unitário"),
    limite:    int   = Query(40,   description="Máximo de resultados (limite: 100)"),
):
    termo    = produto.strip().lower()
    hoje     = datetime.today()
    data_fim = hoje.strftime("%Y%m%d")
    data_ini = (hoje - timedelta(days=180)).strftime("%Y%m%d")  # últimos 6 meses
    limite   = min(limite, 100)

    tarefas_pncp = [
        (uf, mod, data_ini, data_fim, pag, termo)
        for uf  in UFS
        for mod in MODALIDADES
        for pag in [1, 2]
    ]

    resultados = []

    with ThreadPoolExecutor(max_workers=40) as executor:
        futuros_pncp = {executor.submit(pncp_buscar_pagina, *t): t for t in tarefas_pncp}

        futuro_dados   = executor.submit(compras_dados_buscar, termo)
        futuro_painel  = executor.submit(painel_precos_buscar, termo)
        futuro_global1 = executor.submit(pncp_busca_global, termo, 1)
        futuro_global2 = executor.submit(pncp_busca_global, termo, 2)

        for fut in as_completed(futuros_pncp):
            resultados.extend(fut.result())

        for fut in [futuro_dados, futuro_painel, futuro_global1, futuro_global2]:
            try:
                resultados.extend(fut.result())
            except Exception:
                pass

    if min_preco is not None:
        resultados = [r for r in resultados if r["preco"] >= min_preco]
    if max_preco is not None:
        resultados = [r for r in resultados if r["preco"] <= max_preco]

    unicos = deduplicar(resultados)
    unicos.sort(key=lambda x: x["preco"])
    unicos = unicos[:limite]

    precos = [r["preco"] for r in unicos] if unicos else []
    stats  = {}
    if precos:
        stats = {
            "minimo":  round(min(precos), 2),
            "maximo":  round(max(precos), 2),
            "media":   round(sum(precos) / len(precos), 2),
            "mediana": round(sorted(precos)[len(precos) // 2], 2),
        }

    return {
        "sucesso":     True,
        "total":       len(unicos),
        "stats":       stats,
        "resultados":  unicos,
        "mais_opcoes": unicos,  # retrocompatibilidade
    }


@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "version":   "3.0",
        "fontes":    ["PNCP", "PNCP-Global", "Dados.gov.br", "Painel de Preços"],
        "timestamp": datetime.now().isoformat(),
    }
