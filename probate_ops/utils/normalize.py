import io, os, pandas as pd, re

ALIASES = {
    "county": "county",
    "source url": "source_url",
    "case no": "case_no",
    "decedent": "decedent",
    "street address": "street_address",
    "city": "city",
    "state": "state",
    "zip code": "zip",
    "death date": "death_date",
    "party": "party",
    "party street address": "party_street_address",
    "party city": "party_city",
    "party state": "party_state",
    "party zip code": "party_zip",
    "petition type": "petition_type",
    "petition date": "petition_date",
}


def read_table(bytes_: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in [".csv", ".txt"]:
        return pd.read_csv(io.BytesIO(bytes_))
    return pd.read_excel(io.BytesIO(bytes_))


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    orig = list(df.columns)
    low = [str(c).strip().lower() for c in orig]
    ren = {orig[i]: ALIASES.get(low[i], low[i]) for i in range(len(orig))}
    df = df.rename(columns=ren)
    for c in ALIASES.values():
        if c not in df.columns:
            df[c] = None
    df["zip"] = df["zip"].astype(str).str.extract(r"(\d{5})")[0]
    df["party_zip"] = df["party_zip"].astype(str).str.extract(r"(\d{5})")[0]
    df["property_address"] = df["street_address"]
    df["owner_name"] = df["decedent"]
    df["mailing_address"] = (
        (
            df["party_street_address"].fillna("").astype(str).str.strip()
            + ", "
            + df["party_city"].fillna("").astype(str).str.strip()
            + ", "
            + df["party_state"].fillna("").astype(str).str.strip()
            + " "
            + df["party_zip"].fillna("").astype(str)
        )
        .str.replace(r",\s*,", ", ", regex=True)
        .str.strip(", ")
        .str.strip()
    )
    df["death_date"] = pd.to_datetime(df["death_date"], errors="coerce")
    df["petition_date"] = pd.to_datetime(df["petition_date"], errors="coerce")

    # features
    td = pd.Timestamp.today().normalize()
    df["absentee_flag"] = (
        df["party_city"].str.lower() != df["city"].str.lower()
    ) | (df["party_zip"] != df["zip"])
    df["days_since_death"] = (
        (td - df["death_date"]).dt.days.fillna(9999).astype(int)
    )
    df["days_since_petition"] = (
        (td - df["petition_date"]).dt.days.fillna(9999).astype(int)
    )
    key = (
        df["owner_name"].fillna("").str.lower().str.strip()
        + "|"
        + df["party_zip"].fillna("")
    )
    df["holdings_in_file"] = key.map(key.value_counts()).fillna(1).astype(int)
    return df
