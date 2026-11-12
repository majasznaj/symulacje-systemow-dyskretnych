# Symulacje systemów dyskretnych: logistyka pomocy humanitarnej w Strefie Gazy

Symulacja dostaw pomocy humanitarnej do Strefy Gazy: kolejka na przejściach granicznych, przejazd po zniszczonych drogach do hubów, rozładunek i pokrycie zapotrzebowania na żywność.
Model odtwarza jeden miesiąc z danych ONZ. Warstwy dodatkowe (rozładunek, żywność, zdarzenia losowe, analityka) włącza się flagami. Bez flag działa sama kolejka i dojazd.

## Co ta baza robi

Domyślnie maj 2024 (`config.MONTH`). Inny miesiąc wybierasz przez `--month`, np. `python src/run.py --month 2023-11`. Dane Excela obejmują październik 2023 – styczeń 2025.

1. Każdy wiersz z `Commodities-Received.xlsx` to jedna ciężarówka wjeżdżająca przez przejście graniczne.
2. Na przejściu ciężarówka czeka w kolejce i jest odprawiana (SimPy). Przejście ma skończoną pojemność K (odprawa plus kolejka). Gdy jest pełne, ciężarówka zawraca, wraca po dobie, a po trzech odmowach jest odrzucona na stałe.
3. Potem jedzie po grafie dróg z OpenStreetMap do jednego z hubów. Trasę wyznacza D* Lite. Hub jest losowany z udziału wydań z całego miesiąca w `Commodities-Dispatching`. Przejście wjazdu pochodzi z `Received`, bo kolumna `Crossing` w `Dispatching` jest niespójna (patrz „Znane ograniczenia”, punkt 2).
4. Zniszczenia z UNOSAT spowalniają drogi. Stan na 1. dzień miesiąca jest punktem startu, a nowe fale wchodzą w dniach zdjęć. `--damage-lifetime N` zdejmuje falę po N dniach od zdjęcia. Zmiana trasy zapisuje się w `replan_causes` i w logu tekstowym.
5. Opcjonalnie można zamknąć najruchliwszą drogę. Ciężarówki bez trasy czekają i po 72 h rezygnują.

Warstwy dodatkowe (flagi w „Szybkim starcie”):

- **Rozładunek (`--unloading`).** W hubie ciężarówka czeka na wolny dok i rozładowuje się średnio 30 min.
- **Popyt na żywność (`--demand`).** Ładunek jest przeliczany na tony. Co dobę ludność hubu zjada zapas (do 2100 kcal na osobę), a z kalorii wychodzi uproszczona faza 1–5.
- **Zdarzenia losowe (`--stochastic`).** Incydenty drogowe, zamknięcia przejść i awarie ciężarówek. Mają osobny generator losowy, więc nie zmieniają pozostałych losowań.
- **Analityka (`--analytics`), scenariusze (`--scenario`), wiele seedów (`--multi-seed`).**

**Weryfikacja:** rozkład hubów w symulacji vs dane `Commodities-Dispatching`:

| Miesiąc | Ciężarówek | Maks. różnica | Szum próbkowania σ |
|---|---|---|---|
| 2023-11 | 2545 | 0,96 pp | 0,93 pp |
| 2024-03 | 4993 | 0,68 pp | 0,45 pp |
| 2024-05 | 4342 | 1,01 pp | 0,76 pp |

Różnice mieszczą się w szumie próbkowania. To sprawdza, czy losowanie hubów odtwarza dane, a nie czy dane są dobre.

## Szybki start

Pliki *demo.ipynb* (przegląd krok po kroku z wykresami) i *colab_run_m2.ipynb* (gotowe komórki do Colaba).

| Polecenie | Co robi |
|---|---|
| `python src/run.py` | symulacja dla `config.MONTH` |
| `--month 2023-11` | inny miesiąc. Dane przygotowują się same przy pierwszym uruchomieniu |
| `--seed 7` | inne ziarno losowań |
| `--log-days 1,2 --log-every 50` | log tekstowy `sim_log.txt`: wszystkie ciężarówki z dni 1–2 i co 50. ciężarówka, plus zdarzenia |
| `--no-damage` | bez zniszczeń |
| `--damage-lifetime 14` | fala UNOSAT schodzi z dróg 14 dni po zdjęciu |
| `--no-capacity` | bez pojemności K |
| `--block-main "5 08:00" --block-hours 12 --block-k 1` | zamyka k najruchliwszych dróg 5. dnia o 8:00 na 12 h |
| `--diagnose` | tylko diagnostyka grafu, tras i zniszczeń (bez symulacji) |
| `--unloading` / `--demand` / `--stochastic` / `--analytics` | pojedyncze warstwy dodatkowe |
| `--m2` | wszystkie cztery warstwy naraz |
| `--scenario B` | scenariusz: A bazowy, B odprawa 2x szybsza, C blokada najruchliwszej drogi, D 2x więcej doków, E 2x więcej ciężarówek |
| `--multi-seed 5` | pięć przebiegów (seed, seed+1, ...) i tabela ze średnią i odchyleniem |
| `--build-graph` | ponowne pobranie grafu z Overpass (graf jest w repo) |

Wyniki trafiają do `output/<miesiąc>/`:

| Plik | Zawartość |
|---|---|
| `truck_log.csv` | jedna linia na ciężarówkę: przejście, hub, czasy kolejki, odprawy i dojazdu, długość trasy, zmiany trasy, czy dowiozła. Z warstwami dodatkowymi także kategoria i masa ładunku, czas rozładunku, awaria, `rejections` (ile razy zawrócona przez K) |
| `summary_crossings.csv`, `summary_hubs.csv` | kolejki na przejściach i czasy dojazdu do hubów |
| `sim_log.txt` | log tekstowy (z `--log-days` / `--log-every`) |
| `diagnoza.png`, `mapa_zniszczen.png`, `diagnoza_*.csv` | z `--diagnose`: trasy i drogi pomalowane zniszczeniami |
| `demand_summary.csv`, `demand_history.csv` | z `--demand`: pokrycie zapotrzebowania na żywność i historia dobowa |
| `kpi_summary.csv`, `bottleneck_*.csv`, `kpi_*.png` | z `--analytics`: wskaźniki, wąskie gardła, wykresy |
| `multiseed_kpi.csv`, `multiseed_summary.csv` | z `--multi-seed` |
| `scenario_<A-E>/` | z `--scenario`: te same pliki dla danego scenariusza |

Ciężarówka odrzucona przez K ma `final_state = odrzucona`, `delivered = False` i puste czasy kolejki i dojazdu.

## Gdzie co jest

| Ścieżka | Do czego |
|---|---|
| `src/config.py` | wszystkie parametry i założenia w jednym miejscu |
| `src/data.py` | Excel → ciężarówki, udziały hubów w miesiącu, ludność hubów (`data/processed/`) |
| `src/network.py` | graf dróg (pobranie, wczytanie, przycięcie do Strefy), przypinanie punktów do węzłów, trasy bazowe |
| `src/damage.py` | UNOSAT → liczba punktów w oczku 500 m → czas przejazdu krawędzi |
| `src/dstar_lite.py`, `src/router.py` | D* Lite: po jednym polu kosztu na hub, ciężarówka czyta z niego następny krok |
| `src/fsm.py` | maszyna stanów ciężarówki |
| `src/events.py` | zdarzenia zmieniające drogi w czasie: fale UNOSAT i blokady |
| `src/sim.py` | pętla SimPy: wjazd, kolejka, odprawa, jazda, rozładunek, doby popytu |
| `src/demand.py` | ładunek → tony, zapas żywności, kalorie na osobę, faza 1–5 |
| `src/stochastic.py` | incydenty drogowe, zamknięcia przejść, awarie |
| `src/analytics.py` | wskaźniki, wąskie gardła, wykresy |
| `src/run.py` | uruchamianie, scenariusze, wiele seedów, tabele |
| `src/diagnose.py` | diagnostyka grafu, tras i zniszczeń |
| `data/raw/` | Excele ONZ (Received, Dispatching) i archiwum UNOSAT |
| `data/processed/` | graf `gaza_drive.graphml`, ciężarówki (`trucks_*.csv`), udziały hubów (`hub_shares_*.csv`, `hub_weights_*.csv`), mapowanie odbiorców na huby (`hub_mapping_*.csv`) |

## Modele

| Model | Stan | Uwagi |
|---|---|---|
| Kolejka M/G/c/K | jest | wjazdy z danych (dzień z Excela, godzina losowana w 8–18), c stanowisk (Kerem Shalom 8, Rafah 6, pozostałe 4), czas odprawy Erlang-3 o średniej 45 min (Gisha 2020). K = największa liczba ciężarówek w systemie przejścia: Kerem Shalom 200, Rafah 250, pozostałe 100 (z długości kolejek, patrz „Źródła”). Przy pełnym systemie ciężarówka zawraca, wraca po 24 h, a po trzech odmowach jest odrzucona. W maju, marcu i listopadzie K nie jest osiągane (największa kolejka ok. 170 ciężarówek). Działa przy przeciążeniu: w scenariuszu E (2x ciężarówek) odrzuconych jest 577 z 8684, a średnia kolejka dowiezionych spada z ok. 23 h do ok. 10 h |
| FSM | jest | wjazd → kolejka → odprawa → jazda ↔ bez drogi → rozładunek → dowiozła / zrezygnowała. Przy pełnym przejściu: zawrócona → wjazd albo odrzucona. Niedozwolone przejście zgłasza błąd |
| D* Lite | jest | pole kosztu do każdego hubu naprawiane przyrostowo po zmianie dróg. Heurystyka wyłączona, więc w praktyce to przyrostowy Dijkstra liczony od hubu wstecz |
| Rozładunek w hubie | jest (`--unloading`) | doki jako zasób SimPy, średnio 30 min |
| Popyt i żywność | jest, uproszczone (`--demand`) | zapas, kalorie na osobę, faza 1–5 z progów 2100/1900/1700/1500 kcal. To nie jest oficjalny IPC, bo liczy tylko kalorie. Wody model nie uwzględnia, bo nie ma jej w danych |
| Zdarzenia losowe | jest (`--stochastic`) | częstości nieskalibrowane, dane ACLED nie są użyte |

Możliwe rozszerzenia w przyszłości: Nagel-Schreckenberg (ruch przed bramką), model tłumu Helbinga, Utility AI, dane ACLED.

## Założenia spoza danych

Wszystkie są w `src/config.py`, oznaczone słowem ZAŁOŻENIE. Najważniejsze:

- czas odprawy 45 min (Gisha 2020), liczba stanowisk (8, 6, 4) dobrana tak, żeby kolejka na Kerem Shalom wychodziła rzędu godzin, pojemność K (200, 250, 100), doba do ponownej próby i trzy próby,
- godzina wjazdu (Excel ma tylko datę) i godziny otwarcia 8–18, przy czym odprawa trwa także po 18:00,
- prędkość ciężarówki 30 km/h, na drogach `service`, `living_street` i `track` mniej,
- spowolnienie od zniszczeń: połowa prędkości przy 150 punktach UNOSAT w oczku 500 m, wszystkie klasy zniszczeń liczone tak samo,
- współrzędne przejść i hubów. Przy każdej oznaczono, czy sprawdzono je na stronie źródła ([W]), pochodzą z dokumentu Logistics Cluster ([P]) czy nie mają źródła ([?]),
- przelicznik palety na tony 0,64 t (z median: 14 t na ciężarówkę przy 22 paletach), ciężarówka bez znanej ilości dostaje 14 t,
- łączna ludność Gazy 2,2 mln (`GAZA_POPULATION`) to jedyna liczba spoza Excela. Ludność hubu to 2,2 mln razy udział hubu w wydaniach danego miesiąca. Zakładamy, że pomoc jedzie tam, gdzie są ludzie,
- doki rozładunkowe (4/3/3/2/2) i czas rozładunku 30 min,
- częstości zdarzeń losowych: incydenty 0,002 na krawędź na dobę, zamknięcia przejść 0,15 (Kerem Shalom) i 0,20 (Rafah) na dobę po 6 ± 2 h, awarie 3% na 100 km,
- próg `MIN_CROSSING_SAMPLES = 30`: przy mniejszej liczbie wierszy dla przejścia używany jest rozkład globalny (działa tylko z `HUB_SHARE_BY_CROSSING = True`).

## Znane ograniczenia

1. **Graf w Rafah (naprawiony 12.11.2026).** Poprzedni graf miał w Rafah 460 krawędzi, a trasy do Hub_Rafah były 2,5–2,9 razy dłuższe niż linia prosta. Po ponownym pobraniu z OSM pas ma 3009 krawędzi, a graf 25 634 węzłów zamiast 14 002. Graf jest przycięty do granicy Strefy plus 500 m (`GAZA_CLIP_BUFFER_M`), bo prostokąt `GAZA_BBOX` obejmuje też Izrael. Trasa jest teraz 1,1–1,3 razy dłuższa niż linia prosta dla wszystkich par przejście-hub. Hub_Rafah (współrzędne z dokumentu z 2009, [P]) przypina się do węzła 783 m od punktu. Zamknięcie jednej krawędzi (`--block-main`) daje objazd ok. 0,5 km, więc scenariusz C prawie nic nie zmienia. Zamknięcie głównej drogi północ–południe wymaga zamknięcia całego przekroju korytarza.
2. **Kolumna `Crossing` w Dispatching nie zgadza się z Received.** W 2024-03 wszystkie 5131 wierszy ma `Rafah`, a w Received 76,5% wjazdów jest przez Kerem Shalom. W 2024-05 Dispatching ma 62% wierszy z „Rafah”, a przez Rafah wjechało 5,5% ciężarówek. Nie wiemy, co ta kolumna oznacza. Dlatego hub jest losowany z rozkładu całego miesiąca i nie zależy od przejścia. Stary wariant włącza `HUB_SHARE_BY_CROSSING = True`.
3. **Zniszczenia działają prawie jak równomierne spowolnienie.** 97% krawędzi ma jakieś zniszczenia, mediana to ok. 190 punktów w oczku (czas ×2,3). Datą zniszczenia jest data zdjęcia, nie ataku. W UNOSAT nie ma dat naprawy, więc domyślnie fale zostają. `--damage-lifetime` zakłada, że po N dniach droga wraca do poprzedniej prędkości.
4. **Kolejka jest skalibrowana tylko co do rzędu wielkości.** Liczba stanowisk nie jest znana (11 komórek Kerem Shalom to miejsca postoju, nie równoległe odprawy). Doniesienia o czasie czekania są anegdotyczne: ok. 11 h, czasem do trzech dni (The World, lipiec 2024), średnio do 20 dni na trasie z Egiptu (Oxfam, marzec 2024). W maju 2024 na Kerem Shalom wychodzi średnio ok. 2,5 h, p95 ok. 10 h, maksimum ok. 16 h (seed 42, bez zdarzeń losowych). Przy 10 stanowiskach średnia spada do 1,3 h, przy 12 do 0,7 h. Czekanie przed dniem z danych (trasa z Egiptu, Al-Arisz, Nitzana) nie jest w modelu. Na małych przejściach (Erez, Western Erez, Gate 96, JLOTS) 4 stanowiska to zgadywanie.
5. **Wyniki z warstwami dodatkowymi zależą od założeń bez danych.** Ludność hubu wynika z udziału wydań, więc pokrycie żywności na hub wychodzi podobne (w 2024-05 ok. 93–100%). Informacja jest w pokryciu łącznym: w 2024-05 ok. 97% (odchylenie 0,15 pp przy 5 seedach). Ludność Rafah wychodzi ok. 1 mln, a w maju 2024 Rafah był wysiedlany, więc jest zawyżona. Średnia kolejka na przejściach to w 2024-05 ok. 126 min bez zdarzeń losowych i ok. 177 min z `--m2` (odchylenie 25 min), więc z `--m2` trzeba raportować średnią z wielu seedów.
6. **Graf zawiera drogi serwisowe i dojazdowe oraz Korytarz Filadelfijski.** Trasy mogą przechodzić przez drogi, których ciężarówki humanitarne nie używają.
7. **Część odbiorców z Excela nie jest zmapowana do hubów.** W 2023-11 to 117 nazw (14% ruchu), głównie szpitale, magazyny ONZ i sklepy. Do rozszerzenia w `HUB_RULES` po sprawdzeniu lokalizacji.

## Plan

- Kalibracja kolejki i doków, scenariusz zamknięcia całego przekroju korytarza, rozszerzenie `HUB_RULES`, ludność z IPC dla danego okresu.
- Porównanie kierunku zmian z raportami IPC, walidacja, raport końcowy.

## Jak dodawać nowe rzeczy

- nowy parametr: `src/config.py`,
- nowy stan ciężarówki: `src/fsm.py` (stany i dozwolone przejścia), potem użyć go w `src/sim.py`,
- nowa warstwa: osobny generator losowy (`default_rng([seed, 11])`) w `sim.py` i flaga w `run.py`, domyślnie wyłączona,
- nowe zdarzenie zmieniające drogi: `events.Event(minuta, opis, apply)`, gdzie `apply(G, damage_model)` zwraca zbiór zmienionych krawędzi `(u, v)`. Router sam naprawi trasy.

## Źródła

- UN OCHA / Logistics Cluster: `Commodities-Received.xlsx`, `Commodities-Dispatching.xlsx` (wjazdy i wydania pomocy),
- UNOSAT: ocena zniszczeń budynków w Strefie Gazy (`unosat_gaza.zip`, warstwa punktowa),
- OpenStreetMap przez OSMnx: sieć dróg.

### Źródła z internetu (parametry kolejki i pojemności K)

Nie ma ich w Excelach. Użyliśmy ich do ustawienia czasu odprawy, liczby stanowisk i pojemności K w `src/config.py`. Dane o czasach są anegdotyczne, więc służą tylko do ustalenia rzędu wielkości (patrz „Znane ograniczenia”, punkt 5).

| Co z niego wzięliśmy | Gdzie użyte | Źródło |
|---|---|---|
| Przekazanie towaru z ciężarówki izraelskiej na palestyńską trwa ok. 45 min. Po stronie izraelskiej jest 11 komórek po 17–25 ciężarówek. Wjazd ok. 6:00–15:00, praca do zmroku. | `SERVICE_MEAN_MIN = 45`, szacunek K | Gisha, [*Kerem Shalom Crossing*, factsheet (2020)](https://gisha.org/UserFiles/File/publications/Kerem_Shalom_Crossing_2020_EN.pdf) |
| Kolejka ciężarówek długości 3 km przy Kerem Shalom i 1,5 km (miejscami po dwie-trzy w poprzek) przy Rafah, marzec 2024. | `CAPACITY_K` (200 i 250, przy założeniu 15 m na ciężarówkę) | Reuters, [*Destruction, lawlessness and red tape hobble aid as Gazans go hungry* (25.03.2024)](https://www.reuters.com/world/middle-east/destruction-lawlessness-red-tape-hobble-aid-gazans-go-hungry-2024-03-25/) |
| Kierowca czekał ok. 11 h, czasem do trzech dni, śpiąc w ciężarówce. | dobór liczby stanowisk (kolejka rzędu godzin) | The World / PRX, [*The struggle to get aid into Gaza* (12.07.2024)](https://theworld.org/stories/2024/07/12/the-struggle-to-get-aid-into-gaza) |
| Ciężarówki stoją w kolejkach średnio ok. 20 dni (według Oxfam, głównie trasa z Egiptu, czyli przed dniem z Excela). | opis ograniczenia, że czekanie przed dniem z danych nie jest w modelu | Oxfam (marzec 2024), cytowany w The National, [*How Israel is obstructing life-saving aid from entering Gaza* (19.03.2024)](https://www.thenationalnews.com/mena/palestine-israel/2024/03/19/how-israel-blocks-aid-to-gaza/) |
| Trasa z Egiptu przez Al-Arisz, Rafah i Nitzana trwa 4–5 tygodni. Jedna odrzucona pozycja cofa całą partię. | uzasadnienie zawracania i ponownych prób przy K | Lekarze bez Granic, [*What it takes to get lifesaving supplies into Gaza*](https://www.doctorswithoutborders.org/latest/impossible-task-getting-lifesaving-supplies-gaza) |
| Kierowcy z Egiptu tygodniami czekają na zgodę, a inspekcje trwają ok. 18 h. Ze 150–200 ciężarówek przyjmowano 15–20. | uzasadnienie odrzucania ciężarówek | CNN, [*What the Gaza blockade looks like through the eyes of Egyptian truck drivers* (21.08.2025)](https://www.cnn.com/2025/08/21/middleeast/gaza-blockade-egypt-truck-drivers-israel-intl) |
| W czerwcu 2026 z Egiptu rozładowano tylko 52% zgłoszonych ciężarówek, bo część była zawracana. W listopadzie 2025 przez Nitzana zawrócono 48%. | uzasadnienie odrzucania ciężarówek | Logistics Cluster Palestine, protokoły spotkań: [2 lipca 2026](https://logcluster.org/sites/default/files/public/2026-07/logistics-clusterpalestinemeeting-minutes_260702.pdf), [listopad 2025](https://reliefweb.int/attachments/1ffe4842-e338-5420-b06d-5914d9178b84/Logistics%20Cluster_Palestine_Gaza_Meeting%20Minutes_251111.pdf) |

Wartości, które **nie** pochodzą z żadnego źródła, tylko z naszego założenia: liczba stanowisk (8 i 6, na małych przejściach 4), 15 m na ciężarówkę, doba do ponownej próby i trzy próby.
