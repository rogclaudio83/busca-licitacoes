+from datetime import date, timedelta
+import unicodedata
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
-    # URL correta da API pública do PNCP
-    url = "https://pncp.gov.br/api/consulta/v1/itens/contrato"
-
-    params = {
-        "q": produto,
-        "pagina": 1,
-        "tamanhoPagina": 20,
-    }
+    url = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
 
     headers = {
         "User-Agent": "Mozilla/5.0",
         "Accept": "application/json"
     }
 
     try:
-        response = requests.get(url, params=params, headers=headers, timeout=15)
-
-        if response.status_code != 200:
-            return {"sucesso": False, "erro": f"PNCP retornou status {response.status_code}"}
-
-        dados = response.json()
-        itens = dados.get("data", [])
+        hoje = date.today()
+        inicio = hoje - timedelta(days=30)
+
+        modalidades = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
+        itens = []
+
+        for modalidade in modalidades:
+            pagina = 1
+            while pagina <= 3:
+                params = {
+                    # A API de consulta do PNCP espera datas no formato AAAAMMDD
+                    "dataInicial": inicio.strftime("%Y%m%d"),
+                    "dataFinal": hoje.strftime("%Y%m%d"),
+                    "codigoModalidadeContratacao": modalidade,
+                    "pagina": pagina,
+                    "tamanhoPagina": 50,
+                }
+
+                response = requests.get(url, params=params, headers=headers, timeout=15)
+                if response.status_code != 200:
+                    break
+
+                dados = response.json()
+                lote = dados.get("data", [])
+                if not lote:
+                    break
+
+                itens.extend(lote)
+                pagina += 1
 
         lista = []
+        termo = normalizar_texto(produto)
         for item in itens:
+            campos_texto = [
+                item.get("descricao"),
+                item.get("objetoCompra"),
+                item.get("objetoContratacao"),
+                item.get("informacaoComplementar"),
+                item.get("numeroControlePNCP"),
+            ]
+            texto_composto = " ".join(str(campo) for campo in campos_texto if campo)
+            if termo not in normalizar_texto(texto_composto):
+                continue
+
             valor = item.get("valorUnitario") or item.get("valorUnitarioEstimado")
+            if not valor:
+                valor = item.get("valorTotalEstimado") or item.get("valorTotalHomologado")
             if not valor:
                 continue
 
             lista.append({
                 "preco":            float(valor),
                 "orgao":            item.get("orgaoEntidade", {}).get("razaoSocial", "Órgão não identificado"),
                 "esfera":           "Federal" if item.get("orgaoEntidade", {}).get("esferaId") == "F" else "Estadual/Municipal",
-                "data":             formatar_data(item.get("dataAssinatura") or item.get("dataInicio", "")),
-                "descricao":        item.get("descricao", produto),
+                "data":             formatar_data(item.get("dataPublicacaoPncp") or item.get("dataAberturaProposta") or item.get("dataInclusao", "")),
+                "descricao":        item.get("descricao") or item.get("objetoCompra") or item.get("objetoContratacao") or produto,
                 "unidade":          item.get("unidadeMedida", "UN"),
                 "quantidade":       item.get("quantidade", 1),
                 "numero_contrato":  item.get("numeroContratoEmpenho", "N/I"),
-                "objeto":           item.get("objetoContrato", ""),
+                "objeto":           item.get("objetoCompra", ""),
                 "uf":               item.get("unidadeOrgao", {}).get("ufSigla", ""),
                 "municipio":        item.get("unidadeOrgao", {}).get("municipioNome", ""),
             })
 
-        lista.sort(key=lambda x: x["preco"])
+        # remove registros duplicados por órgão + descrição + preço
+        vistos = set()
+        lista_unica = []
+        for registro in lista:
+            chave = (registro["orgao"], registro["descricao"], registro["preco"])
+            if chave in vistos:
+                continue
+            vistos.add(chave)
+            lista_unica.append(registro)
+
+        lista_unica.sort(key=lambda x: x["preco"])
 
-        return {"sucesso": True, "total": len(lista), "mais_opcoes": lista}
+        return {"sucesso": True, "total": len(lista_unica), "mais_opcoes": lista_unica}
 
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
+
+
+def normalizar_texto(texto: str) -> str:
+    texto = (texto or "").lower().strip()
+    texto = unicodedata.normalize("NFKD", texto)
+    return "".join(c for c in texto if not unicodedata.combining(c))
