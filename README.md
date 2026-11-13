# Symulacje systemów dyskretnych: logistyka pomocy humanitarnej w Strefie Gazy

Symulacja dostaw pomocy humanitarnej do Strefy Gazy: kolejka na przejściach granicznych, przejazd po zniszczonych drogach do hubów, rozładunek i pokrycie zapotrzebowania na żywność.
Model odtwarza jeden miesiąc z danych ONZ. Warstwy dodatkowe (rozładunek, żywność, zdarzenia losowe, analityka) włącza się flagami. Bez flag działa sama kolejka i dojazd.

## Co ta baza robi

Domyślnie maj 2024 (`config.MONTH`). Inny miesiąc wybierasz przez `--month`, np. `python src/run.py --month 2023-11`. Dane Excela obejmują październik 2023 – styczeń 2025.

1. Każdy wiersz z `Commodities-Received.xlsx` to jedna ciężarówka wjeżdżająca przez przejście graniczne.
2. Na przejściu ciężarówka czeka w kolejce i jest odprawiana (SimPy). Przejście ma skończoną pojemność K (odprawa plus kolejka). Gdy jest pełne, ciężarówka zawraca, wraca po dobie, a po trzech odmowach jest odrzucona na stałe.
3. Potem jedzie po grafie dróg z OpenStreetMap do jednego z hubów. Trasę wyznacza D* Lite. Hub jest losowany spośród hubów tej samej części Strefy co przejście (północ: Erez, Western Erez, Gate 96, JLOTS; południe: Kerem Shalom, Rafah, Kissufim), z wagami z tonażu żywności wydanej w danym miesiącu w `Commodities-Dispatching`. Przejście wjazdu pochodzi z `Received`, bo kolumna `Crossing` w `Dispatching` jest niespójna (patrz „Znane ograniczenia”, punkt 2).
4. Zniszczenia z UNOSAT spowalniają drogi. Stan na 1. dzień miesiąca jest punktem startu, a nowe fale wchodzą w dniach zdjęć. `--damage-lifetime N` zdejmuje falę po N dniach od zdjęcia. Zmiana trasy zapisuje się w `replan_causes` i w logu tekstowym.
5. Opcjonalnie można zamknąć najruchliwszą drogę. Ciężarówki bez trasy czekają i po 72 h rezygnują.

Warstwy dodatkowe (flagi w „Szybkim starcie”):

- **Rozładunek (`--unloading`).** W hubie ciężarówka czeka na wolny dok i rozładowuje się średnio 30 min.
- **Popyt na żywność (`--demand`).** Ładunek jest przeliczany na tony. Co dobę ludność hubu zjada zapas (do 2100 kcal na osobę), a z kalorii wychodzi uproszczona faza 1–5. Ludność hubu to liczba mieszkańców gubernatorstwa z raportów IPC (osobna dla każdej doby), a nie wynik rozkładu pomocy. Szczegóły w „Ludność i żywność”.
- **Zdarzenia losowe (`--stochastic`).** Incydenty drogowe, zamknięcia przejść i awarie ciężarówek. Mają osobny generator losowy, więc nie zmieniają pozostałych losowań.
- **Analityka (`--analytics`), scenariusze (`--scenario`), wiele seedów (`--multi-seed`).**

**Weryfikacja:** rozkład hubów w symulacji vs rozkład oczekiwany (udziały hubów dla przejścia z `hub_shares_*.csv` ważone liczbą ciężarówek na przejściu):

| Miesiąc | Ciężarówek | Maks. różnica | Szum próbkowania σ |
|---|---|---|---|
| 2023-11 | 2545 | 0,72 pp | 0,97 pp |
| 2024-03 | 4993 | 0,47 pp | 0,41 pp |
| 2024-05 | 4342 | 0,58 pp | 0,66 pp |

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
| `diagnoza.png`, `mapa_zniszczen.png`, `diagnoza_*.csv` | z `--diagnose`: wszystkie przejścia i huby oraz trasy przejście → hub na jednej mapie (kolor = przejście, rysowane tylko dla przejść z ruchem w miesiącu, na wspólnych odcinkach linie biegną obok siebie), oraz drogi pomalowane zniszczeniami |
| `demand_summary.csv`, `demand_history.csv` | z `--demand`: pokrycie zapotrzebowania na żywność i historia dobowa |
| `kpi_summary.csv`, `bottleneck_*.csv`, `kpi_*.png` | z `--analytics`: wskaźniki, wąskie gardła, wykresy |
| `multiseed_kpi.csv`, `multiseed_summary.csv` | z `--multi-seed` |
| `scenario_<A-E>/` | z `--scenario`: te same pliki dla danego scenariusza |

Ciężarówka odrzucona przez K ma `final_state = odrzucona`, `delivered = False` i puste czasy kolejki i dojazdu.

## Gdzie co jest

| Ścieżka | Do czego |
|---|---|
| `src/config.py` | wszystkie parametry i założenia w jednym miejscu |
| `src/data.py` | Excel → ciężarówki, udziały hubów w miesiącu (`data/processed/`), ludność hubów z IPC (`hub_population_daily`) |
| `src/network.py` | graf dróg (pobranie, wczytanie, przycięcie do Strefy), przypinanie punktów do węzłów, trasy bazowe |
| `src/damage.py` | UNOSAT → liczba punktów w oczku 500 m → czas przejazdu krawędzi |
| `src/dstar_lite.py`, `src/router.py` | D* Lite: po jednym polu kosztu na hub, ciężarówka czyta z niego następny krok |
| `src/fsm.py` | maszyna stanów ciężarówki |
| `src/events.py` | zdarzenia zmieniające drogi w czasie: fale UNOSAT i blokady |
| `src/sim.py` | pętla SimPy: wjazd, kolejka, odprawa, jazda, rozładunek, doby popytu |
| `src/demand.py` | ładunek → tony, zapas żywności, kalorie na osobę, faza kaloryczna 1–5 |
| `src/stochastic.py` | incydenty drogowe, zamknięcia przejść, awarie |
| `src/analytics.py` | wskaźniki, wąskie gardła, wykresy |
| `src/run.py` | uruchamianie, scenariusze, wiele seedów, tabele |
| `src/diagnose.py` | diagnostyka grafu, tras i zniszczeń |
| `data/raw/` | Excele ONZ (Received, Dispatching) i archiwum UNOSAT |
| `data/processed/` | graf `gaza_drive.graphml`, ciężarówki (`trucks_*.csv`), udziały hubów (`hub_shares_*.csv`, plik `.method` unieważnia cache po zmianie reguły), mapowanie odbiorców na huby (`hub_mapping_*.csv`) |

## Modele

| Model | Stan | Uwagi |
|---|---|---|
| Kolejka M/G/c/K | jest | wjazdy z danych (dzień z Excela, godzina losowana w 8–18), c stanowisk (Kerem Shalom 8, Rafah 6, pozostałe 4), czas odprawy Erlang-3 o średniej 45 min (Gisha 2020). K = największa liczba ciężarówek w systemie przejścia: Kerem Shalom 200, Rafah 250, pozostałe 100 (z długości kolejek, patrz „Źródła”). Przy pełnym systemie ciężarówka zawraca, wraca po 24 h, a po trzech odmowach jest odrzucona. W maju, marcu i listopadzie K nie jest osiągane (największa kolejka ok. 170 ciężarówek). Działa przy przeciążeniu: w scenariuszu E (2x ciężarówek) odrzuconych jest 577 z 8684, a średnia kolejka dowiezionych spada z ok. 23 h do ok. 10 h |
| FSM | jest | wjazd → kolejka → odprawa → jazda ↔ bez drogi → rozładunek → dowiozła / zrezygnowała. Przy pełnym przejściu: zawrócona → wjazd albo odrzucona. Niedozwolone przejście zgłasza błąd |
| D* Lite | jest | pole kosztu do każdego hubu naprawiane przyrostowo po zmianie dróg. Heurystyka wyłączona, więc w praktyce to przyrostowy Dijkstra liczony od hubu wstecz |
| Rozładunek w hubie | jest (`--unloading`) | doki jako zasób SimPy, średnio 30 min |
| Popyt i żywność | jest, uproszczone (`--demand`) | zapas, ludność z IPC, kalorie na osobę, faza kaloryczna 1–5 z progów 2100/1900/1700/1500 kcal. To nie jest klasyfikacja IPC, bo liczy tylko kalorie. Wody model nie uwzględnia, bo nie ma jej w danych. Opis w „Ludność i żywność” |
| Zdarzenia losowe | jest (`--stochastic`) | częstości nieskalibrowane, dane ACLED nie są użyte |

Możliwe rozszerzenia w przyszłości: Nagel-Schreckenberg (ruch przed bramką), model tłumu Helbinga, Utility AI, dane ACLED.

## Ludność i żywność

**Co to IPC.** IPC (Integrated Food Security Phase Classification) to skala ONZ, FAO i WFP do oceny braku żywności: faza 1 (minimalna), 2 (napięta), 3 (kryzys), 4 (zagrożenie), 5 (katastrofa lub głód). Raporty IPC dla Gazy podają też liczbę mieszkańców gubernatorstw. Używamy ich w dwóch miejscach. Liczby ludności to dane z raportów. Nazwy faz 1–5 pożyczamy do wskaźnika z kalorii, ale to **nie jest** klasyfikacja IPC, bo prawdziwe IPC bierze pod uwagę też strategie przetrwania, odżywienie dzieci i śmiertelność. Dlatego w plikach wyniku kolumny nazywają się `kcal_phase` i `kcal_phase_month`.

**1. Ludność huba (`data.hub_population_daily`, osobno dla każdej doby miesiąca).**
- Z raportów IPC mamy liczby w trzech grupach: północ (North Gaza + Gaza), środek (Deir al-Balah + Khan Younis) i Rafah. Punkty są w `IPC_POPULATION`, a ich źródła w tabeli niżej.
- Między punktami interpolujemy liniowo po dniach. Przed pierwszym punktem (grudzień 2023) i po ostatnim wartość jest stała.
- Grupę dzielimy na huby w stałej proporcji z tabeli IPC z kwietnia 2025 (`IPC_SPLIT`): North Gaza 310 : Gaza 740, Deir al-Balah 400 : Khan Younis 620.
- Hub reprezentuje całe swoje gubernatorstwo. Ludność nie zależy od tego, ile pomocy tam jedzie.
- Przykład, maj 2024, Rafah: 1,33 mln do 6 maja, ok. 200 tys. 26 maja, ok. 166 tys. 31 maja. Średnia z miesiąca to 760 tys.

**2. Dokąd jedzie ciężarówka.** Hub jest losowany spośród hubów tej samej części Strefy co przejście (`CROSSING_HUBS` w `config.py`):
- północ (Erez, Western Erez, Gate 96, JLOTS) → Gaza City, North Jabalia,
- południe (Kerem Shalom, Rafah, Kissufim) → Deir al-Balah, Khan Younis, Rafah.

Wagi to **tonaż żywności** wydanej w miesiącu w `Commodities-Dispatching` (tonaż to ilość razy przelicznik jednostki, kategoria `Food Items`). Z tego pliku bierzemy tylko rozkład, bo Dispatching zawiera ok. 38% żywności z Received (maj 2024: 19,5 tys. t wobec 51,7 tys. t). Gdy w części Strefy nie ma w miesiącu żadnych wydań, wagi wynikają z ludności hubów. Podział na północ i południe zgadza się z danymi: Dispatching kieruje przejście Western Erez wyłącznie do Gaza City (6,4 tys. t), a nic z niego na południe. Przypisanie Gate 96, JLOTS i Kissufim do stref to nasze założenie. Przykład, maj 2024: z Kerem Shalom 52% do Rafah, 31% do Deir al-Balah, 17% do Khan Younis, a z przejść północnych 99,6% do Gaza City, 0,4% do North Jabalia (w Dispatching prawie nic nie trafia do Jabalii, mimo że hub ma ok. 89 tys. mieszkańców według przyjętego podziału).

**3. Ile żywności wiezie ciężarówka.** Ilość i jednostka z `Received` zamieniają się na tony: `MT` bez zmian, palety razy 0,64 t, jednostka `Truck` razy 14 t, pozostałe i brak ilości to 14 t, całość ograniczona do 0,1–40 t. Do zapasu trafia tylko kategoria `Food Items`. Medyczne, niespożywcze i mieszane nie liczą się jako żywność.

**4. Zapas i zjadanie (raz na dobę).**
- Po rozładunku zapas huba rośnie o tony ciężarówki.
- Potrzeba doby = ludność doby × 2100 kcal / 3,3 mln kcal na tonę. Dla 760 tys. osób to 484 t na dobę.
- Zapas jest wspólny w grupie IPC (północ: North Jabalia + Gaza City, środek: Deir al-Balah + Khan Younis, Rafah osobno; `FOOD_SHARED_WITHIN_IPC_GROUP`). Zjedzone grupy = min(zapas grupy, suma potrzeb hubów grupy). Zjedzone dzieli się na huby proporcjonalnie do potrzeb, więc huby jednej grupy mają to samo kcal na osobę. Zapas na koniec w tabeli to udział huba (według ludności) w zapasie grupy. Uzasadnienie: IPC podaje ludność tylko dla grupy, a podział na huby to nasze założenie, więc nie ma podstaw, by traktować huby oddalone o 6–13 km jako odcięte od siebie.
- Kalorie na osobę = zjedzone × 3,3 mln / ludność.
- Faza dobowa (`kcal_phase` w `demand_history.csv`): od 2100 kcal faza 1, od 1900 faza 2, od 1700 faza 3, od 1500 faza 4, poniżej faza 5.
- Faza miesiąca (`kcal_phase_month` w `demand_summary.csv`): te same progi, ale dla średnich kcal na osobę z całego miesiąca (zjedzone razy 3,3 mln / suma ludności po dobach). `days_phase_4_5` to liczba dób z fazą 4 lub 5, a `stock_end_days` to zapas na koniec miesiąca wyrażony w dobach potrzeby.
- Pokrycie huba = suma zjedzonego / suma potrzeb z całego miesiąca. Pokrycie łączne liczone jest tak samo po wszystkich hubach.
- Symulacja liczy wszystkie doby miesiąca, także po ostatniej ciężarówce.
- **Górne ograniczenie** to min(dostawy, potrzeby) / potrzeby. Tyle wyniosłoby pokrycie, gdyby żywność mogła płynąć także między grupami IPC. Różnica między pokryciem łącznym a górnym ograniczeniem to koszt nierównego rozdziału pomocy między grupami.

**Czego to nie uwzględnia:** rynku, własnej produkcji i zapasów domowych (pokrycie liczy tylko pomoc z Excela), strat, przepływu żywności między grupami IPC, wody, różnic między grupami wiekowymi. Zapas startuje od zera.

**Wynik, maj 2024 (seed 42, `--demand`):**

| Hub (grupa IPC) | Ludność (średnio) | Potrzeba [t] | Dowieziono do huba [t] | Zjedzono [t] | Zapas na koniec [t] (doby potrzeby) | Pokrycie | kcal na osobę (średnio) | Faza miesiąca | Dób w fazie 4–5 |
|---|---|---|---|---|---|---|---|---|---|
| North_Jabalia (północ) | 88 571 | 1 747 | 61 | 1 596 | 1 799 (32) | 91,3% | 1918 | 2 | 3 |
| Gaza_City (północ) | 211 429 | 4 171 | 11 438 | 3 809 | 4 295 (32) | 91,3% | 1918 | 2 | 3 |
| Deir_al_Balah (środek) | 457 466 | 9 025 | 12 927 | 7 714 | 0 | 85,5% | 1795 | 3 | 6 |
| Khan_Younis (środek) | 709 072 | 13 988 | 6 743 | 11 956 | 0 | 85,5% | 1795 | 3 | 6 |
| Rafah (Rafah) | 760 006 | 14 993 | 20 563 | 11 539 | 9 025 (85) | 77,0% | 1616 | 4 | 7 |
| **Razem** | 2 226 544 | 43 924 | 51 732 | 36 613 | 15 119 | **83,4%** | | | |

Kolumna „Dowieziono do huba” pokazuje, gdzie ciężarówki rozładowały towar. Zjedzono więcej niż dowieziono do North_Jabalia, bo zapas północy jest wspólny z Gaza City, do którego jedzie niemal cała północna pomoc. Przy 5 seedach pokrycie łączne to 82,8% (odchylenie 0,4 pp), a górne ograniczenie 100%. Północ (grupa IPC) dostaje 11,5 tys. t przy potrzebie 5,9 tys. t, ale zapas pojawia się w trakcie miesiąca (start od zera), więc na początku są dni z fazą 4–5. Rafah ma w miesiącu 20,6 tys. t dostaw przy potrzebie 15 tys. t, a mimo to pokrycie 77%: zapas z pierwszych dni kończy się ok. 9. doby i do ok. 17. doby prawie nic nie dojeżdża (kcal na osobę 0–1300), a potem dostawy rosną, gdy ludność spada z 1,33 mln do 0,17 mln (Rafah po ewakuacji), więc zapas na koniec miesiąca wystarcza na 85 dób. Ten zapas nie pomaga środkowi, bo żywność nie płynie między grupami (ograniczenie 5).

## Założenia spoza danych

Wszystkie są w `src/config.py`, oznaczone słowem ZAŁOŻENIE. Najważniejsze:

- czas odprawy 45 min (Gisha 2020), liczba stanowisk (8, 6, 4) dobrana tak, żeby kolejka na Kerem Shalom wychodziła rzędu godzin, pojemność K (200, 250, 100), doba do ponownej próby i trzy próby,
- godzina wjazdu (Excel ma tylko datę) i godziny otwarcia 8–18, przy czym odprawa trwa także po 18:00,
- prędkość ciężarówki 30 km/h, na drogach `service`, `living_street` i `track` mniej,
- spowolnienie od zniszczeń: połowa prędkości przy 150 punktach UNOSAT w oczku 500 m, wszystkie klasy zniszczeń liczone tak samo,
- współrzędne przejść i hubów. Przy każdej oznaczono, czy sprawdzono je na stronie źródła ([W]), pochodzą z dokumentu Logistics Cluster ([P]) czy nie mają źródła ([?]),
- przelicznik palety na tony 0,64 t (z median: 14 t na ciężarówkę przy 22 paletach), ciężarówka bez znanej ilości dostaje 14 t,
- ludność hubów: punkty IPC, podział grup IPC na gubernatorstwa i dwie liczby dla Rafah z raportów (opis i źródła w „Ludność i żywność”),
- zjadanie żywności: 2100 kcal na osobę na dobę, 3,3 mln kcal w tonie, zapas startuje od zera, brak strat, żywność jest wspólna w grupie IPC i nie płynie między grupami,
- doki rozładunkowe (4/3/3/2/2) i czas rozładunku 30 min,
- częstości zdarzeń losowych: incydenty 0,002 na krawędź na dobę, zamknięcia przejść 0,15 (Kerem Shalom) i 0,20 (Rafah) na dobę po 6 ± 2 h, awarie 3% na 100 km,
- przypisanie przejść do stref północ / południe (`CROSSING_HUBS`): Western Erez wynika z Dispatching, Gate 96, JLOTS i Kissufim to założenie geograficzne,
- przypisanie odbiorców z Dispatching do hubów po nazwie (`HUB_RULES`). Nazw bez miejscowości (np. „Miraj Stores”) nie zgadujemy.

## Znane ograniczenia

1. **Graf w Rafah (naprawiony 12.11.2026).** Poprzedni graf miał w Rafah 460 krawędzi, a trasy do Hub_Rafah były 2,5–2,9 razy dłuższe niż linia prosta. Po ponownym pobraniu z OSM pas ma 3009 krawędzi, a graf 25 634 węzłów zamiast 14 002. Graf jest przycięty do granicy Strefy plus 500 m (`GAZA_CLIP_BUFFER_M`), bo prostokąt `GAZA_BBOX` obejmuje też Izrael. Trasa jest teraz 1,1–1,3 razy dłuższa niż linia prosta dla wszystkich par przejście-hub. Hub_Rafah (współrzędne z dokumentu z 2009, [P]) przypina się do węzła 783 m od punktu. Zamknięcie jednej krawędzi (`--block-main`) daje objazd ok. 0,5 km, więc scenariusz C prawie nic nie zmienia. Zamknięcie głównej drogi północ–południe wymaga zamknięcia całego przekroju korytarza.
2. **Kolumna `Crossing` w Dispatching nie zgadza się z Received.** W 2024-03 wszystkie 5131 wierszy ma `Rafah`, a w Received 76,5% wjazdów jest przez Kerem Shalom. W 2024-05 Dispatching ma 62% wierszy z „Rafah”, a przez Rafah wjechało 5,5% ciężarówek. Nie wiemy, co ta kolumna oznacza. Dlatego nie przypisujemy hubów po przejściu z Dispatching. Hub zależy tylko od strefy przejścia z Received (północ / południe), a wagi w strefie to tonaż żywności z całego miesiąca.
3. **Zniszczenia działają prawie jak równomierne spowolnienie.** 97% krawędzi ma jakieś zniszczenia, mediana to ok. 190 punktów w oczku (czas ×2,3). Datą zniszczenia jest data zdjęcia, nie ataku. W UNOSAT nie ma dat naprawy, więc domyślnie fale zostają. `--damage-lifetime` zakłada, że po N dniach droga wraca do poprzedniej prędkości.
4. **Kolejka jest skalibrowana tylko co do rzędu wielkości.** Liczba stanowisk nie jest znana (11 komórek Kerem Shalom to miejsca postoju, nie równoległe odprawy). Doniesienia o czasie czekania są anegdotyczne: ok. 11 h, czasem do trzech dni (The World, lipiec 2024), średnio do 20 dni na trasie z Egiptu (Oxfam, marzec 2024). W maju 2024 na Kerem Shalom wychodzi średnio ok. 2,5 h, p95 ok. 10 h, maksimum ok. 16 h (seed 42, bez zdarzeń losowych). Przy 10 stanowiskach średnia spada do 1,3 h, przy 12 do 0,7 h. Czekanie przed dniem z danych (trasa z Egiptu, Al-Arisz, Nitzana) nie jest w modelu. Na małych przejściach (Erez, Western Erez, Gate 96, JLOTS) 4 stanowiska to zgadywanie.
5. **Wyniki żywności zależą od założeń bez danych.** Podział grup IPC na gubernatorstwa jest stałą proporcją z kwietnia 2025. Rafah w maju i czerwcu 2024 ma dwie liczby z raportów zamiast tabeli IPC. Żywność jest wspólna w grupie IPC, ale nie płynie między grupami, więc nadwyżka w Rafah nie pomaga środkowi ani północy. Przypisanie przejść do stref jest założeniem, a w Dispatching od czerwca 2024 prawie nie ma wydań na północy, więc wagi North_Jabalia / Gaza City wynikają wtedy z ludności. Zapas startuje od zera, a pokrycie liczy tylko pomoc z Excela. Rozkład hubów pochodzi z Dispatching, które obejmuje ok. 38% tonażu z Received. W listopadzie 2023 12% odbiorców z Dispatching nie jest zmapowanych do hubów. Średnia kolejka na przejściach to w 2024-05 ok. 126 min bez zdarzeń losowych i ok. 177 min z `--m2` (odchylenie 25 min), więc z `--m2` trzeba raportować średnią z wielu seedów.
6. **Graf zawiera drogi serwisowe i dojazdowe oraz Korytarz Filadelfijski.** Trasy mogą przechodzić przez drogi, których ciężarówki humanitarne nie używają.
7. **Część odbiorców z Excela nie jest zmapowana do hubów.** W 2023-11 to 117 nazw (14% ruchu), głównie szpitale, magazyny ONZ i sklepy. Do rozszerzenia w `HUB_RULES` po sprawdzeniu lokalizacji.

## Plan

- Kalibracja kolejki i doków, scenariusz zamknięcia całego przekroju korytarza, rozszerzenie `HUB_RULES`, przepływ żywności między grupami IPC.
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

### Źródła z internetu (ludność hubów)

Użyte w `IPC_POPULATION` i `IPC_SPLIT` w `src/config.py`.

| Okres | Liczby | Źródło |
|---|---|---|
| 24.11–7.12.2023 i prognoza do 7.02.2024 | północ 600 tys. (prognoza 500 tys.), południe 1 626 544 (prognoza 1 726 544), razem 2 226 544 | IPC, [*Gaza Strip: Acute Food Insecurity, Nov 2023 – Feb 2024*](https://www.ipcinfo.org/fileadmin/user_upload/ipcinfo/docs/IPC_Gaza_Acute_Food_Insecurity_Nov2023_Feb2024.pdf) |
| 15.02–15.03.2024 | North Gaza + Gaza 300 tys., Deir al-Balah + Khan Younis 600 tys., Rafah 1 326 544 | IPC, [*Special Brief (18.03.2024)*](https://www.un.org/unispal/wp-content/uploads/2024/03/IPC_Gaza_Strip_Acute_Food_Insecurity_Feb_July2024_Special_Brief.pdf) |
| koniec maja 2024 | w Rafah zostaje ok. 200 tys. po wysiedleniu 945 tys. osób | UNRWA (29.05.2024), cytowane w [raporcie Famine Review Committee (czerwiec 2024)](https://www.un.org/unispal/wp-content/uploads/2024/06/IPC_Famine_Review_Committee_Report_Gaza_June2024.pdf) |
| połowa czerwca 2024 | w Rafah zostaje ok. 65 tys. | UNRWA, cytowane przez [FEWS NET, *Gaza Targeted Analysis* (czerwiec 2024)](https://fews.net/middle-east-and-europe/gaza/targeted-analysis/june-2024/print) |
| 1.09–31.10.2024 i prognoza do 30.04.2025 | północ 430 715, Deir al-Balah + Khan Younis 1 665 702, Rafah 44 201, razem 2 140 618 | IPC, [*Special Brief, Sept 2024 – Aug 2025*](https://www.ipcinfo.org/fileadmin/user_upload/ipcinfo/docs/IPC_Gaza_Strip_Acute_Food_Insecurity_Malnutrition_Sept2024_Aug2025_Special_Brief.pdf) |
| 1.04–10.05.2025 (tylko do podziału grup) | North Gaza 310 tys., Gaza 740 tys., Deir al-Balah 400 tys., Khan Younis 620 tys., Rafah 30 tys. | IPC, [*Special Brief, Apr – Sep 2025*](https://www.ipcinfo.org/fileadmin/user_upload/ipcinfo/docs/IPC_Gaza_Strip_Acute_Food_Insecurity_Apr_Sep2025_Special_Report.pdf) |

Wartości z założenia: podział grup IPC na pojedyncze gubernatorstwa, podział południa w grudniu 2023 – styczniu 2024, stan północy w maju–czerwcu 2024 (300 tys. jak w marcu) i interpolacja liniowa między punktami.
