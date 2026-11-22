"""One-off: the topic queue (topics/queue.json) from candidate titles, keeping only what exists.

Each topic: de.wikipedia articles (read in full, >= 9000 characters together, or the topic is dropped),
Commons categories that exist, archive.org search words for US-government films.
"""
import json
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import material_de, sources  # noqa: E402

T = [
 ("tempelhof", "Tempelhof: Der Flughafen, der Berlin rettete", "1948", "Berlin", 1948,
  ["Flughafen Berlin-Tempelhof", "Berliner Luftbrücke"], ["Category:Berlin Tempelhof Airport", "Category:Berlin Airlift", "Category:Tempelhof Airport in 1948"],
  ["tempelhof", "berlin airlift", "berlin airfield"]),
 ("waehrungsreform", "Währungsreform 1948: 40 D-Mark für jeden", "1948", "Westdeutschland", 1948,
  ["Währungsreform 1948 (Westdeutschland)", "Deutsche Mark", "Ludwig Erhard"], ["Category:Currency reform in Germany 1948", "Category:Deutsche Mark", "Category:Währungsreform 1948"],
  ["currency reform germany", "german currency", "deutsche mark"]),
 ("schwarzmarkt", "Schwarzmarkt 1946: Zigaretten statt Geld", "1946", "Deutschland", 1946,
  ["Schwarzmarkt", "Nachkriegszeit", "Zigarettenwährung"], ["Category:Black market in Germany", "Category:Black markets", "Category:Germany in 1946"],
  ["black market germany", "germany 1946", "german food"]),
 ("hungerwinter", "Hungerwinter 1946/47: Wie überlebte man ihn?", "1946", "Deutschland", 1946,
  ["Hungerwinter 1946/47", "Nachkriegszeit", "Lebensmittelkarte"], ["Category:Hunger winter 1946-1947", "Category:Germany in 1947", "Category:Food in Germany"],
  ["german food story", "germany hunger", "food germany 1946"]),
 ("care-pakete", "CARE-Pakete: Was steckte drin?", "1946", "Deutschland", 1946,
  ["CARE-Paket", "Nachkriegszeit", "Marshallplan"], ["Category:CARE packages", "Category:CARE (relief organization)", "Category:Food aid"],
  ["care package", "relief germany", "food aid germany"]),
 ("truemmerfrauen", "Trümmerfrauen: Wer räumte Deutschland auf?", "1946", "Deutschland", 1946,
  ["Trümmerfrau", "Trümmerbahn", "Nachkriegszeit"], ["Category:Trümmerfrauen", "Category:Rubble women", "Category:Rubble clearance in Germany"],
  ["rubble germany", "germany rebuilding", "rebuilding germany"]),
 ("vertriebene", "Flüchtlinge und Vertriebene: Zwölf Millionen Neuanfänge", "1946", "Deutschland", 1946,
  ["Flucht und Vertreibung Deutscher aus Mittel- und Osteuropa 1945–1950", "Heimatvertriebene", "Lastenausgleich"], ["Category:Expulsion of Germans after World War II", "Category:Displaced persons camps in Germany", "Category:Refugees in Germany"],
  ["refugees germany", "displaced persons germany", "refugee camp germany"]),
 ("marshallplan", "Marshallplan: Wohin flossen die Dollar?", "1948", "Westdeutschland", 1948,
  ["Marshallplan", "Europäisches Wiederaufbauprogramm", "Wirtschaftswunder"], ["Category:Marshall Plan", "Category:Marshall Plan in Germany"],
  ["marshall plan", "marshall plan germany", "european recovery"]),
 ("kaefer", "Der Käfer: 5.000 Mark und der millionste Wagen", "1955", "Wolfsburg", 1955,
  ["VW Käfer", "Volkswagenwerk Wolfsburg", "Wirtschaftswunder"], ["Category:Volkswagen Beetle", "Category:Volkswagen Beetle (Type 1)", "Category:Volkswagen factory Wolfsburg"],
  ["volkswagen", "wolfsburg"]),
 ("17-juni-1953", "17. Juni 1953: Aufstand in der DDR", "1953", "Ost-Berlin", 1953,
  ["Aufstand vom 17. Juni 1953", "Walter Ulbricht"], ["Category:Uprising of 1953 in East Germany", "Category:17 June 1953"],
  ["east berlin 1953", "berlin uprising", "east germany 1953"]),
 ("flucht-westberlin", "Flucht nach West-Berlin: Wie lief eine Flucht ab?", "1959", "Berlin", 1959,
  ["Ungesetzlicher Grenzübertritt im DDR-Recht", "West-Berlin", "Notaufnahmelager Marienfelde"], ["Category:Marienfelde Refugee Center", "Category:Refugees from East Germany", "Category:Escapes from East Germany"],
  ["refugee berlin", "east german refugees", "west berlin refugee"]),
 ("mauerbau", "13. August 1961: Über Nacht eine Grenze", "1961", "Berlin", 1961,
  ["Berliner Mauer", "Bau der Berliner Mauer", "Ost-Berlin"], ["Category:Construction of the Berlin Wall", "Category:Berlin Wall in 1961", "Category:Berlin Wall"],
  ["berlin wall", "berlin border", "berlin 1961"]),
 ("checkpoint-charlie", "Checkpoint Charlie 1961: Panzer Auge in Auge", "1961", "Berlin", 1961,
  ["Checkpoint Charlie", "Berlin-Krise", "Berliner Mauer"], ["Category:Checkpoint Charlie", "Category:Berlin Crisis of 1961", "Category:Checkpoint Charlie in 1961"],
  ["checkpoint charlie", "berlin tanks", "berlin crisis"]),
 ("kennedy-berlin", "Kennedy in Berlin 1963: Der Satz, der die Stadt erobert hat", "1963", "Berlin", 1963,
  ["Ich bin ein Berliner", "Berliner Mauer", "West-Berlin"], ["Category:John F. Kennedy in Berlin", "Category:John F. Kennedy's visit to West Berlin", "Category:Kennedy visit to Germany 1963"],
  ["kennedy berlin", "kennedy germany", "kennedy visit"]),
 ("gi-familien", "GIs in Deutschland: Besatzer und Besetzte Tür an Tür", "1947", "Deutschland", 1947,
  ["Amerikanische Besatzungszone", "Besatzungszone", "US-Streitkräfte in Deutschland"], ["Category:American occupation of Germany", "Category:United States Army in Germany", "Category:Bremerhaven"],
  ["occupation germany", "us army germany", "american soldiers germany"]),
 ("westberlin-alltag", "West-Berlin: Das Leben auf der Insel", "1953", "West-Berlin", 1953,
  ["West-Berlin", "Berliner Luftbrücke", "Berlin-Blockade"], ["Category:West Berlin", "Category:West Berlin in 1950s", "Category:Berlin in the 1950s"],
  ["west berlin", "this is berlin", "berlin 1953"]),
 ("wirtschaftswunder", "Wirtschaftswunder: Was kostete das gute Leben?", "1955", "Westdeutschland", 1955,
  ["Wirtschaftswunder", "Soziale Marktwirtschaft", "Ludwig Erhard"], ["Category:Wirtschaftswunder", "Category:Germany in the 1950s", "Category:West Germany in the 1950s"],
  ["west germany 1950s", "germany economy", "german industry"]),
]


def cat_exists(c):
    d = material_de._get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "titles": c, "prop": "categoryinfo", "format": "json"}))
    pg = next(iter(d["query"]["pages"].values()))
    return "missing" not in pg and (pg.get("categoryinfo") or {}).get("files", 0) > 0


def main():
    topics, dropped = [], []
    for slug, name, year, place, y, wiki, cats, films in T:
        got = []
        for t in wiki:
            try:
                got.append(sources.wikipedia(t, "de"))
            except Exception:                                        # noqa: BLE001
                pass
        chars = sum(len(g["text"]) for g in got)
        if chars < 9000:
            dropped.append((slug, f"only {chars} characters of articles"))
            continue
        okc = [c for c in cats if cat_exists(c)]
        topics.append({"slug": slug, "name": name, "year_label": year, "place": place, "years": [y - 1, y + 1],
                       "wikipedia": [g["title"] for g in got], "commons_categories": okc, "film_queries": films,
                       "status": "queued"})
        print(f"{slug}: {len(got)} articles, {chars} chars, {len(okc)}/{len(cats)} categories")
    (ROOT / "topics").mkdir(exist_ok=True)
    (ROOT / "topics" / "queue.json").write_text(json.dumps({"topics": topics}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("dropped:", dropped)


if __name__ == "__main__":
    main()
