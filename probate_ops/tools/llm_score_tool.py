import os, json
from openai import OpenAI
from ..core.settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM = (
    "Score probate leads for real estate acquisitions. "
    "Return STRICT JSON: {score:0-100, tier:'high'|'medium'|'low', rationale:string}. "
    "Prefer absentee owners, older petitions, multiple holdings; penalize missing address."
)


def score_llm(record: dict) -> dict:
    minimal = {
        "owner_name": record.get("owner_name"),
        "property_address": record.get("property_address"),
        "city": record.get("city"),
        "state": record.get("state"),
        "zip": record.get("zip"),
        "petition_type": record.get("petition_type"),
        "absentee_flag": bool(record.get("absentee_flag")),
        "days_since_death": int(record.get("days_since_death")),
        "days_since_petition": int(record.get("days_since_petition")),
        "holdings_in_file": int(record.get("holdings_in_file")),
        "county": record.get("county"),
    }
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Record: {minimal}"},
        ],
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"score": 50, "tier": "medium", "rationale": "Fallback parse."}
