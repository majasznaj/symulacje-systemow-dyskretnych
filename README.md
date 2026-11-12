# Symulacje systemów dyskretnych: logistyka pomocy humanitarnej w Strefie Gazy

Model symulacji logistyki pomocy humanitarnej i dynamiki przetrwania ludności na przykładzie Strefy Gazy.
Stan: baza z milestone'a 1 plus opcjonalne warstwy milestone'a 2 (rozładunek w hubach, popyt na żywność, zdarzenia losowe, analityka KPI, scenariusze, wiele seedów). Bez flag M2 symulacja działa tak jak w M1 (wynik jest identyczny, sprawdzone na 2023-11 i 2024-03 przy seedzie 42).

## Co ta baza robi

Odtwarza jeden miesiąc z danych ONZ. Domyślnie marzec 2024 (`config.MONTH`), każdy inny wybierasz przez `--month`, np. `python src/run.py --month 2023-11`. Dane Excela obejmują październik 2023 – styczeń 2025.

1. Każdy wiersz z `Commodities-Received.xlsx` to jedna ciężarówka wjeżdżająca przez przejście graniczne.
2. Na przejściu ciężarówka czeka w kolejce i jest odprawiana (SimPy).
3. Potem jedzie po grafie dróg z OpenStreetMap do jednego z hubów. Trasę wyznacza D* Lite. Hub jest losowany z rozkładu warunkowego `P(hub | crossing)` z `Commodities-Dispatching`: ciężarówki z Rafah mają inny rozkład destinations niż ciężarówki z Kerem Shalom.
4. Zniszczenia z UNOSAT spowalniają drogi. Stan na 1. dzień miesiąca jest punktem startu, a nowe fale zniszczeń wchodzą w dniach zdjęć. `--damage-lifetime N` zdejmuje falę po N dniach od zdjęcia (założenie: w UNOSAT nie ma dat naprawy). Zmiana trasy zapisuje się w `replan_causes` i w logu tekstowym jako `powód:`.
5. Opcjonalnie można zamknąć najruchliwszą drogę. Ciężarówki bez trasy czekają i po 72 h rezygnują.

Warstwy M2 (wszystkie wyłączone domyślnie, włączane flagami, patrz „Szybki start"):

6. **Rozładunek (`--unloading`).** W hubie ciężarówka czeka na wolny dok (zasób SimPy) i jest rozładowywana w czasie Erlang-3 o średniej 30 min. Nowy stan FSM `rozładunek`.
7. **Popyt na żywność (`--demand`).** Ładunek z Excela (kategoria, ilość, jednostka) jest przeliczany na tony, a żywność trafia do zapasu hubu. Co dobę ludność hubu zjada tyle, ile jest w zapasie (do swojej potrzeby 2100 kcal na osobę), a z kalorii na osobę wynika uproszczona faza bezpieczeństwa żywnościowego 1–5.
8. **Zdarzenia losowe (`--stochastic`).** Incydenty drogowe (zamknięcie krawędzi na kilka godzin, częstsze na najruchliwszych drogach), zamknięcia przejść granicznych i awarie ciężarówek. Mają własny strumień losowy, więc nie zmieniają losowań z M1.
9. **Analityka (`--analytics`)** i **scenariusze A–E**, **wiele seedów (`--multi-seed N`)**: tabele i wykresy KPI, porównania z briefu.

Na wyjściu jest log każdej ciężarówki i dwie tabele podsumowań (z warstwami M2 dochodzą kolumny i tabele popytu).

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
| `--damage-lifetime 14` | fala UNOSAT schodzi z dróg 14 dni po zdjęciu |
| `--block-main "5 08:00" --block-hours 12 --block-k 1` | zamyka k najruchliwszych dróg 5. dnia o 8:00 na 12 h |
| `--build-graph` | ponowne pobranie grafu z Overpass (graf jest już w repo) |
| `--diagnose` | tylko diagnostyka grafu, tras i zniszczeń (bez symulacji), mapy `diagnoza.png` i `mapa_zniszczen.png` |
| `--unloading` | M2: rozładunek w hubach (doki, `HUB_UNLOAD_DOCKS`) |
| `--demand` | M2: popyt na żywność, zapas w hubach, kalorie na osobę, faza 1–5 |
| `--stochastic` | M2: incydenty drogowe, zamknięcia przejść, awarie ciężarówek |
| `--analytics` | M2: tabele KPI i wykresy `kpi_*.png` |
| `--m2` | skrót na `--unloading --demand --stochastic --analytics` |
| `--scenario B` | M2: scenariusze z briefu: A bazowy, B odprawa 2x szybsza, C blokada najruchliwszej drogi, D 2x więcej doków w hubach, E 2x więcej ciężarówek. Wyniki w `output/<miesiąc>/scenario_<litera>/` |
| `--multi-seed 5` | M2: pięć przebiegów (seed, seed+1, ...) i tabela ze średnią i odchyleniem standardowym |

Przykład pełnego przebiegu M2: `python src/run.py --month 2024-03 --m2`. Plik *colab_run_m2.ipynb* ma gotowe komórki dla M2.

Wyniki trafiają do `output/<miesiąc>/`:

| Plik | Zawartość |
|---|---|
| `truck_log.csv` | jedna linia na ciężarówkę: przejście, hub, czas w kolejce, odprawa, czas i długość dojazdu, zmiany trasy (`replans`), powód zmiany (`replan_causes`), czas bez drogi, czy dowiozła |
| `summary_crossings.csv` | kolejki na przejściach (średnia, p95, maksimum) |
| `summary_hubs.csv` | czasy i długości dojazdu do hubów |
| `sim_log.txt` | log tekstowy (tylko z `--log-days` / `--log-every`) |
| `diagnoza.png`, `mapa_zniszczen.png`, `diagnoza_*.csv` | z `--diagnose`: graf z trasami oraz drogi pomalowane zniszczeniami |
| `demand_summary.csv`, `demand_history.csv` | z `--demand`: pokrycie zapotrzebowania na żywność na hub, historia dobowa (zapas, kalorie na osobę, faza) |
| `kpi_summary.csv`, `bottleneck_*.csv`, `kpi_*.png` | z `--analytics`: KPI ogólne, wąskie gardła (przejścia i krawędzie), rozkłady kolejek i dojazdów, zapas i kalorie, oś czasu faz, mapa zatorów |
| `multiseed_kpi.csv`, `multiseed_summary.csv` | z `--multi-seed`: KPI każdego przebiegu oraz średnia i odchylenie |
| `scenario_<A-E>/` | z `--scenario`: te same pliki co wyżej dla danego scenariusza |
Kolumny M2 w `truck_log.csv`: `category`, `cargo_mt`, `unload_wait_min`, `unload_min`, `breakdown_delay_min`.

## Gdzie co jest

| Ścieżka | Do czego |
|---|---|
| `src/config.py` | wszystkie parametry i założenia w jednym miejscu (przejścia, huby, liczba stanowisk, czas odprawy, prędkości) |
| `src/data.py` | Excel → ciężarówki i macierz udziałów hubów `P(hub \| crossing)` (`data/processed/`) |
| `src/network.py` | graf dróg (pobranie, wczytanie), przypinanie punktów do węzłów, trasy bazowe |
| `src/damage.py` | UNOSAT → liczba punktów w oczku 500 m → czas przejazdu krawędzi |
| `src/dstar_lite.py` | algorytm D* Lite (a raczej przybliżenie, bo to ciężkie w implementacji) |
| `src/router.py` | po jednym polu kosztu D* Lite na hub, ciężarówka czyta z niego następny krok |
| `src/fsm.py` | maszyna stanów ciężarówki (z rozładunkiem) |
| `src/events.py` | zdarzenia zmieniające drogi w czasie: fale UNOSAT i blokady |
| `src/sim.py` | pętla SimPy: wjazd, kolejka, odprawa, jazda, rozładunek, dojazd, doby popytu |
| `src/demand.py` | M2: ładunek → tony, zapas żywności w hubach, kalorie na osobę, faza 1–5 (autorka: Martyna, przepisane do wspólnego kodu) |
| `src/stochastic.py` | M2: incydenty drogowe, zamknięcia przejść, awarie (Martyna) |
| `src/analytics.py` | M2: KPI, wąskie gardła i wykresy (Martyna) |
| `src/run.py` | uruchamianie, scenariusze A–E, wiele seedów i tabele podsumowań |
| `src/diagnose.py` | diagnostyka grafu, tras i zniszczeń, mapy |
| `data/raw/` | Excele ONZ (Received, Dispatching) i archiwum UNOSAT |
| `data/processed/` | gotowy graf `gaza_drive.graphml`, ciężarówki (`trucks_<miesiąc>.csv`), macierz udziałów hubów (`hub_shares_<miesiąc>.csv`, wiersze = crossingi, kolumny = huby), mapowanie odbiorców na huby (`hub_mapping_<miesiąc>.csv`, do przejrzenia) |

## Modele: co jest, czego jeszcze nie ma

| Model z notatek zespołu | Stan | Uwagi |
|---|---|---|
| Kolejka Kendalla | jest jako M/G/c | wjazdy z danych (dzień z Excela, godzina losowana równomiernie w 8–18, co przy znanej liczbie wjazdów jest równoważne procesowi Poissona), c stanowisk (Kerem Shalom 8, Rafah 6), czas odprawy Erlang-3 o średniej 25 min. **K (pojemności) nie ma.** Dopóki nikt nie jest odrzucany ani przekierowywany, K nie zmienia żadnego czasu, więc wróci razem z odrzucaniem ciężarówek |
| FSM | jest | wjazd → kolejka → odprawa → jazda ↔ bez drogi → rozładunek → dowiozła / zrezygnowała. Niedozwolone przejście zgłasza błąd. Stanu kryzysu jeszcze nie ma |
| Rozładunek w hubie | jest (opcja `--unloading`) | doki jako zasób SimPy (`HUB_UNLOAD_DOCKS`), czas Erlang-3 o średniej 30 min. Liczba doków i czas są założeniem, patrz niżej |
| Popyt i bezpieczeństwo żywnościowe | jest w wersji uproszczonej (`--demand`) | zapas żywności w hubie, kalorie na osobę na dobę, faza 1–5 z progów 2100/1900/1700/1500 kcal. To **nie jest** oficjalny IPC (IPC liczy też wodę, zdrowie i śmiertelność), tylko uproszczony wskaźnik z samych kalorii |
| Zdarzenia losowe | są własne (`--stochastic`) | incydenty drogowe, zamknięcia przejść, awarie. Dane ACLED nie są użyte, więc częstości nie są skalibrowane |
| D* Lite | jest | pole kosztu do każdego hubu naprawiane przyrostowo po zmianie dróg (zniszczenia, blokady). Heurystyka jest wyłączona, bo liczymy pole dla całej floty, więc w praktyce to przyrostowy Dijkstra liczony od hubu wstecz. Przyrostowa naprawa to właśnie część, która tu pracuje. |
| Nagel-Schreckenberg (ruch, zatory przed bramką) | nie ma | |
| Helbing (tłum w punktach dystrybucji) | nie ma | |
| Utility AI (decyzje kierowców) | nie ma | wymaga stanu kryzysu w FSM. Kategoria ładunku trafia już do logu (`category`) |
| KPI, scenariusze, wiele seedów, wykresy | jest (`--analytics`, `--scenario`, `--multi-seed`) | |
| Zdarzenia z ACLED, walidacja na danych historycznych | nie ma | etap 4 briefu |

## Założenia, które nie pochodzą z danych

Wszystkie są w `src/config.py`, oznaczone słowem ZAŁOŻENIE. Najważniejsze:

- liczba stanowisk odprawy i czas odprawy (brief mówi, że czasów na granicy nie ma w publicznych danych),
- godzina wjazdu (Excel ma tylko datę) i godziny otwarcia 8–18, przy czym odprawa trwa także po 18:00,
- prędkość ciężarówki 30 km/h, a na drogach `service`, `living_street` i `track` odpowiednio mniej,
- spowolnienie od zniszczeń: połowa prędkości przy 150 punktach UNOSAT w oczku 500 m, wszystkie klasy zniszczeń liczone tak samo,
- współrzędne przejść i hubów. Przy każdej jest oznaczone, czy zostały sprawdzone na stronie źródła ([W]), pochodzą z dokumentu Logistics Cluster ([P]) czy nie mają źródła ([?]),
- M2: przelicznik palety na tony 0,64 t (z median: 14 t ładunku na ciężarówkę przy 22 paletach), ciężarówka bez znanej ilości dostaje 14 t, ograniczenie do 0,1–40 t,
- M2: liczba ludności przy hubach (600 / 400 / 350 / 200 / 150 tys.) jest jednym stałym założeniem na cały okres, a nie danymi IPC z danego miesiąca,
- M2: liczba doków rozładunkowych (4/3/3/2/2) i czas rozładunku 30 min. Nie ma danych o magazynach, a wynik mocno od nich zależy,
- M2: częstości incydentów drogowych (0,002 na krawędź na dobę), zamknięć przejść (Kerem Shalom 0,15, Rafah 0,20 na dobę, 6 ± 2 h) i awarii (3% na 100 km) to wartości do kalibracji,
- próg `MIN_CROSSING_SAMPLES = 30` — jeśli w `Commodities-Dispatching` dla danego crossingu jest mniej niż 30 wierszy, używamy globalnego rozkładu hubów zamiast lokalnego (żeby nie ufać szumowi z kilku wierszy).

## Znane ograniczenia

1. **Graf w Rafah (naprawiony 12.11.2026).** Poprzedni graf miał w Rafah tylko 460 krawędzi (pas 31,25–31,30°N), a trasy do Hub_Rafah były 2,5–2,9 razy dłuższe niż linia prosta. OSM jest dziś pełniejszy: po ponownym pobraniu pas ma 3009 krawędzi, a cały graf 25 634 węzłów zamiast 14 002. Graf jest przycięty do granicy Strefy + 500 m (`config.GAZA_CLIP_BUFFER_M`), bo sam prostokąt `GAZA_BBOX` obejmuje też Izrael i trasy mogłyby iść jego drogami. Współczynnik trasa / linia prosta jest teraz 1,1–1,3 dla wszystkich par przejście-hub (Rafah → Hub_Rafah 6,8 km zamiast 15,4 km, Kerem Shalom → Hub_Rafah 10,3 km zamiast 17,8 km), a Kerem Shalom przypina się do węzła 16 m od punktu zamiast 1,2 km. Pozostaje jedno: Hub_Rafah (współrzędne z dokumentu z 2009, oznaczone [P]) przypina się do węzła 783 m od punktu. Zamknięcie jednej, najruchliwszej krawędzi (`--block-main`) daje teraz objazd o około 0,5 km i nikt nie zostaje bez drogi, więc scenariusz „zamknięcie głównej drogi północ-południe" wymaga zamknięcia całego przekroju korytarza, a nie jednej krawędzi.
2. **Destinations dla Kerem Shalom w marcu 2024 są nieznane.** W `Commodities-Dispatching` dla 2024-03 wszystkie 5131 wierszy ma `Crossing = Rafah`, mimo że w `Commodities-Received` 76,5% wjazdów (3818/4993) jest przez Kerem Shalom. Dla Kerem Shalom używamy fallbacku do globalnego rozkładu hubów (który = rozkład Rafah, bo wszystkie destinations to Rafah). Weryfikacja `P(hub | crossing)` możliwa tylko dla Rafah — i tam zgadza się z danymi do ~1 pp (szum próbkowania 2545–5131 losowań).
3. **Zniszczenia działają prawie jak równomierne spowolnienie.** 97% krawędzi ma jakieś zniszczenia, a mediana to ok. 190 punktów w oczku (czas ×2,3). Datą zniszczenia jest data zdjęcia satelity, nie ataku. W pliku UNOSAT prawie nie ma późniejszego zejścia do klasy „brak uszkodzeń”, więc domyślnie fale zostają. `--damage-lifetime` jest jawnym założeniem, że po N dniach droga wraca do poprzedniej prędkości.
4. **Wyniki M2 zależą od założeń, które nie mają danych.** Przy `--m2` w marcu 2024 średnie oczekiwanie na dok w Hub_Rafah to ok. 250–290 min i to ono dominuje czas dostawy. Powód: do Hub_Rafah jedzie 4375 z 4993 ciężarówek (rozkład `P(hub | crossing)` z danych, a dla Kerem Shalom brak destinations, patrz punkt 2), a zakładamy tylko 4 doki. Średnia kolejka na przejściach rośnie z 6 do ok. 40–70 min po dodaniu zamknięć przejść, a między seedami waha się mocno (odchylenie ok. 19 min przy 3 seedach), więc należy raportować średnią z wielu seedów. Pokrycie zapotrzebowania na żywność (ok. 53%) jest wypadkową tych założeń i nie należy go traktować jako oszacowania rzeczywistego niedoboru. Hub_Rafah dostaje kilka razy więcej żywności niż potrzebuje, a pozostałe huby 10–33%, bo nie ma przesyłania zapasów między hubami.
5. **Kolejka przejść jest nieskalibrowana.** Liczba stanowisk (Kerem Shalom 8, Rafah 6) i czas odprawy to założenia. W 2024-03 obciążenie Rafah wychodzi ok. 0,27, a w 2023-11 tylko cztery dni są przeciążone. Nie ma pojemności K ani odrzucania ciężarówek.
6. **Graf zawiera drogi serwisowe i dojazdowe oraz Korytarz Filadelfijski.** Trasy mogą przechodzić przez drogi, których ciężarówki humanitarne w praktyce nie używają. Do rozważenia ograniczenie klas dróg.
7. **Część destinations z Excela pozostaje niezmapowana do hubów** — w 2023-11 to 117 nazw (323 wiersze, 14% ruchu), głównie szpitale, magazyny logistyczne ONZ i sklepy. Do rozszerzenia `HUB_RULES` po ręcznej weryfikacji lokalizacji.

## Plan

- **Milestone 2 (zrobione):** scenariusze A–E i pętla po wielu seedach, rozładunek w hubie (stan `UNLOAD`), uproszczony popyt na żywność, zdarzenia losowe, analityka KPI, naprawa grafu w Rafah. **Zostaje do M2/M3:** K razem z odrzucaniem ciężarówek (stan `REJECTED`), kalibracja kolejki i doków, scenariusz zamknięcia całego przekroju korytarza, rozszerzenie `HUB_RULES`, ludność z IPC per okres.
- **Milestone 3:** Nagel-Schreckenberg przy bramkach, tłum w punktach dystrybucji (Helbing), stan kryzysu i Utility AI, zdarzenia z ACLED, kalibracja zdarzeń losowych.
- **Milestone 4:** wizualizacja, walidacja na danych historycznych, raport.

## Jak dodawać nowe rzeczy

- nowy parametr: `src/config.py`,
- nowy stan ciężarówki: `src/fsm.py` (stany i dozwolone przejścia), potem użyć go w `src/sim.py`,
- nowa warstwa M2: osobny strumień losowy `default_rng([seed, 11])` w `sim.py` i domyślnie wyłączona flaga w `run.py`, żeby nie zmieniać wyniku M1,
- nowe zdarzenie zmieniające drogi: `events.Event(minuta, opis, apply)`, gdzie `apply(G, damage_model)` zwraca zbiór zmienionych krawędzi `(u, v)`. Router sam naprawi trasy.

## Źródła danych

- UN OCHA / Logistics Cluster: `Commodities-Received.xlsx`, `Commodities-Dispatching.xlsx` (wjazdy i wydania pomocy),
- UNOSAT: ocena zniszczeń budynków w Strefie Gazy (`unosat_gaza.zip`, warstwa punktowa),
- OpenStreetMap przez OSMnx: sieć dróg.