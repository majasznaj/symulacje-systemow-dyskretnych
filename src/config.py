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
    "Kissufim": (31.3738, 34.3733),         # [W] OSM node 13141629229 "Kissufim crossing" (poprzednio 31.3736, 34.3758, ok. 250 m obok)
    "Gate 96": (31.4527, 34.4529),          # [?] wschodni koniec korytarza Netzarim (OSM, droga 749), ok. 70 m od płotu. Dokładnej
                                            # lokalizacji brak w OSM i w prasie ("dziura w płocie" przy korytarzu Netzarim).
                                            # W V 2024 nieużywany (Gisha). Poprzednio 31.4395, 34.4125, ok. 1,9 km w głębi Strefy.
    "JLOTS": (31.4969, 34.4090),            # [?] brzegowy koniec mola z OSM (way 1262899251). To molo WCK z III 2024; pływające molo
                                            # JLOTS (17.05-VII 2024) stało w pobliżu, tuż na północ od korytarza Netzarim. Ciężarówki
                                            # zjeżdżały z mola na plażę. Poprzednio 31.4820, 34.4030, ok. 1 km w głębi lądu.
    "Erez": (31.5582, 34.5447),             # [W] Wikipedia: 31°33′29.52″N 34°32′41″E (poprzednio 31.5414, 34.4908, ok. 5 km obok)
    "Western Erez": (31.5931, 34.4950),     # [W] OSM node 12403280153 "Erez West Crossing" (Zikim). Poprzednio 31.5640, 34.4710,
                                            # czyli w Beit Lahia, ok. 3,9 km od granicy.
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
                        r"|k[ah]*n\s*y[ou]+n[ie]?s|kh\.?\s*/?\s*y[ou]+nis|european (gaza )?hospital|خان يونس|خانيونس"),
    ("Hub_Deir_al_Balah", r"deir|dair|middle|nuseirat|bureij|maghazi|zawaida"
                          r"|\bdi?e?r\s*al|d[./\\]?\s*balah|dar\s*al|abalah|dier|nus[ae]?i?rat|nsyrat|nsirat|nusairat|buraj|bureij|burij|دير البلح|النصيرات|البريج|المغازي"),
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
DAMAGE_CELL_M = 100        # bok oczka siatki zliczającej zniszczenia (krawędź bierze maksimum z oczek, przez które przechodzi)
# Waga punktu zależy od klasy uszkodzenia z UNOSAT: 1 zniszczony, 2 poważnie, 3 średnio, 4 możliwe uszkodzenie, 11 możliwe
# uszkodzenie od sąsiedniego uderzenia. ZAŁOŻENIE: gruz robią głównie budynki zniszczone i poważnie uszkodzone, ale słabsze uszkodzenia też utrudniają przejazd (połowa wagi).
DAMAGE_CLASS_WEIGHT = {1: 1.0, 2: 1.0, 3: 0.75, 4: 0.5, 11: 0.5}
DAMAGE_DEFAULT_WEIGHT = 0.5
# Odgruzowanie: punkt schodzi z dróg po losowym czasie od zdjęcia, U(min, max) dni. None = zniszczenia zostają.
# ZAŁOŻENIE bez danych (w UNOSAT nie ma dat usunięcia gruzu). Głównie ciągi używane do transportu i pomocy odgruzowuje się szybko,
# a mniej ważne drogi wolniej. Data zdjęcia jest tylko górnym ograniczeniem daty zniszczenia.
DEBRIS_CLEAR_DAYS = (60, 180)
DEBRIS_SEED = 7            # osobny generator, żeby czas odgruzowania nie zależał od ziarna symulacji

# --- ruch ciężarówek (ZAŁOŻENIA) ---
TRUCK_SPEED_KMH = 30.0
MIN_SPEED_KMH = 5.0
SLOWDOWN_PER_DAMAGE = 1 / 6     # prędkość = SPEED / (1 + SLOWDOWN * ważone zniszczenia w oczku), nie mniej niż MIN_SPEED.
                                # ZAŁOŻENIE (bez kalibracji na danych): przy 6 zniszczonych budynkach w oczku 100 m (1 ha) prędkość
                                # spada o połowę. To ta sama gęstość co poprzednio (150 punktów w oczku 500 m = 6 na hektar).

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
# c dobrane tak, żeby przy 45 min kolejka na Kerem Shalom w marcu-maju 2024 wychodziła rzędu godzin (średnio ok. 2-3 h, maksimum ok. 16 h),
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
# Ludność hubu pochodzi z raportów IPC (liczba ludzi w gubernatorstwie), niezależnie od tego, ile pomocy dociera do huba.
# IPC łączy gubernatorstwa w grupy analizy, a huby odpowiadają pojedynczym gubernatorstwom, więc patrz IPC_SPLIT.
# Punkty to (data, północ = North Gaza + Gaza, środek = Deir al-Balah + Khan Younis, Rafah). Między punktami jest interpolacja
# liniowa po dniach, a ludność miesiąca to średnia z jego dni (data.hub_population). Przed pierwszym i po ostatnim punkcie wartość jest stała.
IPC_POPULATION = [
    # IPC 21.12.2023, analiza 24.11-7.12.2023: północ 600 000, południe (mieszkańcy + przesiedleni) 1 626 544.
    # IPC nie rozbija południa na gubernatorstwa, więc dzielimy je jak w IPC z marca 2024 (środek 600 000 : Rafah 1 326 544).
    ("2023-12-01", 600_000, 507_000, 1_119_544),
    # IPC 21.12.2023, prognoza 8.12.2023-7.02.2024: północ 500 000, południe 1 726 544 (ten sam podział południa).
    ("2024-01-15", 500_000, 538_000, 1_188_544),
    # IPC 18.03.2024, analiza 15.02-15.03.2024: północ 300 000, środek 600 000, Rafah 1 326 544.
    ("2024-03-01", 300_000, 600_000, 1_326_544),
    # Początek ofensywy na Rafah (6.05.2024): bez zmian względem IPC z marca (jej prognoza obejmuje do 15.07.2024).
    ("2024-05-06", 300_000, 600_000, 1_326_544),
    # Rafah: ok. 200 000 mieszkańców po wysiedleniu 945 000 osób (UNRWA 29.05.2024, cytowane w raporcie FRC z czerwca 2024).
    # Północ bez zmian, środek = reszta do sumy 2 226 544.
    ("2024-05-26", 300_000, 1_726_544, 200_000),
    # Rafah: ok. 65 000 w połowie czerwca 2024 (UNRWA, cytowane przez FEWS NET). Środek = reszta do sumy.
    ("2024-06-15", 300_000, 1_861_544, 65_000),
    # IPC wrzesień 2024 (analiza 1.09-31.10.2024, prognoza do 30.04.2025 z tymi samymi liczbami): suma 2 140 618.
    ("2024-09-01", 430_715, 1_665_702, 44_201),
    ("2025-04-30", 430_715, 1_665_702, 44_201),
]
# Podział grup IPC na gubernatorstwa według tabeli IPC z kwietnia 2025 (jedyna z pięcioma osobnymi gubernatorstwami):
# North Gaza 310 000 : Gaza 740 000, Deir al-Balah 400 000 : Khan Younis 620 000. ZAŁOŻENIE: stały udział w całym okresie.
IPC_SPLIT = {
    "Hub_North_Jabalia": ("north", 310_000 / 1_050_000),
    "Hub_Gaza_City": ("north", 740_000 / 1_050_000),
    "Hub_Deir_al_Balah": ("middle", 400_000 / 1_020_000),
    "Hub_Khan_Younis": ("middle", 620_000 / 1_020_000),
    "Hub_Rafah": ("rafah", 1.0),
}

# --- dokąd jedzie ciężarówka z danego przejścia ---
# Ciężarówka z przejścia wybiera hub spośród hubów tej samej części Strefy (wg geografii). W Dispatching przejście Western Erez
# prowadzi wyłącznie do Gaza City (6,4 tys. t żywności, żadnej na południe), więc podział jest zgodny z danymi. Przejścia nieuwzględnione
# w słowniku mogą jechać do wszystkich hubów. ZAŁOŻENIE: Gate 96 i JLOTS (północ od korytarza Netzarim) obsługują północ, Kissufim środek.
# Wagi hubów w grupie to ich udział w tonażu żywności z Dispatching w miesiącu. Gdy grupa nie ma w miesiącu żadnych wydań
# (Dispatching od czerwca 2024 prawie nie ma północy), wagi wynikają z ludności hubów (IPC_SPLIT).
# Kolumna Crossing w Dispatching jest przy tym niespójna z Received dla etykiety "Rafah" (patrz README), więc przejścia z niej nie bierzemy.
NORTH_HUBS = ["Hub_North_Jabalia", "Hub_Gaza_City"]
SOUTH_HUBS = ["Hub_Deir_al_Balah", "Hub_Khan_Younis", "Hub_Rafah"]
CROSSING_HUBS = {
    "Erez": NORTH_HUBS, "Western Erez": NORTH_HUBS, "Gate 96": NORTH_HUBS, "JLOTS": NORTH_HUBS,
    "Kerem Shalom": SOUTH_HUBS, "Rafah": SOUTH_HUBS, "Kissufim": SOUTH_HUBS,
}
# Żywność dostarczona do któregokolwiek huba grupy IPC (północ / środek / Rafah) służy całej grupie. IPC podaje ludność tylko
# dla grup, a podział na huby to nasze założenie (IPC_SPLIT). Huby w grupie leżą 6-13 km od siebie. False: każdy hub osobno.
FOOD_SHARED_WITHIN_IPC_GROUP = True

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
