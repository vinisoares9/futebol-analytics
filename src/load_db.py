import os
import json
import mysql.connector
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

def conectar():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=MYSQL_PASSWORD,
        database="futebol_analytics"
    )

def carregar_json():
    with open("data/raw/brasileirao_2026_rodadas.json", encoding="utf-8") as f:
        return json.load(f)

def inserir_time(cursor, time):
    sql = """
        INSERT INTO times (time_id, nome_popular, sigla, escudo_url)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE nome_popular = VALUES(nome_popular)
    """
    valores = (time["time_id"], time["nome_popular"], time["sigla"], time.get("escudo"))
    cursor.execute(sql, valores)

def converter_data(data_str):
    if not data_str:
        return None
    try:
        data_convertida = datetime.strptime(data_str, "%d/%m/%Y")
        return data_convertida.strftime("%Y-%m-%d")
    except ValueError:
        return None

def inserir_partida(cursor, partida, rodada_numero):
    sql = """
        INSERT INTO partidas (
            partida_id, rodada, time_mandante_id, time_visitante_id,
            placar_mandante, placar_visitante, status, data_realizacao
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            placar_mandante = VALUES(placar_mandante),
            placar_visitante = VALUES(placar_visitante),
            status = VALUES(status)
    """
    valores = (
        partida["partida_id"],
        rodada_numero,
        partida["time_mandante"]["time_id"],
        partida["time_visitante"]["time_id"],
        partida.get("placar_mandante"),
        partida.get("placar_visitante"),
        partida.get("status"),
        converter_data(partida.get("data_realizacao"))
    )
    cursor.execute(sql, valores)

def main():
    dados = carregar_json()
    conexao = conectar()
    cursor = conexao.cursor()

    times_inseridos = set()
    total_partidas = 0

    for rodada in dados:
        numero_rodada = rodada["rodada"]

        for partida in rodada["partidas"]:
            # Insere os dois times da partida, se ainda não inseridos
            for lado in ["time_mandante", "time_visitante"]:
                time = partida[lado]
                if time["time_id"] not in times_inseridos:
                    inserir_time(cursor, time)
                    times_inseridos.add(time["time_id"])

            inserir_partida(cursor, partida, numero_rodada)
            total_partidas += 1

    conexao.commit()
    cursor.close()
    conexao.close()

    print(f"Concluído! {len(times_inseridos)} times e {total_partidas} partidas carregados no banco.")

if __name__ == "__main__":
    main()