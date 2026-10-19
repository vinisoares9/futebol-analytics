"""
Funções compartilhadas de dados e features.

Este módulo é usado tanto pelo notebook de modelagem quanto pela API. Assim, as
features calculadas no treino e na previsão são exatamente as mesmas (evita o
problema de "o modelo treinou com uma conta e a API faz outra").

Regra principal: as partidas são processadas em ORDEM CRONOLÓGICA (pela data), e as
features de cada jogo usam apenas informações de jogos anteriores a ele.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
import unicodedata

import numpy as np
import pandas as pd

CAMINHO_PARTIDAS_CSV = "data/processed/partidas.csv"

# Nomes que mudam entre as fontes (já normalizados: minúsculas e sem acento)
APELIDOS = {
    "botafogo-rj": "botafogo",
}

# Todas as features que o módulo calcula. O modelo salvo guarda quais delas usa.
TODAS_FEATURES = [
    "elo_diff",
    "mandante_pontos_5j", "visitante_pontos_5j",
    "mandante_saldo_5j", "visitante_saldo_5j",
    "mandante_pontos_casa_5j", "visitante_pontos_fora_5j",
]

# Valores neutros para o começo de cada temporada, quando o time ainda não jogou
PONTOS_NEUTRO = 1.4  # média aproximada de pontos por jogo no Brasileirão
SALDO_NEUTRO = 0.0


def normalizar_nome(nome: str) -> str:
    """'Grêmio' -> 'gremio', 'Botafogo-RJ' -> 'botafogo'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    chave = sem_acento.lower().strip()
    return APELIDOS.get(chave, chave)


def resultado_partida(placar_mandante, placar_visitante) -> str:
    if placar_mandante > placar_visitante:
        return "vitoria_mandante"
    if placar_mandante < placar_visitante:
        return "vitoria_visitante"
    return "empate"


# --------------------------------------------------------------------------- #
# Carga de dados
# --------------------------------------------------------------------------- #
SQL_PARTIDAS_2026 = """
    SELECT p.partida_id, p.rodada, p.data_realizacao, p.status,
           p.time_mandante_id AS mandante_id, tm.nome_popular AS mandante,
           p.time_visitante_id AS visitante_id, tv.nome_popular AS visitante,
           p.placar_mandante, p.placar_visitante
    FROM partidas p
    JOIN times tm ON p.time_mandante_id = tm.time_id
    JOIN times tv ON p.time_visitante_id = tv.time_id
"""

SQL_PARTIDAS_HISTORICO = """
    SELECT partida_hist_id AS partida_id, temporada, rodada, data_realizacao,
           mandante, visitante, placar_mandante, placar_visitante
    FROM partidas_historico
"""


def carregar_partidas(engine=None, caminho_csv: str = CAMINHO_PARTIDAS_CSV) -> pd.DataFrame:
    """
    Junta as duas fontes (histórico + 2026) num formato único.

    Lê do MySQL quando um `engine` é informado e o banco responde. Caso contrário,
    usa o CSV versionado em data/processed/ (permite rodar o projeto sem MySQL).
    """
    if engine is not None:
        try:
            atual = pd.read_sql(SQL_PARTIDAS_2026, engine)
            historico = pd.read_sql(SQL_PARTIDAS_HISTORICO, engine)
            return _padronizar(historico, atual)
        except Exception as erro:  # banco desligado, tabela ausente etc.
            print(f"Aviso: não foi possível ler o MySQL ({erro.__class__.__name__}). Usando {caminho_csv}.")

    df = pd.read_csv(caminho_csv, parse_dates=["data_realizacao"])
    return df


def _padronizar(historico: pd.DataFrame, atual: pd.DataFrame) -> pd.DataFrame:
    historico = historico.assign(
        fonte="historico", status="finalizado", mandante_id=pd.NA, visitante_id=pd.NA
    )
    atual = atual.assign(fonte="api_2026", temporada=2026)

    df = pd.concat([historico, atual], ignore_index=True)
    df["data_realizacao"] = pd.to_datetime(df["data_realizacao"])
    df["mandante_norm"] = df["mandante"].map(normalizar_nome)
    df["visitante_norm"] = df["visitante"].map(normalizar_nome)

    colunas = [
        "fonte", "temporada", "rodada", "partida_id", "data_realizacao", "status",
        "mandante_id", "mandante", "mandante_norm",
        "visitante_id", "visitante", "visitante_norm",
        "placar_mandante", "placar_visitante",
    ]
    return df[colunas].sort_values(["data_realizacao", "fonte", "partida_id"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Features: rating Elo + forma recente
# --------------------------------------------------------------------------- #
@dataclass
class ParametrosElo:
    k: float = 20.0                 # quanto um resultado move o rating
    vantagem_casa: float = 60.0     # pontos de Elo somados ao mandante
    regressao_temporada: float = 0.25  # fração puxada de volta à média entre temporadas
    elo_inicial: float = 1500.0
    elo_novato: float = 1450.0      # time que aparece pela 1ª vez (geralmente recém-promovido)


@dataclass
class EstadoTimes:
    """Situação de cada time depois do último jogo processado (usado pela API)."""
    parametros: ParametrosElo
    elo: dict = field(default_factory=dict)
    temporada: int | None = None
    temporadas_processadas: int = 0
    forma: dict = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=5)))
    forma_casa: dict = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=5)))
    forma_fora: dict = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=5)))

    def rating(self, time: str) -> float:
        if time not in self.elo:
            # Na 1ª temporada todos começam iguais; depois disso, um time novo
            # normalmente é recém-promovido e começa abaixo da média.
            primeira = self.temporadas_processadas <= 1
            self.elo[time] = self.parametros.elo_inicial if primeira else self.parametros.elo_novato
        return self.elo[time]

    def iniciar_temporada(self, temporada: int):
        """Entre temporadas, os ratings voltam um pouco para a média e a forma zera."""
        if self.temporada is not None and temporada != self.temporada:
            fator = self.parametros.regressao_temporada
            media = self.parametros.elo_inicial
            self.elo = {t: r + fator * (media - r) for t, r in self.elo.items()}
            self.forma.clear()
            self.forma_casa.clear()
            self.forma_fora.clear()
        if temporada != self.temporada:
            self.temporadas_processadas += 1
        self.temporada = temporada

    def features(self, mandante: str, visitante: str) -> dict:
        """Features de um jogo usando só o que aconteceu ANTES dele."""
        def media(fila, idx, neutro):
            return float(np.mean([j[idx] for j in fila])) if fila else neutro

        return {
            "elo_diff": self.rating(mandante) - self.rating(visitante),
            "mandante_pontos_5j": media(self.forma[mandante], 0, PONTOS_NEUTRO),
            "visitante_pontos_5j": media(self.forma[visitante], 0, PONTOS_NEUTRO),
            "mandante_saldo_5j": media(self.forma[mandante], 1, SALDO_NEUTRO),
            "visitante_saldo_5j": media(self.forma[visitante], 1, SALDO_NEUTRO),
            "mandante_pontos_casa_5j": media(self.forma_casa[mandante], 0, PONTOS_NEUTRO),
            "visitante_pontos_fora_5j": media(self.forma_fora[visitante], 0, PONTOS_NEUTRO),
        }

    def registrar_resultado(self, mandante: str, visitante: str, gols_m: int, gols_v: int):
        p = self.parametros
        r_m, r_v = self.rating(mandante), self.rating(visitante)

        esperado_m = 1 / (1 + 10 ** (-(r_m + p.vantagem_casa - r_v) / 400))
        real_m = 1.0 if gols_m > gols_v else 0.5 if gols_m == gols_v else 0.0
        # vitórias por placar largo movem mais o rating
        multiplicador = np.log(abs(gols_m - gols_v) + 1) + 1
        ajuste = p.k * multiplicador * (real_m - esperado_m)
        self.elo[mandante] = r_m + ajuste
        self.elo[visitante] = r_v - ajuste

        pts_m = 3 if gols_m > gols_v else 1 if gols_m == gols_v else 0
        pts_v = 3 if gols_v > gols_m else 1 if gols_m == gols_v else 0
        self.forma[mandante].append((pts_m, gols_m - gols_v))
        self.forma[visitante].append((pts_v, gols_v - gols_m))
        self.forma_casa[mandante].append((pts_m, gols_m - gols_v))
        self.forma_fora[visitante].append((pts_v, gols_v - gols_m))


def calcular_features(partidas: pd.DataFrame, parametros: ParametrosElo | None = None,
                      temporada_inicial: int = 2012):
    """
    Percorre as partidas finalizadas em ordem de data e devolve:
      - um DataFrame com uma linha por partida, as features e o resultado;
      - o EstadoTimes final (ratings e forma atuais), usado para prever jogos futuros.

    `temporada_inicial` define a partir de quando o Elo começa a ser calculado.
    Começar alguns anos antes do período de treino dá tempo do rating "aquecer".
    """
    parametros = parametros or ParametrosElo()
    estado = EstadoTimes(parametros)

    jogos = partidas[
        (partidas["status"] == "finalizado")
        & (partidas["temporada"] >= temporada_inicial)
        & partidas["data_realizacao"].notna()
    ].sort_values(["data_realizacao", "fonte", "partida_id"])

    linhas = []
    for jogo in jogos.itertuples(index=False):
        estado.iniciar_temporada(jogo.temporada)
        feats = estado.features(jogo.mandante_norm, jogo.visitante_norm)
        linhas.append({
            "fonte": jogo.fonte,
            "temporada": jogo.temporada,
            "partida_id": jogo.partida_id,
            "data_realizacao": jogo.data_realizacao,
            "mandante": jogo.mandante,
            "visitante": jogo.visitante,
            "placar_mandante": int(jogo.placar_mandante),
            "placar_visitante": int(jogo.placar_visitante),
            **feats,
            "resultado": resultado_partida(jogo.placar_mandante, jogo.placar_visitante),
        })
        estado.registrar_resultado(
            jogo.mandante_norm, jogo.visitante_norm,
            int(jogo.placar_mandante), int(jogo.placar_visitante),
        )

    return pd.DataFrame(linhas), estado
