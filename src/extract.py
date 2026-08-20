import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_FUTEBOL_KEY")
BASE_URL = "https://api.api-futebol.com.br/v1"
CAMPEONATO_ID = 10 # Brasileirão Série A
TOTAL_RODADAS = 38

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

def buscar_rodada(numero_rodada):
    url = f"{BASE_URL}/campeonatos/{CAMPEONATO_ID}/rodadas/{numero_rodada}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Erro na rodada {numero_rodada}: status {response.status_code}")
        return None

def main():
    todas_rodadas = []

    for rodada in range(1, TOTAL_RODADAS + 1):
        print(f"Buscando rodada {rodada}/{TOTAL_RODADAS}...")
        dados = buscar_rodada(rodada)

        if dados:
            todas_rodadas.append(dados)

        time.sleep(0.5) # evita sobrecarregar a API

    caminho_saida = "data/raw/brasileirao_2026_rodadas.json"
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(todas_rodadas, f, ensure_ascii=False, indent=2)

    print(f"\nConcluído! {len(todas_rodadas)} rodadas salvas em {caminho_saida}")

if __name__ == "__main__":
    main()