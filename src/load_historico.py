"""
Carrega o histórico do Brasileirão (data/raw/historico_brasileirao.csv) na tabela
partidas_historico do MySQL. Pode ser executado várias vezes sem duplicar dados.
"""
import os
import pandas as pd
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
CAMINHO_CSV = "data/raw/historico_brasileirao.csv"

SQL_CRIAR_TABELA = """
    CREATE TABLE IF NOT EXISTS partidas_historico (
        partida_hist_id   INT PRIMARY KEY,
        temporada         INT NOT NULL,
        rodada            INT NOT NULL,
        data_realizacao   DATE NOT NULL,
        mandante          VARCHAR(60) NOT NULL,
        visitante         VARCHAR(60) NOT NULL,
        placar_mandante   INT NOT NULL,
        placar_visitante  INT NOT NULL,
        INDEX idx_temporada (temporada),
        INDEX idx_data (data_realizacao)
    )
"""

SQL_INSERIR = """
    INSERT INTO partidas_historico (
        partida_hist_id, temporada, rodada, data_realizacao,
        mandante, visitante, placar_mandante, placar_visitante
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        temporada = VALUES(temporada),
        data_realizacao = VALUES(data_realizacao),
        placar_mandante = VALUES(placar_mandante),
        placar_visitante = VALUES(placar_visitante)
"""


def preparar_dados():
    df = pd.read_csv(CAMINHO_CSV).sort_values("ID").reset_index(drop=True)

    # O CSV não tem coluna de temporada. Como os IDs seguem a ordem dos jogos,
    # uma nova temporada começa quando a rodada "volta" (ex.: de 38 para 1).
    # Usar o ano da data não funciona: a temporada 2020 terminou em fevereiro de 2021.
    nova_temporada = df["rodata"].diff() < -20
    df["temporada"] = 2003 + nova_temporada.cumsum()

    df["data_realizacao"] = pd.to_datetime(df["data"], dayfirst=True).dt.strftime("%Y-%m-%d")

    return df[[
        "ID", "temporada", "rodata", "data_realizacao",
        "mandante", "visitante", "mandante_Placar", "visitante_Placar",
    ]]


def main():
    df = preparar_dados()

    conexao = mysql.connector.connect(
        host="localhost", user="root", password=MYSQL_PASSWORD, database="futebol_analytics"
    )
    cursor = conexao.cursor()
    cursor.execute(SQL_CRIAR_TABELA)

    linhas = [tuple(int(v) if i not in (3, 4, 5) else v for i, v in enumerate(row))
              for row in df.itertuples(index=False)]
    cursor.executemany(SQL_INSERIR, linhas)

    conexao.commit()
    cursor.close()
    conexao.close()

    print(f"Concluído! {len(linhas)} partidas históricas carregadas "
          f"({df['temporada'].min()}-{df['temporada'].max()}).")


if __name__ == "__main__":
    main()
