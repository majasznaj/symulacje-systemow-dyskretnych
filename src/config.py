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

# --- przejścia graniczne i huby (WGS84) ---
# Stan weryfikacji: [W] współrzędne sprawdzone na stronie źródła, [P] pochodzi z PDF Logistics Cluster, [?] bez źródła.
CROSSINGS = {
    "Kerem Shalom": (31.2208, 34.2706),     # [W] Wikipedia: 31°13′15″N 34°16′14″E
    "Rafah": (31.2486, 34.2592),            # [W] Wikipedia: 31°14′55″N 34°15′33″E
    "Kissufim": (31.3736, 34.3758),         # [?] z notebooka, bez źródła
    "Gate 96": (31.4395, 34.4125),          # [?] z notebooka, bez źródła
    "JLOTS": (31.4820, 34.4030),            # [?] z notebooka, bez źródła (tymczasowe molo)
    "Erez": (31.5582, 34.5447),             # [W] Wikipedia: 31°33′29.52″N 34°32′41″E (poprzednio 31.5414, 34.4908, ok. 5 km obok)
    "Western Erez": (31.5640, 34.4710),     # [?] z notebooka, bez źródła
}
# Huby to punkty orientacyjne (magazyn albo obóz UNRWA jako przybliżenie okolicy dystrybucji), nie dokładne adresy.
HUBS = {
    "Hub_Rafah": (31.2979, 34.2723),        # [P] Logistics Cluster, Rafah Transit hub I (dokument z 2009; zamiennik: hub II 31.3007, 34.2752)
    "Hub_Khan_Younis": (31.3508, 34.2883),  # [?] obóz Khan Yunis wg Gemini (31°21′03″N 34°17′18″E), strona Wikipedii nie podaje współrzędnych
    "Hub_Deir_al_Balah": (31.4258, 34.3406),  # [W] Wikipedia, obóz Deir al-Balah: 31°25′33″N 34°20′26″E
    "Hub_Gaza_City": (31.5080, 34.4510),    # [?] z notebooka (zamiennik: Logistics Cluster Gaza City 31.5033, 34.4751)
    "Hub_North_Jabalia": (31.5372, 34.4964),  # [W] Wikipedia, obóz Jabalia: 31°32′14″N 34°29′47″E
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
# Typy dróg: filtr osmnx "drive" odrzuca m.in. service (podjazdy, boczne uliczki) i track (drogi polne). W Strefie wiele
# realnych dróg ma właśnie te tagi, więc wpuszczamy je (ROAD_EXCLUDED to lista z "drive" bez service i track).
USE_EXTRA_ROAD_TYPES = True   # False = zwykłe "drive" jak dotąd
ROAD_EXCLUDED = ("abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|escalator|footway|no|path|"
                 "pedestrian|planned|platform|proposed|raceway|razed|rest_area|services|steps")
# Wolniejsze typy dróg: prędkość swobodna = TRUCK_SPEED_KMH * współczynnik (ZAŁOŻENIA, brak danych)
ROAD_SPEED_FACTOR = {"service": 0.6, "living_street": 0.6, "track": 0.4}
GRAPH_STRONGLY_CONNECTED = True   # False = zostaw największą słabo spójną składową (nie gubi miast za jednokierunkową luką)
GAZA_BBOX = (34.20, 31.21, 34.57, 31.60)   # (zachód, południe, wschód, północ), awaryjnie
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

# --- zniszczenia (UNOSAT) ---
USE_DAMAGE = True
DAMAGE_CELL_M = 500        # bok oczka siatki zliczającej zniszczenia

# --- ruch ciężarówek (ZAŁOŻENIA) ---
TRUCK_SPEED_KMH = 30.0
MIN_SPEED_KMH = 5.0
SLOWDOWN_PER_DAMAGE = 1 / 150   # prędkość = SPEED / (1 + SLOWDOWN * zniszczenia), nie mniej niż MIN_SPEED.
                                # ZAŁOŻENIE (bez kalibracji na danych): przy 150 punktach w oczku prędkość spada o połowę.
                                # Dla porównania w marcu 2024 mediana krawędzi ma ok. 190 punktów w oczku (czas x2,3), p99 ok. 750.

# --- przejścia: kolejka (ZAŁOŻENIA) ---
OPEN_HOURS = (8, 18)        # Excel ma tylko datę; godzinę wjazdu losujemy z tego okna
# Kolejka na przejściu to M/G/c (K na razie nie ma, bo nikt nie jest odrzucany): wjazdy z Excela (dzień z danych, godzina
# losowana równomiernie w OPEN_HOURS, czyli proces Poissona o intensywności z danych), c = LANES, czas obsługi G jak niżej.
# Odprawa (G w notacji Kendalla). "uniform": rozkład jednostajny CLEARANCE_MIN; "erlang": Erlang(k) o średniej SERVICE_MEAN_MIN.
# Obie wartości średniej są takie same (25 min), więc zmiana rozkładu nie zmienia średniego obciążenia stanowisk.
SERVICE_DIST = "erlang"
CLEARANCE_MIN = (15, 35)    # dla "uniform" (wartości z waszego notebooka)
SERVICE_MEAN_MIN = 25.0     # dla "erlang" (ZAŁOŻENIE)
ERLANG_K = 3                # kształt: im większe, tym bardziej równy czas odprawy (k=1 to rozkład wykładniczy)
DEFAULT_LANES = 4           # liczba równoległych stanowisk odprawy
LANES = {"Kerem Shalom": 8, "Rafah": 6}

# --- dynamika (ZAŁOŻENIA) ---
STUCK_GIVE_UP_H = 72         # ciężarówka bez drogi do hubu czeka tyle godzin, potem rezygnuje (delivered=False)
STUCK_WAIT_MIN = 15         # ciężarówka bez drogi do hubu sprawdza ponownie co tyle minut
BLOCK_HOURS = 12            # domyślny czas trwania blokady z --block-main
