"""Generate data/demo_posts.csv: a synthetic dataset with planted swarms.

Everything here is made up. The point is a dataset where the right answer is
known, so the detector's precision, recall and false-positive rate can be
measured. Columns: id, account, content, time_posted, label, note. The
detector reads content, time_posted and (optionally) account; label and note
are the answer key.

Planted swarms (label starts with "swarm_"):
    swarm_copypaste   40 near-identical posts within 6 minutes, 40 throwaway accounts
    swarm_template    36 posts from one template, in two 20-minute waves, 18 accounts posting twice
    swarm_schedule    30 near-identical posts exactly every 30 minutes, one account
    swarm_clock       24 near-identical posts at the top of random hours, two accounts
    swarm_paraphrase  16 posts with the same message in different words, within 10 minutes, 16 accounts

Innocent look-alikes (label "organic"):
    quote      one famous quote posted 25 times at unrelated times
    news       60 different reactions to one event within 15 minutes
    greeting   the same morning greeting posted around 08:00 every day by three people
    news feed  one account posting 72 different headlines around the clock

Run:  python data/make_demo_data.py
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 11, 1, tzinfo=timezone.utc)
DAYS = 10
N_BACKGROUND = 4000
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 7, 8, 7, 6, 6, 7, 8, 10, 11, 11, 9, 6, 3]

OPENERS = """Honestly,|Not gonna lie,|Quick update:|So apparently|Just realised that|Hot take:|Fun fact,
Unpopular opinion but|Can confirm,|Reminder that|For what it's worth,|Late to this, but|Okay so|Turns out
Small rant:|Good news,|Bad news,|Serious question,|Random thought:|PSA:|Weirdly enough,|As expected,
In case anyone wondered,|Long story short,|Well,|Update from this morning:|Today I learned|Confession:
Minor victory:|No joke,""".replace("\n", "|").split("|")

SUBJECTS = """my neighbour's cat|the bakery on the corner|our football coach|the new bus timetable
my sister's wedding playlist|the office coffee machine|this year's tomato harvest|the library's late fees
my old laptop|the hiking trail by the lake|our landlord|the school bake sale|that documentary about octopuses
the gym's new opening hours|my grandmother's soup recipe|the local chess club|the ferry to the island
my bike's front brake|the city marathon route|the corner shop's ice cream freezer|our book club pick
the sourdough starter I neglected|the dentist's waiting room|my flatmate's drum kit|the weekend farmers market
the band we saw on Friday|the puzzle with two thousand pieces|my allergy medication|the campsite booking system
the pottery class teacher|our street's recycling schedule|the second season of that detective show
my cousin's food truck|the university parking office|the knitting pattern I bought|the sauna at the pool
my phone's battery|the vegetable stall owner|the choir rehearsal|the neighbour's leaf blower
the museum's night opening|my running shoes|the train to the coast|the stray dog near the station
the kids' science fair|the karaoke bar downtown""".replace("\n", "|").split("|")

PREDICATES = """finally got fixed after three weeks of waiting|turned out much better than anyone predicted
has been driving everybody slightly mad lately|is somehow more expensive than last winter
completely surprised me in the best possible way|needs a serious rethink before spring arrives
won an award nobody had heard of before|broke down again right when it mattered
is now closed on Mondays for some reason|made the whole evening worth the trip
smells exactly like my childhood summers|keeps getting recommended to me by strangers
was mentioned on the radio this afternoon|has a waiting list longer than my patience
got a fresh coat of paint and looks brand new|ran out before noon like it always does
is moving to a bigger place across the river|taught me more than a year of lectures did
disappeared for two days and came back unbothered|costs less if you ask nicely at the counter
is getting replaced by something shinier and worse|still works perfectly despite being ancient
was cancelled because of the storm warning|sold out in under ten minutes online
has the friendliest staff I have met in years|leaks whenever it rains from the east
woke up the entire building at six|deserves far more credit than it gets
is the reason I was late twice this week|will be free for students until January
went viral in our group chat for no reason|ended with everyone singing off key
survived the move without a single scratch|has been quietly improving every month
looks nothing like the photos on the website|arrived early for the first time in history
got mixed up with someone else's order|is honestly the highlight of my autumn
requires a form that nobody can find|was better the second time around
is haunted according to the caretaker|now accepts card payments at last
gave me an idea for a weekend project|made my dad laugh until he cried
has changed owners three times since May|is twice as loud as it needs to be
won't be back until the roadworks finish""".replace("\n", "|").split("|")

ENDINGS = """Anyone else noticed?|Ten out of ten, would recommend.|I have no further comments.|What a week.
Thoughts?|Still processing this.|Tell your friends.|Make of that what you will.|I regret nothing.
Will report back tomorrow.|Send help and snacks.|Life is strange.|That's all, carry on.
Photos to follow.|Never again, probably.|Worth every cent.|Am I the only one?|Small joys.
Somebody explain this to me.|Mark your calendars.|Lesson learned.|It's the little things.
Can't make this up.|More coffee needed.|Zero complaints.|Asking for a friend.|Feels like progress.
See you there maybe.|Back to work now.|Dreams do come true.""".replace("\n", "|").split("|")

NAMES = """Aino Mikko Sanna Jukka Leena Pekka Tiina Ville Laura Antti Maria Juha Emma Olli Noora Timo
Helmi Eero Iida Lauri Kaisa Sami Riikka Tomi Venla Aleksi Oona Petri Milla Joonas""".split()
PLACES = """Tampere Oulu Turku Espoo Lahti Kuopio Vaasa Pori Joensuu Rovaniemi Kotka Porvoo
Hanko Rauma Kajaani Savonlinna Imatra Kemi""".split()

NEWS_A = """Whole block just went dark|Lights out across the old town|Power cut on our street again
Anyone else lose electricity|Blackout downtown right now|Trams have stopped near the square
Traffic lights are dead on the main road|Half the harbour district has no power
Candles out, the grid is down|Elevator stuck between floors here|Shops are closing early in the dark
Our whole building lost power mid-dinner""".replace("\n", "|").split("|")
NEWS_B = """and my phone is at nine percent|so the kids think it's an adventure|and the freezer is full, great
while I was halfway through a film|so dinner is now sandwiches|and the neighbours are out with torches
right as the match went to penalties|and the router died with it|so I'm reading by the window
and nobody knows how long it will last|but the stars look incredible|and the cat is unimpressed""".replace("\n", "|").split("|")
NEWS_C = """Stay safe out there.|Is the utility company saying anything?|Check on elderly neighbours.
Third time this year.|Hope it's back before morning.|Any official word yet?|What happened this time?
Good excuse for an early night.|Typical.|Wild evening.""".replace("\n", "|").split("|")

COPYPASTE = "The council vote on the harbour development was rigged from the start. Share this before they delete it and demand a recount now"
TEMPLATE_PRAISE = ["and my energy bill dropped by a third", "and I sleep so much better at night",
                   "and I honestly can't imagine going back", "and everyone at home has noticed the difference",
                   "and it paid for itself already", "and it changed my daily routine completely"]
SCHEDULE = "Breaking: experts confirm the water supply in the northern district is unsafe. Officials are hiding the test results. Read the leaked report"
CLOCK = "Limited offer today only: verified followers and likes delivered instantly, trusted by thousands of creators. Message us to boost your account"
PARAPHRASE = [
    "The planned transit overhaul will wreck the city budget, and every household is going to pay for it through higher taxes.",
    "Higher taxes for every family: that is what the mayor's public transport scheme really means for our town.",
    "Don't be fooled by the shiny brochures. Residents will foot the bill for this bus and tram redesign for decades.",
    "Our wallets are about to get lighter thanks to the transit reform nobody asked for.",
    "They call it modernisation, I call it a tax hike on ordinary people to fund new tram lines.",
    "If the transport proposal passes, expect your local tax bill to climb year after year.",
    "Ordinary citizens are the ones who will pay dearly when this costly commuter project goes ahead.",
    "The city wants to pour millions into rail and buses, and guess who is covering the cost? All of us.",
    "This expensive mobility plan is a burden on taxpayers, plain and simple.",
    "Mark my words, the new network of routes will drain public money and push taxes up for everybody.",
    "A reckless spending spree on trams is coming, and working families will be squeezed to finance it.",
    "Why should we be charged more every year just so the council can redraw the bus map?",
    "The price of the mayor's pet transit idea will land on residents as bigger tax demands.",
    "Budget ruin and steeper taxes: the true result of overhauling how the city moves people around.",
    "People here cannot afford another levy, yet the transport makeover guarantees exactly that.",
    "Say no to the commuter scheme, unless you enjoy handing more of your salary to city hall.",
]


def at(day: float, hour: float = 0, minute: float = 0, second: float = 0) -> datetime:
    return START + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


class DemoData:
    """Builds the rows (time, content, label, note, account). The sections draw
    from two seeded random streams, so calling them in a different order gives
    a different dataset; generate() is the one place that fixes the order."""

    def __init__(self) -> None:
        self.rng = random.Random(2026)
        # Accounts use their own random stream so adding them does not change the posts.
        self.arng = arng = random.Random(1917)
        self.rows: list[tuple[datetime, str, str, str, str]] = []
        # Ordinary accounts: a few very active, most posting now and then.
        self.people = sorted({f"{arng.choice(NAMES).lower()}{arng.choice(['_', '.', ''])}"
                              f"{arng.choice(PLACES).lower()}{arng.randrange(10, 99)}" for _ in range(1100)})[:900]
        self.activity = [arng.paretovariate(1.3) for _ in self.people]
        # People sleep: each ordinary account is silent for 7 hours a night (a few are night owls).
        self.bedtime = {p: arng.choice([22, 23, 0, 1, 2]) if arng.random() < 0.9 else arng.choice([4, 6, 8])
                        for p in self.people}

    def throwaway(self, stems: list[str]) -> str:
        return f"{self.arng.choice(stems)}{self.arng.randrange(1000, 99999)}"

    def someone_awake(self, when: datetime) -> str:
        for _ in range(200):
            person = self.arng.choices(self.people, weights=self.activity)[0]
            if (when.hour - self.bedtime[person]) % 24 >= 7:
                break
        return person

    def add(self, when: datetime, content: str, label: str, note: str, account: str | None = None) -> None:
        self.rows.append((when.replace(microsecond=1), content, label, note, account or self.someone_awake(when)))

    def organic_time(self) -> datetime:
        rng = self.rng
        hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
        return at(rng.randrange(DAYS), hour, rng.randrange(60), rng.randrange(60))

    def chatter(self, n: int) -> None:
        """Ordinary, unrelated posts, then very short replies below the clustering length limit."""
        rng = self.rng
        for _ in range(n):
            detail = rng.choice([
                f"{rng.choice(NAMES)} from {rng.choice(PLACES)} told me",
                f"After {rng.randrange(2, 40)} years in {rng.choice(PLACES)},",
                f"Heard from {rng.choice(NAMES)} that",
                f"Back in {rng.choice(PLACES)},",
                "",
            ])
            text = " ".join(part for part in (
                rng.choice(OPENERS), detail, rng.choice(SUBJECTS), rng.choice(PREDICATES) + ".", rng.choice(ENDINGS)) if part)
            self.add(self.organic_time(), text, "organic", "background")
        for _ in range(150):
            self.add(self.organic_time(), rng.choice(["lol", "this!", "thanks for sharing", "same here", "so true", "wow", "agreed 100%"]),
                     "organic", "short")

    def lookalikes(self) -> None:
        """Innocent posts that resemble a swarm in text or in timing, but not both."""
        rng = self.rng
        for _ in range(25):
            quote = "Be the change you wish to see in the world."
            self.add(self.organic_time(), rng.choice([quote, quote + " - Gandhi", f'"{quote}"', quote + " Words to live by."]),
                     "organic", "quote")
        for _ in range(60):
            self.add(at(7, 18, 40, rng.uniform(0, 900)), f"{rng.choice(NEWS_A)} {rng.choice(NEWS_B)}. {rng.choice(NEWS_C)}",
                     "organic", "news")
        for day in range(DAYS):
            for who in ("marja_morning", "kahvi_kalle", "sunrise_sirpa"):   # three people with a daily ritual
                self.add(at(day, 7, 30, rng.uniform(0, 3600)), "Good morning everyone, have a wonderful day!", "organic", "greeting", who)

    def copypaste_brigade(self) -> None:
        rng = self.rng
        for _ in range(40):
            text = COPYPASTE
            if rng.random() < 0.4:
                text = text.replace("Share this", rng.choice(["Repost this", "Spread this", "Share it"]))
            text += rng.choice([".", "!", "!!!", ". #recount", "! #harbourgate", ""])
            if rng.random() < 0.3:
                text = text.upper() if rng.random() < 0.3 else text.replace("rigged", "RIGGED")
            self.add(at(2, 21, 14, rng.uniform(0, 360)), text, "swarm_copypaste", "copy-paste brigade",
                     self.throwaway(["truthteller", "harbourwatch", "citizen", "wakeup", "realvoter", "freevoice"]))

    def template_astroturfing(self) -> None:
        """One template, two waves; each account posts once per wave."""
        rng, arng = self.rng, self.arng
        reviewers = [f"{arng.choice(NAMES).lower()}_{arng.choice('abcdefghjklmnprstv')}{arng.randrange(60, 99)}" for _ in range(18)]
        for wave_day, hour, minute in ((4, 14, 0), (5, 9, 30)):
            arng.shuffle(reviewers)
            for who in reviewers:
                text = (f"I've been using the Solvera heat pump for {rng.randrange(2, 12)} "
                        f"{rng.choice(['weeks', 'months'])} {rng.choice(TEMPLATE_PRAISE)}. "
                        f"{rng.choice(['Best purchase this year', 'Best decision we made', 'Best upgrade ever'])}, "
                        f"check out their autumn discount before it ends!")
                self.add(at(wave_day, hour, minute, rng.uniform(0, 1200)), text, "swarm_template", "template astroturfing", who)

    def bots(self) -> None:
        """A timer bot (every 30 minutes) and a clock bot (top of the hour, irregular hours)."""
        rng = self.rng
        for k in range(30):
            text = f"{SCHEDULE} here: watersafe-report.example/{rng.randrange(1000, 9999)}"
            self.add(at(1, 0, 7 + 30 * k, rng.uniform(-3, 3)), text, "swarm_schedule", "posts every 30 minutes", "watersafe_alerts")
        hours = rng.sample(range(3 * 24, 9 * 24), 24)
        for k, h in enumerate(hours):
            text = CLOCK + rng.choice([".", "!", " today.", " now!", " - DM open."])
            self.add(at(0, h, 0, rng.uniform(0, 6)), text, "swarm_clock", "posts at the top of the hour",
                     ("boost_agency", "growthdeals24")[k % 2])

    def reworded_swarm(self) -> None:
        """Same message reworded, synchronised. Lexical matching should miss this."""
        for text in PARAPHRASE:
            self.add(at(6, 12, 5, self.rng.uniform(0, 600)), text, "swarm_paraphrase", "reworded copies",
                     self.throwaway(["taxpayer", "localvoice", "concerned_resident", "commuter"]))

    def news_feed(self) -> None:
        """Automated and around the clock, but every post is different and nothing
        about it is coordinated. Automated is not the same as malicious."""
        arng = self.arng
        for _ in range(72):
            text = f"{arng.choice(['News:', 'Update:', 'Just in:', 'Local:'])} {arng.choice(SUBJECTS)} {arng.choice(PREDICATES)}."
            self.add(at(arng.randrange(DAYS), arng.randrange(24), arng.randrange(60), arng.randrange(60)),
                     text, "organic", "news feed", "harbour_daily_news")


def generate(background: int = N_BACKGROUND) -> list[tuple[datetime, str, str, str, str]]:
    """All rows, oldest first."""
    data = DemoData()
    data.chatter(background)
    data.lookalikes()
    data.copypaste_brigade()
    data.template_astroturfing()
    data.bots()
    data.reworded_swarm()
    data.news_feed()
    return sorted(data.rows, key=lambda r: r[0])


def write(rows: list[tuple[datetime, str, str, str, str]], out: Path) -> None:
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "account", "content", "time_posted", "label", "note"])
        for k, (when, content, label, note, account) in enumerate(rows, 1):
            writer.writerow([k, account, content, when.strftime("%Y-%m-%d %H:%M:%S"), label, note])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic demo dataset.")
    parser.add_argument("--background", type=int, default=N_BACKGROUND, help="number of ordinary posts (default 4000)")
    parser.add_argument("--out", default=str(Path(__file__).with_name("demo_posts.csv")))
    args = parser.parse_args(argv)
    rows = generate(args.background)
    write(rows, Path(args.out))
    swarm = sum(r[2] != "organic" for r in rows)
    print(f"Wrote {args.out} with {len(rows)} posts, {swarm} of them in planted swarms.")


if __name__ == "__main__":
    main()