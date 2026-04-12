from openai import OpenAI
import json

client = OpenAI()


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
- motivazione (breve)
- parole chiave

Atti:
{json.dumps(atti, ensure_ascii=False)}
"""

    response = client.chat.completions.create(
        model="gpt-5-3",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return response.choices[0].message.content