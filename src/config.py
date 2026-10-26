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
    # "North Gaza" ma trafić na północ, więc ta reguła stoi przed Gaza City; druga linia w każdej regule: warianty pisowni i nazwy arabskie (nazw bez miejscowości, np. "Miraj Stores", nie zgadujemy)
    ("Hub_Rafah", r"rafah|rafa\b|al-mashroua|mashrou|sultan|geneina|musabah|musabeh|khirbet|mall al-ar"
                  r"|\brf?ah\b|رفح|السلطان"),
    ("Hub_Khan_Younis", r"khan\s*y[ou]+n[ie]?s|kytc"
                        r"|k[ah]*n\s*y[ou]+n[ie]?s|kh\.?\s*/?\s*y[ou]+nis|خان يونس|خانيونس"),
    ("Hub_Deir_al_Balah", r"deir|dair|middle|nuseirat|bureij|maghazi|zawaida"
                          r"|\bdi?e?r\s*al|d[./\\]?\s*balah|dar\s*al|abalah|dier|nus[ae]?i?rat|nsyrat|nsirat|nusairat|buraj|bureij|دير البلح|النصيرات|البريج|المغازي"),
    ("Hub_North_Jabalia", r"north|jabal|beit lahi|beit hanoun|جباليا|بيت لاهيا|بيت حانون"),
    ("Hub_Gaza_City", r"gaza(?! strip)|gfo|(?<!دير )غزة"),
]

# --- graf drogowy ---
GRAPH_STRONGLY_CONNECTED = True   # False = zostaw największą słabo spójną składową (nie gubi miast za jednokierunkową luką)
GAZA_BBOX = (34.20, 31.21, 34.57, 31.60)   # (zachód, południe, wschód, północ), awaryjnie
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

# --- zniszczenia (UNOSAT) ---
USE_DAMAGE = True
DAMAGE_AS_OF = None        # None = tryb dynamiczny: stan na 1. dzień miesiąca + fale UNOSAT z tego miesiąca
                           # w dniach zdjęć; data np. "2024-03-31" = stały stan na ten dzień, bez fal
DAMAGE_CELL_M = 500        # bok oczka siatki zliczającej zniszczenia
RISK_WEIGHT = 0.0          # koszt trasy = czas przejazdu * (1 + RISK_WEIGHT * zniszczenia); 0 = router minimalizuje sam czas
                           # (ZAŁOŻENIE: >0 oznacza, że kierowca unika zniszczeń także kosztem dłuższej jazdy)

# --- ruch ciężarówek (ZAŁOŻENIA) ---
TRUCK_SPEED_KMH = 30.0
MIN_SPEED_KMH = 5.0
SLOWDOWN_PER_DAMAGE = 1 / 150   # prędkość = SPEED / (1 + SLOWDOWN * zniszczenia), nie mniej niż MIN_SPEED.
                                # ZAŁOŻENIE (bez kalibracji na danych): przy 150 punktach w oczku prędkość spada o połowę.
                                # Dla porównania 750 = p99 w marcu 2024 (zniszczenia prawie nie wpływały na trasy)

# --- przejścia: kolejka (ZAŁOŻENIA) ---
OPEN_HOURS = (8, 18)        # Excel ma tylko datę; godzinę wjazdu losujemy z tego okna
CLEARANCE_MIN = (15, 35)    # odprawa: rozkład jednostajny, minuty (wartości z waszego notebooka)
DEFAULT_LANES = 4           # liczba równoległych stanowisk odprawy
LANES = {"Kerem Shalom": 8, "Rafah": 6}

# --- dynamika (ZAŁOŻENIA) ---
STUCK_GIVE_UP_H = 72         # ciężarówka bez drogi do hubu czeka tyle godzin, potem rezygnuje (delivered=False)
STUCK_WAIT_MIN = 15         # ciężarówka bez drogi do hubu sprawdza ponownie co tyle minut
BLOCK_HOURS = 12            # domyślny czas trwania blokady z --block-main
