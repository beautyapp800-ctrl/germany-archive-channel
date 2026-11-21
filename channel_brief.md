# Channel brief — Deutschland 1945–1970 (крок 1, чекає вибору власника)

Репо: beautyapp800-ctrl/germany-archive-channel (публічний). Двигун скопійовано з archive-channel
(сам archive-channel не змінено). Автоматизація ВИМКНЕНА: робочі workflow лежать у `workflows_off/`,
активні лише ручні `voice-samples` і `branding` (нічого не завантажують на YouTube).

## 1. Назва каналу + handle (перевірено 21.11.2026: youtube.com/@handle → 404 = каналу немає)

| # | Назва | Handle | Ідея |
|---|---|---|---|
| 1 | **Als Oma jung war** | @AlsOmaJungWar | емоційна, «розповідь з родини», легко запам'ятати й шукати |
| 2 | **Wirtschaftswunder-Archiv** | @WirtschaftswunderArchiv | пошукове слово №1 теми + «архів» = довіра |
| 3 | **Von Trümmern zum Wunder** | @VonTruemmernZumWunder | уся дуга каналу 1945→1970 в одній фразі |

Запасні вільні: @Nachkriegsjahre, @ZurueckNach1950, @DeutschlandNach45, @AlsOpaJungWar.
Вільний handle може зайняти хтось інший — краще закріпити в Studio одразу після вибору.

## 2. Аватар і банер (3+3, стиль обкладинок) — `branding/options/`

Основа — справжні фото з перевіреною ліцензією (`branding/options/sources.json`), класичне покращення
(контраст, насиченість, різкість, Lanczos), «вирізаний» герой — пікселі самого фото з білим контуром.
Чорно-білі фото мають теплий тонований грейд (не видається за колір).

- Аватар 1 — «Käfer»: вирізаний мільйонний Käfer (1955) з білим контуром на жовто-помаранчевому сонці, червоне кільце.
- Аватар 2 — «Luftbrücke»: вирізаний C-54 «Rosinenbomber» на блакитному сонці + жовте «1948».
- Аватар 3 — «Stempel»: руїни 1945 + великий червоний штамп «45-70».
- Банер 1 — Tempelhof 1948 + назва 1 + Käfer + цінник «NR. 1.000.000».
- Банер 2 — Рейн (Nationaal Archief, CC0, справжній колір) + назва 2 + Käfer + штамп «ECHT?».
- Банер 3 — руїни 1945 + назва 3 + вирізаний C-54.
- Перевірка читабельності: `check_readability.jpg` (аватари колом 400/98/48 px, безпечна зона банера як на телефоні).
Під обраною назвою банер перероблю з потрібним текстом.

## 3. Опис каналу (Studio → Customization → Basic info)

```
Deutschland 1945 bis 1970 in echten Archivfilmen: Trümmer und Wiederaufbau, Luftbrücke, Währungsreform, Wirtschaftswunder und der Alltag in Ost und West.
Neue Dokumentationen jeden Dienstag und Freitag um 18 Uhr.

Was kostete ein Käfer im Jahr 1955? Wovon lebte man im Hungerwinter 1946/47? Wie versorgte man zwei Millionen Berliner aus der Luft? Jede Folge beantwortet eine Frage aus den Nachkriegsjahren mit konkreten Zahlen, Preisen in D-Mark und Originalaufnahmen der Zeit.

Alle Filme und Fotos sind gemeinfrei, CC0 oder CC BY; jede Quelle steht in der Videobeschreibung. Restaurierung nur klassisch (Entrauschen, Stabilisieren, leichtes Hochskalieren). Die Sprecherstimme ist synthetisch.
```

## 4. Ключові слова (Studio → Settings → Channel → Keywords)

Nachkriegszeit, Wirtschaftswunder, Deutschland 1950er, Deutschland 1960er, Wiederaufbau, Trümmerfrauen, Luftbrücke, Berliner Blockade, Rosinenbomber, Währungsreform 1948, D-Mark, Schwarzmarkt, Hungerwinter, Marshallplan, BRD Geschichte, DDR Alltag, Mauerbau 1961, Berlin Geschichte, Zeitgeschichte, Archivfilm, Dokumentation, Alltag früher, Preise früher, Käfer, Geschichte Deutschland

## 5. Голос — 3 зразки (Piper, НЕ Thorsten) — `voice/samples/`

Прослухано автоматично на GitHub: усі німецькі голоси Piper з вільною ліцензією + усі 236 дикторів
de_DE-mls-medium, оцінка природності UTMOS (1–5). Виключено: thorsten* (Urzeit-Archiv),
pavoque (ліцензія CC BY-NC-SA — некомерційна).

VOICE_TABLE

## 6. Матеріали — скільки знайдено (пошук за метаданими 21.11.2026, відео не завантажувались)

| Джерело | Знайдено | Придатне |
|---|---|---|
| archive.org, фільми про Німеччину 1945–75 | 1 162 | 352 з позначкою PD/CC0/CC BY на сторінці |
| — з них після відсіву війни, процесів, нацистської тематики, ігрового кіно, дублів | | **69** |
| NARA (дзеркало FedFlix): цивільні сюжети 1946–72 (роботи уряду США = PD) | 79 | ще без позначки — кожен перевірю на сторінці каталогу NARA перед використанням |
| Universal Newsreel (PD), сюжети про Німеччину 1946–67 | 35 | у т.ч. вище |
| Фото: Nationaal Archief / Anefo (CC0), US Army / USAF / USACE (PD) на Commons | сотні | ліцензія перевіряється для кожного файлу |

Разом приблизно **110–120 унікальних фільмів/сюжетів**, з них **69 з уже підтвердженою позначкою на сторінці**.
Викинуто: «Welt im Film» (не вважаємо вільним), DEFA, Bundesarchiv (CC BY-SA), британські хроніки.

**Чесно про перекіс:** вільного кіно найбільше про 1945–49 (окупація, голод, руїни, Luftbrücke) і про
1961–63 (Мур, Checkpoint Charlie, Кеннеді). Споживче Wirtschaftswunder (мода, кухня, ТБ, відпустки, школа)
і побут НДР — дуже мало вільного відео; такі теми можливі лише на фото і проходитимуть перевірку
матеріалу до сценарію. Тому стартові теми зміщені туди, де матеріалу достатньо.

## 7. 20 тем на старт

Таблиця з гачками й оцінкою матеріалу — `docs/topics_start.md`. Коротко:
1 Luftbrücke · 2 Rosinenbomber · 3 Tempelhof · 4 Währungsreform 1948 · 5 Schwarzmarkt · 6 Hungerwinter ·
7 CARE-Pakete · 8 Trümmerfrauen · 9 Wohnungsnot 1946 · 10 Flüchtlinge und Vertriebene · 11 Marshallplan ·
12 Der Käfer · 13 Der Rhein · 14 17. Juni 1953 · 15 Flucht nach West-Berlin · 16 13. August 1961 ·
17 Checkpoint Charlie · 18 Kennedy in Berlin · 19 GI-Familien in Deutschland · 20 West-Berlin 1953.

## 8. Google Cloud проєкт — рекомендація: **hypothetica-511509**

- Квота YouTube Data API — 10 000 одиниць/день на проєкт. День завантаження цього каналу ≈ 2 500
  (videos.insert 1 600 + 2× captions.insert по 400 + thumbnails.set 50 + списки відео).
- gen-lang-client-0367233741 уже везе 3 канали (Yesterday in Color — ті самі дні Di/Fr, Urzeit-Archiv,
  Closed Tabs) і, судячи з назви, Gemini-ключі — найбільш завантажений.
- yt-factory-510411 — Huge To Scale (+ ймовірно щоденні канали yt-factory/yt-kids) — щоденні завантаження.
- hypothetica-511509 — What If + America Over Time (Mo/Fr): у п'ятницю разом ≈ 4 200 з 10 000, запас великий.
Після вибору: я запущу `scripts/youtube_auth.py` на ПК, вам лише вибрати акаунт/канал у браузері.

## 9. Далі (після вашого вибору)

Назва + аватар + банер + голос → крок 2: 1 пробне відео (рендер на GitHub), 3 кандидати обкладинки,
субтитри de + en — показую вам. Автоматизацію вмикаю лише після вашого «ок».
