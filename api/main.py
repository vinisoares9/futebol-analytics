import os
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
engine = create_engine(f"mysql+mysqlconnector://root:{MYSQL_PASSWORD}@localhost/futebol_analytics")

modelo = joblib.load("api/modelo_resultado.pkl")

app = FastAPI(title="API de Previsão - Brasileirão 2026")


class PrevisaoRequest(BaseModel):
    time_mandante_id: int
    time_visitante_id: int


def calcular_forma_time(time_id: int):
    query = f"""
        select p.rodada, p.placar_mandante, p.placar_visitante,
               p.time_mandante_id, p.time_visitante_id
        from partidas p
        where p.status = 'finalizado'
          and (p.time_mandante_id = {time_id} or p.time_visitante_id = {time_id})
        order by p.rodada desc
        limit 5
    """
    df = pd.read_sql(query, engine)

    if df.empty:
        return None

    pontos_lista = []
    gols_feitos_lista = []
    gols_sofridos_lista = []

    for _, row in df.iterrows():
        if row['time_mandante_id'] == time_id:
            gols_feitos = row['placar_mandante']
            gols_sofridos = row['placar_visitante']
        else:
            gols_feitos = row['placar_visitante']
            gols_sofridos = row['placar_mandante']

        if gols_feitos > gols_sofridos:
            pontos = 3
        elif gols_feitos == gols_sofridos:
            pontos = 1
        else:
            pontos = 0

        pontos_lista.append(pontos)
        gols_feitos_lista.append(gols_feitos)
        gols_sofridos_lista.append(gols_sofridos)

    return {
        "media_pontos_5j": sum(pontos_lista) / len(pontos_lista),
        "media_gols_feitos_5j": sum(gols_feitos_lista) / len(gols_feitos_lista),
        "media_gols_sofridos_5j": sum(gols_sofridos_lista) / len(gols_sofridos_lista)
    }


@app.get("/")
def raiz():
    return {"mensagem": "API de Previsão do Brasileirão 2026 está no ar"}


@app.post("/prever")
def prever_resultado(req: PrevisaoRequest):
    forma_mandante = calcular_forma_time(req.time_mandante_id)
    forma_visitante = calcular_forma_time(req.time_visitante_id)

    if forma_mandante is None or forma_visitante is None:
        raise HTTPException(status_code=404, detail="Não há histórico suficiente para um dos times informados.")

    features = pd.DataFrame([{
        "mandante_media_pontos_5j": forma_mandante["media_pontos_5j"],
        "mandante_media_gols_feitos_5j": forma_mandante["media_gols_feitos_5j"],
        "mandante_media_gols_sofridos_5j": forma_mandante["media_gols_sofridos_5j"],
        "visitante_media_pontos_5j": forma_visitante["media_pontos_5j"],
        "visitante_media_gols_feitos_5j": forma_visitante["media_gols_feitos_5j"],
        "visitante_media_gols_sofridos_5j": forma_visitante["media_gols_sofridos_5j"]
    }])

    previsao = modelo.predict(features)[0]
    probabilidades = modelo.predict_proba(features)[0]
    classes = modelo.classes_

    return {
        "previsao": previsao,
        "probabilidades": {classe: round(float(prob), 3) for classe, prob in zip(classes, probabilidades)}
    }

