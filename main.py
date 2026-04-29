from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from datetime import datetime, timedelta
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

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}


@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    """
    Busca contratos no PNCP que contenham o termo do produto.
    Estratégia: busca contratações dos últimos 90 dias e filtra pelo termo.
    """
    termo = produto.strip().lower()
    resultados = []

    # Busca nos últimos 90 dias em janelas de 30 dias
    hoje = datetime.today()
    janelas = [
        (hoje - timedelta(days=30),  hoje),
        (hoje - timedelta(days=60),  hoje - timedelta(days=30)),
        (hoje - timedelta(days=90),  hoje - timedelta(days=60)),
    ]

    for data_ini, data_fim in janelas:
        if len(resultados) >= 20:
            break

        data_ini_str = data_ini.strftime("%Y%m%d")
        data_fim_str = data_fim.strftime("%Y%m%d")

        # Busca contratações publicadas no período
        url = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
        params = {
            "dataInicial": data_ini_str,
            "dataFinal":   data_fim_str,
            "pagina":      1,
            "tamanhoPagina": 50,
        }

        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                continue

            dados = resp.json()
            contratacoes = dados.get("data", [])

            for c in contratacoes:
                objeto = (c.get("objetoCompra") or "").lower()
                descricao = (c.get("informacaoComplementar") or "").lower()

                # Filtra pelo termo buscado
                if termo not in objeto and termo not in descricao:
                    continue

                valor = c.get("valorTotalEstimado") or c.get("valorTotalHomologado")
                if not valor or float(valor) <= 0:
                    continue

                orgao = (
                    c.get("orgaoEntidade", {}).get("razaoSocial")
                    or c.get("unidadeOrgao", {}).get("nomeUnidade")
                    or "Órgão não identificado"
                )

                esfera_cod = c.get("orgaoEntidade", {}).get("esferaId", "")
                esfera_map = {"F": "Federal", "E": "Estadual", "M": "Municipal"}
                esfera = esfera_map.get(esfera_cod, esfera_cod or "N/I")

                resultados.append({
                    "preco":           round(float(valor), 2),
                    "orgao":           orgao,
                    "esfera":          esfera,
                    "data":            formatar_data(c.get("dataPublicacaoGlobal") or c.get("dataAberturaProposta", "")),
                    "descricao":       c.get("objetoCompra", produto),
                    "modalidade":      c.get("modalidadeNome", "N/I"),
                    "numero_processo": c.get("numeroCompra") or c.get("processo", "N/I"),
                    "uf":              c.get("unidadeOrgao", {}).get("ufSigla", ""),
                    "municipio":       c.get("unidadeOrgao", {}).get("municipioNome", ""),
                    "link":            c.get("linkSistemaOrigem", ""),
                })

        except Exception:
            continue

    if not resultados:
        # Segunda tentativa: busca por palavra-chave no objeto da contratação (endpoint alternativo)
        try:
            url2 = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
            params2 = {
                "dataInicial":   (hoje - timedelta(days=180)).strftime("%Y%m%d"),
                "dataFinal":     hoje.strftime("%Y%m%d"),
                "pagina":        1,
                "tamanhoPagina": 50,
            }
            resp2 = requests.get(url2, params=params2, headers=HEADERS, timeout=20)
            if resp2.status_code == 200:
                for c in resp2.json().get("data", []):
                    objeto = (c.get("objetoCompra") or "").lower()
                    if termo not in objeto:
                        continue
                    valor = c.get("valorTotalEstimado") or c.get("valorTotalHomologado")
                    if not valor or float(valor) <= 0:
                        continue
                    resultados.append({
                        "preco":           round(float(valor), 2),
                        "orgao":           c.get("orgaoEntidade", {}).get("razaoSocial", "N/I"),
                        "esfera":          c.get("orgaoEntidade", {}).get("esferaId", "N/I"),
                        "data":            formatar_data(c.get("dataAberturaProposta", "")),
                        "descricao":       c.get("objetoCompra", produto),
                        "modalidade":      c.get("modalidadeNome", "N/I"),
                        "numero_processo": c.get("numeroCompra", "N/I"),
                        "uf":              c.get("unidadeOrgao", {}).get("ufSigla", ""),
                        "municipio":       c.get("unidadeOrgao", {}).get("municipioNome", ""),
                        "link":            c.get("linkSistemaOrigem", ""),
                    })
        except Exception:
            pass

    # Ordena pelo menor preço e limita a 20
    resultados.sort(key=lambda x: x["preco"])
    resultados = resultados[:20]

    return {
        "sucesso": True,
        "total":   len(resultados),
        "mais_opcoes": resultados
    }


def formatar_data(data_str: str) -> str:
    if not data_str:
        return "N/I"
    try:
        partes = data_str[:10].split("-")
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    except Exception:
        return data_str[:10]


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
