from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

@app.get("/")
async def principal():
    caminho = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(caminho) if os.path.exists(caminho) else {"erro": "index.html nao encontrado"}

@app.get("/buscar")
async def buscar(produto: str = Query(...)):
    # URL correta da API pública do PNCP
    url = "https://pncp.gov.br/api/consulta/v1/itens/contrato"

    params = {
        "q": produto,
        "pagina": 1,
        "tamanhoPagina": 20,
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)

        if response.status_code != 200:
            return {"sucesso": False, "erro": f"PNCP retornou status {response.status_code}"}

        dados = response.json()
        itens = dados.get("data", [])

        lista = []
        for item in itens:
            valor = item.get("valorUnitario") or item.get("valorUnitarioEstimado")
            if not valor:
                continue

            lista.append({
                "preco":            float(valor),
                "orgao":            item.get("orgaoEntidade", {}).get("razaoSocial", "Órgão não identificado"),
                "esfera":           "Federal" if item.get("orgaoEntidade", {}).get("esferaId") == "F" else "Estadual/Municipal",
                "data":             formatar_data(item.get("dataAssinatura") or item.get("dataInicio", "")),
                "descricao":        item.get("descricao", produto),
                "unidade":          item.get("unidadeMedida", "UN"),
                "quantidade":       item.get("quantidade", 1),
                "numero_contrato":  item.get("numeroContratoEmpenho", "N/I"),
                "objeto":           item.get("objetoContrato", ""),
                "uf":               item.get("unidadeOrgao", {}).get("ufSigla", ""),
                "municipio":        item.get("unidadeOrgao", {}).get("municipioNome", ""),
            })

        lista.sort(key=lambda x: x["preco"])

        return {"sucesso": True, "total": len(lista), "mais_opcoes": lista}

    except requests.exceptions.Timeout:
        return {"sucesso": False, "erro": "Timeout ao consultar o PNCP."}
    except requests.exceptions.ConnectionError:
        return {"sucesso": False, "erro": "Não foi possível conectar ao PNCP."}
    except Exception as e:
        return {"sucesso": False, "erro": str(e)}


def formatar_data(data_str: str) -> str:
    """Converte 2024-03-15T00:00:00 → 15/03/2024"""
    if not data_str:
        return "N/I"
    try:
        partes = data_str[:10].split("-")
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    except Exception:
        return data_str[:10]
