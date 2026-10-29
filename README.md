# Symulacje systemów dyskretnych: logistyka pomocy humanitarnej w Strefie Gazy

Model symulacji logistyki pomocy humanitarnej i dynamiki przetrwania ludności na przykładzie Strefy Gazy.
Stan: koniec milestone'a 1, czyli mała, ale działająca baza, na której budujemy dalej.

## Co ta baza robi

Odtwarza jeden miesiąc z danych ONZ. Domyślnie marzec 2024 (`config.MONTH`), każdy inny wybierasz przez `--month`, np. `python src/run.py --month 2023-11`. Dane Excela obejmują październik 2023 – styczeń 2025.

1. Każdy wiersz z `Commodities-Received.xlsx` to jedna ciężarówka wjeżdżająca przez przejście graniczne.
2. Na przejściu ciężarówka czeka w kolejce i jest odprawiana (SimPy).
3. Potem jedzie po grafie dróg z OpenStreetMap do jednego z hubów. Trasę wyznacza D* Lite. Hub jest losowany z rozkładu warunkowego `P(hub | crossing)` z `Commodities-Dispatching`: ciężarówki z Rafah mają inny rozkład destinations niż ciężarówki z Kerem Shalom.
4. Zniszczenia z UNOSAT spowalniają drogi. Stan na 1. dzień miesiąca jest punktem startu, a nowe fale zniszczeń wchodzą w dniach zdjęć.
5. Opcjonalnie można zamknąć najruchliwszą drogę. Ciężarówki bez trasy czekają i po 72 h rezygnują.

Na wyjściu jest log każdej ciężarówki i dwie tabele podsumowań.

**Weryfikacja:** rozkład hubów w symulacji vs dane `Commodities-Dispatching`:

| Miesiąc | Crossing | Maks. różnica |
|---|---|---|
| 2023-11 | Rafah | 0,85 pp |
| 2024-03 | Rafah | 1,15 pp |

Różnice mieszczą się w szumie próbkowania (`σ ≈ 0,9 pp` przy n=2545, `σ ≈ 0,4 pp` przy n=5131). Kerem Shalom nie jest weryfikowalny w 2024-03 (brak destinations w danych — patrz „Znane ograniczenia", punkt 2).

## Szybki start

plik *colab_run.ipynb* - gotowe komórki

Warianty uruchomienia:

| Polecenie | Co robi |
|---|---|
| `--seed 7` | inny seed losowań |
| `--log-days 1,2 --log-every 50` | log tekstowy `sim_log.txt`: wszystkie ciężarówki z dni 1–2, log wyświetlany dla co 50. ciężarówki, plus wszystkie zdarzenia |
| `--month 2023-11` | inny miesiąc z Excela. Dane przygotowują się same przy pierwszym uruchomieniu, potem są w `data/processed/` |
| `--no-damage` | punkt odniesienia bez zniszczeń |
| `--block-main "5 08:00" --block-hours 12 --block-k 1` | zamyka k najruchliwszych dróg 5. dnia o 8:00 na 12 h |
| `--build-graph` | ponowne pobranie grafu z Overpass (graf jest już w repo) |

Wyniki trafiają do `output/<miesiąc>/`:

| Plik | Zawartość |
|---|---|
| `truck_log.csv` | jedna linia na ciężarówkę: przejście, hub, czas w kolejce, odprawa, czas i długość dojazdu, zmiany trasy, czas bez drogi, czy dowiozła |
| `summary_crossings.csv` | kolejki na przejściach (średnia, p95, maksimum) |
| `summary_hubs.csv` | czasy i długości dojazdu do hubów |
| `sim_log.txt` | log tekstowy (tylko z `--log-days` / `--log-every`) |
| `diagnoza.png`, `mapa_zniszczen.png`, `diagnoza_*.csv` | z `--diagnose`: graf z trasami oraz drogi pomalowane zniszczeniami |

## Gdzie co jest

| Ścieżka | Do czego |
|---|---|
| `src/config.py` | wszystkie parametry i założenia w jednym miejscu (przejścia, huby, liczba stanowisk, czas odprawy, prędkości) |
| `src/data.py` | Excel → ciężarówki i macierz udziałów hubów `P(hub \| crossing)` (`data/processed/`) |
| `src/network.py` | graf dróg (pobranie, wczytanie), przypinanie punktów do węzłów, trasy bazowe |
| `src/damage.py` | UNOSAT → liczba punktów w oczku 500 m → czas przejazdu krawędzi |
| `src/dstar_lite.py` | algorytm D* Lite (a raczej przybliżenie, bo to ciężkie w implementacji) |
| `src/router.py` | po jednym polu kosztu D* Lite na hub, ciężarówka czyta z niego następny krok |
| `src/fsm.py` | maszyna stanów ciężarówki |
| `src/events.py` | zdarzenia zmieniające drogi w czasie: fale UNOSAT i blokady |
| `src/sim.py` | pętla SimPy: wjazd, kolejka, odprawa, jazda, dojazd |
| `src/run.py` | uruchamianie i tabele podsumowań |
| `src/diagnose.py` | diagnostyka grafu, tras i zniszczeń, mapy |
| `data/raw/` | Excele ONZ (Received, Dispatching) i archiwum UNOSAT |
| `data/processed/` | gotowy graf `gaza_drive.graphml`, ciężarówki (`trucks_<miesiąc>.csv`), macierz udziałów hubów (`hub_shares_<miesiąc>.csv`, wiersze = crossingi, kolumny = huby), mapowanie odbiorców na huby (`hub_mapping_<miesiąc>.csv`, do przejrzenia) |

## Modele: co jest, czego jeszcze nie ma

| Model z notatek zespołu | Stan | Uwagi |
|---|---|---|
| Kolejka Kendalla | jest jako M/G/c | wjazdy z danych (dzień z Excela, godzina losowana równomiernie w 8–18, co przy znanej liczbie wjazdów jest równoważne procesowi Poissona), c stanowisk (Kerem Shalom 8, Rafah 6), czas odprawy Erlang-3 o średniej 25 min. **K (pojemności) nie ma.** Dopóki nikt nie jest odrzucany ani przekierowywany, K nie zmienia żadnego czasu, więc wróci razem z odrzucaniem ciężarówek |
| FSM | jest | wjazd → kolejka → odprawa → jazda ↔ bez drogi → dowiozła / zrezygnowała. Niedozwolone przejście zgłasza błąd. Stanów rozładunku i kryzysu jeszcze nie ma |
| D* Lite | jest | pole kosztu do każdego hubu naprawiane przyrostowo po zmianie dróg (zniszczenia, blokady). Heurystyka jest wyłączona, bo liczymy pole dla całej floty, więc w praktyce to przyrostowy Dijkstra liczony od hubu wstecz. Przyrostowa naprawa to właśnie część, która tu pracuje. |
| Nagel-Schreckenberg (ruch, zatory przed bramką) | nie ma | |
| Helbing (tłum w punktach dystrybucji) | nie ma | |
| Utility AI (decyzje kierowców) | nie ma | wymaga stanu kryzysu w FSM i kategorii ładunku (kolumna `category` jest w danych, ale nie trafia do logu) |
| KPI bezpieczeństwa żywnościowego, zdarzenia losowe z ACLED, wizualizacja | nie ma | etapy 3–4 briefu |

## Założenia, które nie pochodzą z danych

Wszystkie są w `src/config.py`, oznaczone słowem ZAŁOŻENIE. Najważniejsze:

- liczba stanowisk odprawy i czas odprawy (brief mówi, że czasów na granicy nie ma w publicznych danych),
- godzina wjazdu (Excel ma tylko datę) i godziny otwarcia 8–18, przy czym odprawa trwa także po 18:00,
- prędkość ciężarówki 30 km/h, a na drogach `service`, `living_street` i `track` odpowiednio mniej,
- spowolnienie od zniszczeń: połowa prędkości przy 150 punktach UNOSAT w oczku 500 m, wszystkie klasy zniszczeń liczone tak samo,
- współrzędne przejść i hubów. Przy każdej jest oznaczone, czy zostały sprawdzone na stronie źródła ([W]), pochodzą z dokumentu Logistics Cluster ([P]) czy nie mają źródła ([?]),
- próg `MIN_CROSSING_SAMPLES = 30` — jeśli w `Commodities-Dispatching` dla danego crossingu jest mniej niż 30 wierszy, używamy globalnego rozkładu hubów zamiast lokalnego (żeby nie ufać szumowi z kilku wierszy).

## Znane ograniczenia

1. **W grafie brakuje ulic w Rafah przy granicy z Egiptem.** W marcu 2024 jedzie do Hub_Rafah 88% ciężarówek. Kerem Shalom → Hub_Rafah ma 17,8 km przy 8,6 km w linii prostej, Rafah → Hub_Rafah 15,4 km przy 5,6 km, a zamknięcie najruchliwszej drogi (`--block-main`) zatrzymuje 182 ciężarówki, bo nie ma objazdu (`docs/rafah_graf.png`). Mapa Google pokazuje w punkcie 31.2826N 34.2572E gęstą siatkę ulic, a graf ma w promieniu 500 m od niego 6 krawędzi i żadnej z tych nazw. Brakuje ich w OSM - w razie potrzeby należy albo je sztucznie dorysować albo wybrać inne źródło map.
2. **Destinations dla Kerem Shalom w marcu 2024 są nieznane.** W `Commodities-Dispatching` dla 2024-03 wszystkie 5131 wierszy ma `Crossing = Rafah`, mimo że w `Commodities-Received` 76,5% wjazdów (3818/4993) jest przez Kerem Shalom. Dla Kerem Shalom używamy fallbacku do globalnego rozkładu hubów (który = rozkład Rafah, bo wszystkie destinations to Rafah). Weryfikacja `P(hub | crossing)` możliwa tylko dla Rafah — i tam zgadza się z danymi do ~1 pp (szum próbkowania 2545–5131 losowań).
3. **Zniszczenia działają prawie jak równomierne spowolnienie.** 97% krawędzi ma jakieś zniszczenia, a mediana to ok. 190 punktów w oczku (czas ×2,3). Datą zniszczenia jest data zdjęcia satelity, nie ataku. Nie ma napraw.
4. **Część destinations z Excela pozostaje niezmapowana do hubów** — w 2023-11 to 117 nazw (323 wiersze, 14% ruchu), głównie szpitale, magazyny logistyczne ONZ i sklepy. Do rozszerzenia `HUB_RULES` w M2 po ręcznej weryfikacji lokalizacji.

## Plan

- **Milestone 2:** scenariusze z briefu jako parametry (więcej ciężarówek, krótsza odprawa, więcej stanowisk, odcięcie arterii, decentralizacja magazynów) i pętla po wielu seedach z jedną tabelą wyników; rozładunek w hubie (stan `UNLOAD` w FSM); K razem z odrzucaniem ciężarówek (stan `REJECTED`); naprawa grafu w Rafah (ręczny patch albo inne źródło OSM); rozszerzenie `HUB_RULES`.
- **Milestone 3:** Nagel-Schreckenberg przy bramkach, tłum w punktach dystrybucji (Helbing), stan kryzysu i Utility AI, KPI głodu, zdarzenia losowe z ACLED.
- **Milestone 4:** wizualizacja, walidacja na danych historycznych, raport.

## Jak dodawać nowe rzeczy

- nowy parametr: `src/config.py`,
- nowy stan ciężarówki: `src/fsm.py` (stany i dozwolone przejścia), potem użyć go w `src/sim.py`,
- nowe zdarzenie zmieniające drogi: `events.Event(minuta, opis, apply)`, gdzie `apply(G, damage_model)` zwraca zbiór zmienionych krawędzi `(u, v)`. Router sam naprawi trasy.

## Źródła danych

- UN OCHA / Logistics Cluster: `Commodities-Received.xlsx`, `Commodities-Dispatching.xlsx` (wjazdy i wydania pomocy),
- UNOSAT: ocena zniszczeń budynków w Strefie Gazy (`unosat_gaza.zip`, warstwa punktowa),
- OpenStreetMap przez OSMnx: sieć dróg.