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
MONTH = "2024-05"   # miesiąc z Excela, który odtwarzamy (maj 2024: cztery przejścia i cztery huby z ładunkiem)
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
GAZA_BBOX = (34.20, 31.21, 34.57, 31.60)   # (zachód, południe, wschód, północ), awaryjnie; i tak przycinane do granicy Strefy
GAZA_CLIP_BUFFER_M = 500    # graf = granica Strefy + tyle metrów (przejścia leżą na granicy; więcej wpuszcza drogi spoza Strefy)
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]

# --- zniszczenia (UNOSAT) ---
USE_DAMAGE = True
DAMAGE_CELL_M = 500        # bok oczka siatki zliczającej zniszczenia
# None = zniszczenia zostają do końca symulacji (UNOSAT nie ma dat naprawy).
# Liczba = po tylu dniach od zdjęcia punkty schodzą z dróg (ZAŁOŻENIE).
DAMAGE_LIFETIME_DAYS = None

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
# Obie wartości średniej są takie same (45 min), więc zmiana rozkładu nie zmienia średniego obciążenia stanowisk.
# Czas odprawy: Gisha, "Kerem Shalom Crossing" (2020): przekazanie towaru z ciężarówki izraelskiej na palestyńską trwa ok. 45 min
# (rozładunek, przeniesienie przez "sterylne" ciężarówki, załadunek). Dla Rafah przyjmujemy to samo (przeładunek z ciężarówek
# egipskich na palestyńskie, MSF 2024), więc to założenie. Uwaga: to czas fizyczny, a w praktyce o czekaniu decyduje też zgoda COGAT.
# Liczba stanowisk NIE jest znana (Gisha: 11 komórek po 17-25 ciężarówek, ale to miejsce na postój, nie liczba równoległych odpraw).
# c dobrane tak, żeby przy 45 min kolejka na Kerem Shalom w marcu-maju 2024 wychodziła rzędu godzin (średnio ok. 2-3 h, p95 ok. 10 h),
# bo kierowcy opisywali ok. 11 h oczekiwania, a czasem do trzech dni (The World, VII 2024; Oxfam III 2024: do 20 dni w kolejkach,
# głównie na trasie z Egiptu, czyli przed dniem z Excela). To jedyna kalibracja, wyłącznie rzędu wielkości, bez danych o czasach.
SERVICE_DIST = "erlang"
CLEARANCE_MIN = (30, 60)    # dla "uniform" (średnia 45 min)
SERVICE_MEAN_MIN = 45.0     # dla "erlang"
ERLANG_K = 3                # kształt: im większe, tym bardziej równy czas odprawy (k=1 to rozkład wykładniczy)
DEFAULT_LANES = 4           # liczba równoległych stanowisk odprawy (przejścia z małym ruchem: Erez, Gate 96, JLOTS, Western Erez)
LANES = {"Kerem Shalom": 8, "Rafah": 6}

# --- pojemność K (M/G/c/K) ---
# K to największa liczba ciężarówek w systemie przejścia naraz: w odprawie plus w kolejce. Gdy jest pełno, ciężarówka jest
# zawracana (stan "zawrócona"), wraca po REJECT_RETRY_H godzinach i próbuje ponownie, a po MAX_ATTEMPTS odmowach jest odrzucona
# na stałe (stan "odrzucona", nie dowiozła). Odpowiada to re-manifestowaniu i odrzucaniu ciężarówek opisanemu przez Logistics Cluster.
# Wartości K szacujemy z długości kolejek: Reuters (25.03.2024) opisuje kolejkę ciężarówek długości 3 km przy Kerem Shalom i
# 1,5 km przy Rafah, miejscami po dwie-trzy w poprzek. Przy ok. 15 m na ciężarówkę to ok. 200 (Kerem Shalom) i ok. 250 (Rafah).
# Podobnie Gisha: 11 komórek po 17-25 ciężarówek, czyli 187-275 miejsc po stronie izraelskiej. 15 m, REJECT_RETRY_H i MAX_ATTEMPTS to
# założenia. CAPACITY_K = None wyłącza K (zwykłe M/G/c, jak w M1).
CAPACITY_K = {"Kerem Shalom": 200, "Rafah": 250}
DEFAULT_CAPACITY_K = 100    # przejścia z małym ruchem (ZAŁOŻENIE)
REJECT_RETRY_H = 24         # po tylu godzinach zawrócona ciężarówka próbuje ponownie (ZAŁOŻENIE)
MAX_ATTEMPTS = 3            # po tylu odmowach ciężarówka jest odrzucona na stałe (ZAŁOŻENIE)

# --- dynamika (ZAŁOŻENIA) ---
STUCK_GIVE_UP_H = 72         # ciężarówka bez drogi do hubu czeka tyle godzin, potem rezygnuje (delivered=False)
STUCK_WAIT_MIN = 15         # ciężarówka bez drogi do hubu sprawdza ponownie co tyle minut
BLOCK_HOURS = 12            # domyślny czas trwania blokady z --block-main
MIN_CROSSING_SAMPLES = 30 # poniżej tego progu dla przejścia używamy globalnego rozkładu

# =============================================================================
# WARSTWY DODATKOWE: rozładunek w hubach, popyt na żywność, zdarzenia losowe
# Wszystko poniżej jest WYŁĄCZONE domyślnie i włączane flagami run.py (--unloading, --demand, --stochastic, --m2).
# Wartości oznaczone ZAŁOŻENIE nie pochodzą z danych i trzeba je opisać w raporcie.
# =============================================================================

# --- ładunek: przeliczenie jednostek z Commodities-Received na tony ---
# Mediana ciężarówki rozliczanej w tonach (MT) to 14 t, a w paletach 22 palety, stąd ok. 0,64 t na paletę (ZAŁOŻENIE:
# obie grupy wożą podobny ładunek). Jednostka "Truck" ma ilość 1, a jednostki typu sztuki czy namioty nie mają wagi.
TONNES_PER_PALLET = 0.64
TRUCK_PAYLOAD_MT = 14.0     # ładunek, gdy nie da się go policzyć z jednostki (ZAŁOŻENIE: mediana ciężarówek w MT)
MAX_TRUCK_MT = 40.0         # górna granica na ciężarówkę (w danych są skrajne ilości, np. 5120 palet w jednym wierszu)

# --- popyt (demand.py) ---
# Ludność hubu = GAZA_POPULATION x udział hubu w wydaniach z Dispatching w danym miesiącu (data.hub_population).
# Excel nie ma ludności, więc przyjmujemy, że pomoc jedzie tam, gdzie są ludzie, a rozkład ludności zmienia się z miesiąca na miesiąc
# razem z rozkładem wydań (np. po maju 2024 Rafah znika z danych). To założenie, nie pomiar: dzięki niemu pokrycie na hub jest
# porównywalne między hubami, a główną miarą jest pokrycie łączne. Hub bez wydań w tym miesiącu nie ma ludności i nie jest liczony.
GAZA_POPULATION = 2_200_000   # ZAŁOŻENIE: jedyna liczba spoza Excela (ok. 2,2 mln wg ONZ), do podmiany na dane IPC/WorldPop

# --- rozkład hubów ---
# False: P(hub) z wszystkich wydań miesiąca. Kolumna Crossing w Dispatching nie zgadza się z Received (np. 2024-03: wszystkie
# wydania "Rafah", a 76% wjazdów to Kerem Shalom), więc nie warunkujemy huba przejściem. True: P(hub | crossing) jak w M1.
HUB_SHARE_BY_CROSSING = False

# --- rozładunek w hubie (--unloading) ---
# Liczba równoległych stanowisk rozładunku (ZAŁOŻENIE: brak danych) i czas rozładunku, Erlang(k) o tej średniej.
HUB_UNLOAD_DOCKS = {
    "Hub_Rafah": 4,
    "Hub_Khan_Younis": 3,
    "Hub_Deir_al_Balah": 3,
    "Hub_Gaza_City": 2,
    "Hub_North_Jabalia": 2,
}
DEFAULT_HUB_DOCKS = 2
UNLOAD_MEAN_MIN = 30.0      # ZAŁOŻENIE
UNLOAD_ERLANG_K = 3

# --- zdarzenia losowe (--stochastic, stochastic.py) ---
# Incydent drogowy: krawędź zamknięta na kilka godzin (ZAŁOŻENIE). Uczęszczane drogi mają INCIDENT_BUSY_FACTOR razy większe ryzyko.
INCIDENT_RATE_PER_EDGE_PER_DAY = 0.002
INCIDENT_BUSY_FACTOR = 3.0
INCIDENT_BUSY_TOP_K = 200
INCIDENT_DURATION_HOURS_MEAN = 3.0
INCIDENT_DURATION_HOURS_STD = 1.5

# Zamknięcie przejścia: prawdopodobieństwo na dobę (ZAŁOŻENIE, bez kalibracji; ACLED nie jest jeszcze użyte)
CROSSING_CLOSURE_RATE_PER_DAY = {
    "Kerem Shalom": 0.15,
    "Rafah": 0.20,
}
CROSSING_CLOSURE_HOURS_MEAN = 6.0
CROSSING_CLOSURE_HOURS_STD = 2.0

# Awaria pojazdu: prawdopodobieństwo na 100 km i czas naprawy [min], rozkład log-normalny (ZAŁOŻENIE)
BREAKDOWN_PROB_PER_100KM = 0.03
BREAKDOWN_REPAIR_MIN_MEAN = 90.0
BREAKDOWN_REPAIR_MIN_STD = 60.0
