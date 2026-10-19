"""
Baixa o histórico do Campeonato Brasileiro Série A (2003-2024).

Fonte: repositório público Brasileirao_Dataset (github.com/adaoduque/Brasileirao_Dataset).
Esses dados complementam a API de 2026, que tem poucas partidas para treinar um modelo.
"""
import os
import requests

URL_HISTORICO = (
    "https://raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/"
    "master/campeonato-brasileiro-full.csv"
)
CAMINHO_SAIDA = "data/raw/historico_brasileirao.csv"


def main():
    print("Baixando histórico do Brasileirão...")
    resposta = requests.get(URL_HISTORICO, timeout=60)
    resposta.raise_for_status()

    os.makedirs(os.path.dirname(CAMINHO_SAIDA), exist_ok=True)
    with open(CAMINHO_SAIDA, "wb") as f:
        f.write(resposta.content)

    linhas = resposta.content.count(b"\n") - 1  # desconta o cabeçalho
    print(f"Concluído! ~{linhas} partidas salvas em {CAMINHO_SAIDA}")


if __name__ == "__main__":
    main()
