from openai import OpenAI
import json
import os
import sys

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def analyze_atti(atti):
    prompt = f"""
Sei un esperto di trasporto marittimo e policy industriale.

Analizza questi atti della Gazzetta Ufficiale e restituisci SOLO quelli rilevanti per Confitarma.

Classifica ogni atto in UNA categoria:
- trasporto marittimo
- industria trasporti
- industria generale

Per ogni atto restituisci:
- titolo sintetico
- categoria
- motivazione breve
- parole chiave

Se nessun atto è rilevante, scrivi solo:
NESSUN ATTO RILEVANTE

Atti:
{json.dumps(atti, ensure_ascii=False)}
"""

    response = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content


if __name__ == "__main__":
    try:
        test_atti = [
            {
                "raw_text": "Disposizioni per l'implementazione dell'approccio equilibrato negli aeroporti nazionali in applicazione del regolamento (UE) 598/2014."
            },
            {
                "raw_text": "Decisione di esecuzione (UE) 2026/335 della Commissione, che istituisce l'elenco dei paesi terzi esentati dall'autorizzazione preventiva per le importazioni di gas nell'Unione."
            }
        ]

        result = analyze_atti(test_atti)

        if result is None:
            print("ERRORE: result is None")
            sys.exit(1)

        result = str(result).strip()

        if not result:
            print("ERRORE: risposta AI vuota")
            sys.exit(1)

        print(result)

    except Exception as e:
        print(f"ERRORE analyze_gazzetta_ai.py: {type(e).__name__}: {e}")
        sys.exit(1)