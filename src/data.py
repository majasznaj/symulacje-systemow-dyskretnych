"""Kroki 3 i 4: strumień ciężarówek z Excela i mapowanie odbiorców na huby."""
import re
import pandas as pd

import config


def _read_sheet0(path):
    df = pd.read_excel(path, sheet_name=0)
    return df.dropna(axis=1, how="all").dropna(how="all")


def _month_bounds(month):
    start = pd.Timestamp(f"{month}-01")
    return start, start + pd.offsets.MonthBegin(1)


def prepare_trucks(month):
    """Received -> jedna ciężarówka na wiersz, tylko wybrany miesiąc."""
    df = _read_sheet0(config.RECEIVED_XLSX)
    start, end = _month_bounds(month)
    df = df[(df["Received Date"] >= start) & (df["Received Date"] < end)].copy()
    df["crossing"] = df["Crossing"].replace(config.CROSSING_ALIASES)
    unknown = set(df["crossing"]) - set(config.CROSSINGS)
    if unknown:
        raise ValueError(f"Przejścia spoza config.CROSSINGS: {unknown}")
    # jeden wiersz = jedna ciężarówka (kolumna 'No. of Trucks' ma same jedynki)
    assert (df["No. of Trucks"] == 1).all(), "Są wiersze z liczbą ciężarówek != 1"
    out = pd.DataFrame({
        "truck_id": df["ID"].astype(int),
        "date": df["Received Date"].dt.normalize(),
        "crossing": df["crossing"],
        "category": df["Cargo Category"],
        "quantity": df["Quantity"],
        "unit": df["Units"],
    }).sort_values(["date", "truck_id"]).reset_index(drop=True)
    return out


def map_hub(name):
    s = str(name).lower()
    for hub, pattern in config.HUB_RULES:
        if re.search(pattern, s):
            return hub
    return None


def prepare_hub_mapping(month):
    """Dispatching -> tabela nazwa odbiorcy -> hub (z liczbą wierszy) oraz udziały hubów."""
    df = _read_sheet0(config.DISPATCH_XLSX)
    start, end = _month_bounds(month)
    df = df[(df["Date Dispatch"] >= start) & (df["Date Dispatch"] < end)].copy()
    col = "Destination Recipient/ partner"
    names = df[col].value_counts().rename_axis("destination").reset_index(name="rows")
    names["hub"] = names["destination"].map(map_hub)
    mapped = names.dropna(subset=["hub"])
    shares = (mapped.groupby("hub")["rows"].sum() / mapped["rows"].sum()).rename("share")
    shares = shares.reindex(list(config.HUBS)).fillna(0.0)
    shares = shares[shares > 0]
    return names, shares


def prepare(month=None, force=False):
    """Zapisuje data/processed/{trucks,hub_mapping,hub_shares}_<miesiąc>.csv i zwraca (trucks, shares)."""
    month = month or config.MONTH
    config.DATA_PROC.mkdir(parents=True, exist_ok=True)
    f_trucks = config.DATA_PROC / f"trucks_{month}.csv"
    f_map = config.DATA_PROC / f"hub_mapping_{month}.csv"
    f_shares = config.DATA_PROC / f"hub_shares_{month}.csv"
    if f_trucks.exists() and f_shares.exists() and not force:
        return load_prepared(month)

    trucks = prepare_trucks(month)
    names, shares = prepare_hub_mapping(month)
    trucks.to_csv(f_trucks, index=False)
    names.to_csv(f_map, index=False)
    shares.to_csv(f_shares)

    n_rows = int(names["rows"].sum())
    n_map = int(names.dropna(subset=["hub"])["rows"].sum())
    print(f"Ciężarówki {month}: {len(trucks)} wierszy, {trucks['date'].nunique()} dni z danymi")
    print(trucks["crossing"].value_counts().to_string())
    print(f"Dispatching {month}: {n_rows} wierszy, {len(names)} nazw odbiorców, "
          f"zmapowano {n_map} ({n_map / n_rows:.1%})")
    print("Udziały hubów:")
    print(shares.round(3).to_string())
    unmapped = names[names["hub"].isna()]
    if len(unmapped):
        print(f"Niezmapowane nazwy ({len(unmapped)}), zajrzyj do {f_map.name}:")
        print(unmapped.head(10).to_string(index=False))
    return trucks, shares


def load_prepared(month=None):
    month = month or config.MONTH
    trucks = pd.read_csv(config.DATA_PROC / f"trucks_{month}.csv", parse_dates=["date"])
    shares = pd.read_csv(config.DATA_PROC / f"hub_shares_{month}.csv", index_col=0)["share"]
    return trucks, shares
