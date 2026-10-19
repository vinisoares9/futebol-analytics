import os
import subprocess
import sys
from pathlib import Path

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parent.parent
sys.path.append(str(RAIZ / "src"))

from features import calcular_features, carregar_partidas, normalizar_nome  # noqa: E402

load_dotenv(RAIZ / ".env")

MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
engine = (
    create_engine(f"mysql+mysqlconnector://root:{MYSQL_PASSWORD}@localhost/futebol_analytics")
    if MYSQL_PASSWORD else None
)

# O arquivo salvo pelo notebook guarda o modelo, as features usadas e os parâmetros do Elo
artefato = joblib.load(RAIZ / "api/modelo_resultado.pkl")
modelo = artefato["modelo"]
FEATURES = artefato["features"]
PARAMETROS_ELO = artefato["parametros_elo"]

app = FastAPI(title="API de Previsão - Brasileirão 2026")

# Estado atual dos times (Elo e forma), recalculado ao iniciar e após cada atualização
contexto = {}


def recalcular_estado():
    """Processa todas as partidas em ordem de data, com o mesmo código usado no treino."""
    partidas = carregar_partidas(engine, caminho_csv=RAIZ / "data/processed/partidas.csv")
    _, estado = calcular_features(partidas, PARAMETROS_ELO)

    times_2026 = partidas[partidas["fonte"] == "api_2026"]
    nomes = pd.concat([
        times_2026[["mandante_id", "mandante"]].set_axis(["time_id", "nome"], axis=1),
        times_2026[["visitante_id", "visitante"]].set_axis(["time_id", "nome"], axis=1),
    ]).drop_duplicates("time_id")

    contexto["estado"] = estado
    contexto["times"] = {int(r.time_id): r.nome for r in nomes.itertuples()}


recalcular_estado()


class PrevisaoRequest(BaseModel):
    time_mandante_id: int
    time_visitante_id: int


@app.get("/")
def raiz():
    return {"mensagem": "API de Previsão do Brasileirão 2026 está no ar"}


@app.get("/times")
def listar_times():
    """Lista os times de 2026 com o ID usado em /prever e o rating Elo atual."""
    estado = contexto["estado"]
    times = [
        {"time_id": time_id, "nome": nome, "elo": round(estado.rating(normalizar_nome(nome)), 1)}
        for time_id, nome in contexto["times"].items()
    ]
    return sorted(times, key=lambda t: t["elo"], reverse=True)


@app.post("/prever")
def prever_resultado(req: PrevisaoRequest):
    times = contexto["times"]
    if req.time_mandante_id not in times or req.time_visitante_id not in times:
        raise HTTPException(status_code=404, detail="Time não encontrado. Consulte os IDs em GET /times.")
    if req.time_mandante_id == req.time_visitante_id:
        raise HTTPException(status_code=400, detail="Mandante e visitante devem ser times diferentes.")

    mandante = times[req.time_mandante_id]
    visitante = times[req.time_visitante_id]

    todas = contexto["estado"].features(normalizar_nome(mandante), normalizar_nome(visitante))
    entrada = pd.DataFrame([{f: todas[f] for f in FEATURES}])

    previsao = modelo.predict(entrada)[0]
    probabilidades = modelo.predict_proba(entrada)[0]

    return {
        "mandante": mandante,
        "visitante": visitante,
        "previsao": previsao,
        "probabilidades": {
            classe: round(float(prob), 3) for classe, prob in zip(modelo.classes_, probabilidades)
        },
        "features": {f: round(float(v), 3) for f, v in entrada.iloc[0].items()},
    }


@app.post("/atualizar-dados")
def atualizar_dados():
    try:
        etapas = {}
        for nome, script in [("extracao", "src/extract.py"), ("carga", "src/load_db.py")]:
            resultado = subprocess.run(
                [sys.executable, script], capture_output=True, text=True, timeout=300, cwd=RAIZ
            )
            if resultado.returncode != 0:
                raise HTTPException(status_code=500, detail=f"Erro na {nome}: {resultado.stderr[-500:]}")
            etapas[nome] = resultado.stdout[-500:]

        recalcular_estado()

        return {
            "status": "sucesso",
            "mensagem": "Dados atualizados e ratings recalculados",
            "detalhes_extracao": etapas["extracao"],
            "detalhes_carga": etapas["carga"],
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Tempo limite excedido ao atualizar os dados")
