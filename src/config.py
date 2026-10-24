"""Wszystkie parametry w jednym miejscu. Zmieniasz tutaj, nie w kodzie.

Wartości oznaczone ZAŁOŻENIE nie pochodzą z danych (brief mówi, że czasów
na granicy nie ma w publicznych zbiorach). Trzeba je opisać w raporcie
i sprawdzić na wrażliwość w M2.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
OUTPUT = ROOT / "output"

# --- pliki wejściowe (wrzuć do data/raw/) ---
RECEIVED_XLSX = DATA_RAW / "Commodities-Received.xlsx"
DISPATCH_XLSX = DATA_RAW / "Commodities-Dispatching.xlsx"
UNOSAT_ZIP = DATA_RAW / "unosat_gaza.zip"
GRAPH_FILE = DATA_PROC / "gaza_drive.graphml"

# --- okno czasowe i losowość ---
MONTH = "2024-03"   # miesiąc z Excela, który odtwarzamy
SEED = 42

# --- przejścia graniczne i huby (współrzędne z waszego notebooka, bez źródła) ---
CROSSINGS = {
    "Kerem Shalom": (31.2215, 34.2706),
    "Rafah": (31.2484, 34.2592),
    "Kissufim": (31.3736, 34.3758),
    "Gate 96": (31.4395, 34.4125),
    "JLOTS": (31.4820, 34.4030),
    "Erez": (31.5414, 34.4908),
    "Western Erez": (31.5640, 34.4710),
}
HUBS = {
    "Hub_Rafah": (31.2870, 34.2420),
    "Hub_Khan_Younis": (31.3462, 34.3039),
    "Hub_Deir_al_Balah": (31.4183, 34.3519),
    "Hub_Gaza_City": (31.5080, 34.4510),
    "Hub_North_Jabalia": (31.5350, 34.4820),
}
# nazwa w Excelu (Received) -> nazwa w CROSSINGS
CROSSING_ALIASES = {"Rafah Crossing": "Rafah"}

# Odbiorca z Dispatching -> hub. Reguły sprawdzane po kolei, pierwsza pasująca wygrywa.
# Wynik zapisuje się do data/processed/hub_mapping_<miesiąc>.csv, przejrzyjcie go.
HUB_RULES = [
    ("Hub_Rafah", r"rafah|rafa\b|al-mashroua|mashrou|sultan|geneina|musabah|musabeh|khirbet|mall al-ar"),
    ("Hub_Khan_Younis", r"khan\s*y[ou]+n[ie]?s|kytc"),
    ("Hub_Deir_al_Balah", r"deir|dair|middle|nuseirat|bureij|maghazi|zawaida"),
    ("Hub_Gaza_City", r"gaza(?! strip)|gfo"),
    ("Hub_North_Jabalia", r"north|jabal|beit lahi|beit hanoun"),
]

# --- graf drogowy ---
GAZA_BBOX = (34.20, 31.21, 34.57, 31.60)   # (zachód, południe, wschód, północ), awaryjnie
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

# --- zniszczenia (UNOSAT) ---
USE_DAMAGE = True
DAMAGE_AS_OF = "2024-03-31"        # None = wszystkie punkty; albo np. "2024-03-31" (filtr po SensorDate)
DAMAGE_CELL_M = 500        # bok oczka siatki zliczającej zniszczenia
DAMAGE_PENALTY = 0.02      # koszt = długość * (1 + PENALTY * zniszczenia^EXPONENT)
DAMAGE_EXPONENT = 2
MAX_COST_MULTIPLIER = 50.0  # żeby żadna droga nie miała kosztu nieskończonego (ZAŁOŻENIE)

# --- ruch ciężarówek (ZAŁOŻENIA) ---
TRUCK_SPEED_KMH = 30.0
MIN_SPEED_KMH = 5.0
SLOWDOWN_PER_DAMAGE = 0.03  # prędkość = SPEED / (1 + SLOWDOWN * zniszczenia)

# --- przejścia: kolejka (ZAŁOŻENIA) ---
OPEN_HOURS = (8, 18)        # Excel ma tylko datę; godzinę wjazdu losujemy z tego okna
CLEARANCE_MIN = (15, 35)    # odprawa: rozkład jednostajny, minuty (wartości z waszego notebooka)
DEFAULT_LANES = 4           # liczba równoległych stanowisk odprawy
LANES = {"Kerem Shalom": 8, "Rafah": 6}
