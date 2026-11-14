"""Generate data/signups/demo_signups.csv: simulated free-tier signups with an answer key.

Everything here is made up. The point is a signup stream where the right answer
is known, so the signup detector's precision, recall and false-positive rate
can be measured, including on the hard innocent cases.

Columns: id, created_at, email, username, ip, asn, asn_org, user_agent,
device_id, country, referrer, label, note. The detector ignores label and note.

Abuse (label starts with "abuse_"):
    abuse_tempmail_burst    45 accounts in 9 minutes, throwaway email services,
                            "user12345" names, headless browser, cloud servers
    abuse_alias_farm        24 accounts that are really 2 Gmail inboxes
                            (dots and +tags), spread over residential proxies
    abuse_proxy_farm        60 accounts every ~4 minutes over 4 hours: every IP
                            different (residential proxies) but 4 devices, one
                            exact browser build, one email template
    abuse_daily_drip        21 accounts over 7 days at ~03:10 UTC from one
                            hosting provider, word+word+digits addresses
    abuse_slow_humanlike    25 accounts over 14 days that copy ordinary users
                            in every field. Planted as a known miss.

Innocent look-alikes (label "organic", note says which):
    trap_classroom          28 students on one university IP, same Chromebook
                            build, same student email domain, within 25 minutes
    trap_team_onboarding    12 colleagues at one company, one office IP, 40 minutes
    trap_promo_burst        150 ordinary people within 90 minutes of a newsletter
    trap_family             households sharing one laptop (2-3 accounts each)
    trap_vpn                privacy-VPN users spread over the two weeks

Run:  python data/make_signup_data.py
"""
from __future__ import annotations

import argparse
import csv
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 11, 1, tzinfo=timezone.utc)
DAYS = 14
N_BACKGROUND = 3000
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2, 3, 5, 6, 7, 7, 7, 8, 8, 7, 7, 8, 9, 10, 10, 9, 7, 4, 2]

FIRST = """aino mikko sanna jukka leena pekka tiina ville laura antti maria juha emma olli noora timo
anna lukas sophie jonas lea felix marie paul julia leon sara elias nina david lina tom
oliver amelia harry isla jack ava charlie mia george grace noah chloe james ella liam zoe
lucas camille hugo manon louis chloé jules inès arthur léa mateo lucia hugo sofia martin
olga ivan maja jakub zofia kacper anja luka mila ana diego carmen pablo elena marco giulia
ahmed fatima omar leila yusuf amira ravi priya arjun ananya wei mei hiro yuki min jun""".split()
LAST = """virtanen korhonen nieminen mäkinen hämäläinen laine heikkinen koskinen järvinen lehtonen
müller schmidt schneider fischer weber meyer wagner becker hoffmann schulz smith jones
taylor brown williams wilson evans thomas johnson roberts martin bernard dubois durand
leroy moreau rossi russo ferrari esposito bianchi garcía fernández lópez martínez sánchez
kowalski nowak wiśniewski novak horvat kovač jensen nielsen hansen andersson johansson
karlsson nilsson eriksson larsen khan ali hassan patel sharma singh chen wang li zhang
tanaka suzuki kim park lee nguyen tran silva santos oliveira costa""".split()
WORDS = """sun moon river stone forest pixel coffee tiger maple ocean storm silver lucky blue
green rocket quiet happy wild cloud ember frost north delta echo nova orbit cedar""".split()

FREE_PROVIDERS = [("gmail.com", 45), ("outlook.com", 9), ("hotmail.com", 6), ("yahoo.com", 8),
                  ("icloud.com", 7), ("proton.me", 3), ("gmx.de", 3), ("web.de", 2),
                  ("live.com", 2), ("mail.ru", 1), ("yandex.com", 1)]
CUSTOM_TLDS = ["fi", "de", "com", "co.uk", "fr", "nl", "se", "io", "es", "it", "pl"]
CUSTOM_STEMS = """studio design consulting media works labs digital bakery photo garden build
travel coffee legal clinic dental fitness yoga print craft wood solar""".split()

# (asn, organisation, country) for residential and mobile internet providers.
RESIDENTIAL = [(719, "Elisa Oyj", "FI"), (1759, "Telia Finland", "FI"), (16086, "DNA Oyj", "FI"),
               (3320, "Deutsche Telekom", "DE"), (3209, "Vodafone GmbH", "DE"), (6805, "Telefonica Germany", "DE"),
               (2856, "British Telecom", "GB"), (5089, "Virgin Media", "GB"), (5607, "Sky UK", "GB"),
               (3215, "Orange France", "FR"), (12322, "Free SAS", "FR"), (5410, "Bouygues Telecom", "FR"),
               (1136, "KPN", "NL"), (33915, "Vodafone Libertel", "NL"), (3301, "Telia Sweden", "SE"),
               (3352, "Telefonica Spain", "ES"), (3269, "Telecom Italia", "IT"), (5617, "Orange Polska", "PL"),
               (7922, "Comcast", "US"), (701, "Verizon", "US"), (7018, "AT&T", "US"), (22773, "Cox", "US"),
               (9498, "Bharti Airtel", "IN"), (4766, "Korea Telecom", "KR"), (2516, "KDDI", "JP")]
VPN = [(9009, "M247 Europe", "NL"), (60068, "Datacamp Limited", "GB"), (212238, "Datacamp Limited", "DE")]
UNIVERSITY = (1741, "FUNET (Finnish university network)", "FI")
DIGITALOCEAN = (14061, "DigitalOcean", "US")
HETZNER = (24940, "Hetzner Online", "DE")

UNLISTED_DISPOSABLE = ["inboxvault.xyz", "quickmail-drop.net", "tmpbox.site", "fastinbox.click"]
DISPOSABLE = ["mailinator.com", "yopmail.com", "guerrillamail.com", "sharklasers.com", "10minutemail.com",
              "temp-mail.org", "maildrop.cc", "dispostable.com", "trashmail.com", "getnada.com"]

UAS = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36", 30),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36", 12),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{s} Safari/605.1.15", 10),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS {i} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{s} Mobile/15E148 Safari/604.1", 18),
    ("Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Mobile Safari/537.36", 16),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{f}.0) Gecko/20100101 Firefox/{f}.0", 8),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36 Edg/{v}.0.0.0", 6),
]
CHROME_V = [138, 139, 140, 141, 142]
SAFARI_V = ["18.6", "26.0", "26.1"]
IOS_V = ["18_6", "26_0", "26_1"]
FIREFOX_V = [143, 144, 145]
CHROMEBOOK = ("Mozilla/5.0 (X11; CrOS x86_64 16328.65.0) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36")
HEADLESS = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "HeadlessChrome/139.0.0.0 Safari/537.36")
STALE_BUILD = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.6367.60 Safari/537.36")
REFERRERS = [("", 40), ("google", 30), ("bing", 4), ("youtube", 6), ("reddit", 4), ("friend_invite", 8),
             ("blog", 8)]



def pick(rng: random.Random, weighted):
    items, weights = zip(*weighted)
    return rng.choices(items, weights=weights)[0]


def ascii_name(s: str) -> str:
    s = s.replace("ł", "l")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def ip_in(rng: random.Random, asn: int, subnet: int | None = None) -> str:
    """A made-up address whose first two octets depend on the network, so
    addresses from one provider look related, as in real allocations."""
    a = 20 + asn % 200
    b = (asn // 7) % 250
    c = subnet if subnet is not None else rng.randrange(256)
    return f"{a}.{b}.{c}.{rng.randrange(1, 255)}"


def device(rng: random.Random) -> str:
    return "".join(rng.choices("0123456789abcdef", k=16))


def user_agent(rng: random.Random) -> str:
    template = pick(rng, UAS)
    return template.format(v=rng.choice(CHROME_V), s=rng.choice(SAFARI_V), i=rng.choice(IOS_V),
                           f=rng.choice(FIREFOX_V))


def human_local(rng: random.Random, first: str, last: str) -> str:
    f, l = ascii_name(first), ascii_name(last)
    style = rng.randrange(8)
    if style == 0:
        return f"{f}.{l}"
    if style == 1:
        return f"{f}{l}"
    if style == 2:
        return f"{f}_{l}{rng.randrange(1, 100)}"
    if style == 3:
        return f"{f[0]}{l}"
    if style == 4:
        return f"{f}{rng.randrange(70, 100)}"
    if style == 5:
        return f"{rng.choice(WORDS)}{f}"
    if style == 6:
        return f"{f}.{l}{rng.randrange(1, 10)}"
    return f"{f}{l[0]}{rng.randrange(1, 1000)}"


def human_username(rng: random.Random, first: str, last: str, local: str) -> str:
    f, l = ascii_name(first), ascii_name(last)
    style = rng.randrange(5)
    if style == 0:
        return local.split("@")[0]
    if style == 1:
        return f"{f}{rng.choice(['', '_', '.'])}{l[: rng.randrange(1, len(l) + 1)]}"
    if style == 2:
        return f"{rng.choice(WORDS)}_{rng.choice(WORDS)}"
    if style == 3:
        return f"{f}{rng.randrange(1, 10000)}"
    return f"the{rng.choice(WORDS)}{f}"


def custom_domain(rng: random.Random, last: str) -> str:
    return f"{ascii_name(last)}-{rng.choice(CUSTOM_STEMS)}.{rng.choice(CUSTOM_TLDS)}"


def background_time(rng: random.Random) -> datetime:
    day = rng.randrange(DAYS)
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
    return START + timedelta(days=day, hours=hour, seconds=rng.uniform(0, 3600))


def human(rng: random.Random, when: datetime, network=None, **override) -> dict:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    if rng.random() < 0.18:
        domain = custom_domain(rng, last)
    else:
        domain = pick(rng, FREE_PROVIDERS)
    local = human_local(rng, first, last)
    asn, org, country = network or rng.choice(RESIDENTIAL)
    row = {"created_at": when, "email": f"{local}@{domain}",
           "username": human_username(rng, first, last, local),
           "ip": ip_in(rng, asn), "asn": asn, "asn_org": org, "user_agent": user_agent(rng),
           "device_id": device(rng), "country": country, "referrer": pick(rng, REFERRERS)}
    row.update(override)
    return row


def generate(seed: int = 7, n_background: int = N_BACKGROUND, hard: bool = False) -> list[dict]:
    """hard=True makes the attackers smarter than anything the detector was
    tuned on: unlisted throwaway domains, normal browsers, more devices,
    looser timing. Used to show where the detector breaks."""
    rng = random.Random(seed)
    rows: list[dict] = []

    def add(row: dict, label: str, note: str) -> None:
        rows.append({**row, "label": label, "note": note})

    # Ordinary signups over two weeks.
    for _ in range(n_background):
        add(human(rng, background_time(rng)), "organic", "background")

    # trap_vpn: privacy-VPN users, spread out.
    for _ in range(90):
        add(human(rng, background_time(rng), network=rng.choice(VPN)), "organic", "trap_vpn")

    # trap_family: households where 2-3 people sign up on one laptop.
    for _ in range(40):
        when = background_time(rng)
        dev, last = device(rng), rng.choice(LAST)
        asn, org, country = rng.choice(RESIDENTIAL)
        ip = ip_in(rng, asn)
        for k in range(rng.choice([2, 2, 3])):
            first = rng.choice(FIRST)
            local = human_local(rng, first, last)
            add({"created_at": when + timedelta(minutes=k * rng.uniform(2, 240)),
                 "email": f"{local}@{pick(rng, FREE_PROVIDERS)}",
                 "username": human_username(rng, first, last, local), "ip": ip, "asn": asn,
                 "asn_org": org, "user_agent": user_agent(rng), "device_id": dev, "country": country,
                 "referrer": pick(rng, REFERRERS)}, "organic", "trap_family")

    # trap_classroom: a workshop where every student signs up during class.
    class_start = START + timedelta(days=3, hours=8, minutes=15)
    class_ip_subnet = 117
    for k in range(28):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        local = f"{ascii_name(first)}.{ascii_name(last)}"
        add({"created_at": class_start + timedelta(seconds=rng.uniform(0, 25 * 60)),
             "email": f"{local}@student.uni-example.fi",
             "username": human_username(rng, first, last, local),
             "ip": f"{ip_in(rng, UNIVERSITY[0], class_ip_subnet).rsplit('.', 1)[0]}.40",
             "asn": UNIVERSITY[0], "asn_org": UNIVERSITY[1], "user_agent": CHROMEBOOK,
             "device_id": device(rng), "country": "FI", "referrer": "teacher_link"},
            "organic", "trap_classroom")

    # trap_team_onboarding: a small company moves its team onto the product.
    team_start = START + timedelta(days=8, hours=9, minutes=30)
    for k in range(12):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        local = f"{ascii_name(first)}.{ascii_name(last)}"
        add({"created_at": team_start + timedelta(seconds=rng.uniform(0, 40 * 60)),
             "email": f"{local}@nordline-logistics.fi",
             "username": human_username(rng, first, last, local),
             "ip": "77.86.21.14", "asn": 719, "asn_org": "Elisa Oyj", "user_agent": user_agent(rng),
             "device_id": device(rng), "country": "FI", "referrer": ""},
            "organic", "trap_team_onboarding")

    # trap_promo_burst: a newsletter goes out and real people sign up fast.
    promo_start = START + timedelta(days=10, hours=17)
    for _ in range(150):
        add(human(rng, promo_start + timedelta(seconds=rng.expovariate(1 / 1500)), referrer="newsletter"),
            "organic", "trap_promo_burst")

    # abuse_tempmail_burst: a script creates accounts as fast as it can.
    burst_start = START + timedelta(days=5, hours=2, minutes=40)
    for k in range(45):
        n = rng.randrange(10000, 99999)
        add({"created_at": burst_start + timedelta(seconds=(k * 60 + rng.uniform(0, 50)) if hard
                                                   else (k * 12 + rng.uniform(0, 4))),
             "email": f"user{n}@{rng.choice(UNLISTED_DISPOSABLE if hard else DISPOSABLE)}",
             "username": f"user{n}",
             "ip": ip_in(rng, DIGITALOCEAN[0], rng.choice([12, 13, 14])), "asn": DIGITALOCEAN[0],
             "asn_org": DIGITALOCEAN[1], "user_agent": user_agent(rng) if hard else HEADLESS,
             "device_id": device(rng) if hard else "",
             "country": "US", "referrer": ""}, "abuse_tempmail_burst", "script, throwaway emails")

    # abuse_alias_farm: two real Gmail inboxes multiplied with dots and +tags.
    alias_start = START + timedelta(days=6, hours=13)
    for base in ("johnsmithdeals", "martinaroberts"):
        for k in range(12):
            local = list(base)
            for pos in sorted(rng.sample(range(1, len(base) - 1), rng.randrange(0, 3)), reverse=True):
                local.insert(pos, ".")
            local = "".join(local)
            if rng.random() < 0.6:
                local += f"+{rng.choice(['promo', 'trial', 'free', 'x'])}{rng.randrange(1, 99)}"
            asn, org, country = rng.choice(RESIDENTIAL)
            add({"created_at": alias_start + timedelta(minutes=rng.uniform(0, 150)),
                 "email": f"{local}@gmail.com",
                 "username": f"{rng.choice(WORDS)}{rng.choice(WORDS)}{rng.randrange(10, 99)}",
                 "ip": ip_in(rng, asn), "asn": asn, "asn_org": org, "user_agent": user_agent(rng),
                 "device_id": device(rng), "country": country, "referrer": "google"},
                "abuse_alias_farm", f"one inbox: {base}@gmail.com")

    # abuse_proxy_farm: antidetect setup with residential proxies. Every IP
    # differs, but the operator's 4 machines and one browser build show through.
    farm_start = START + timedelta(days=9, hours=11)
    farm_devices = [device(rng) for _ in range(20 if hard else 4)]
    for k in range(60):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        digits = rng.randrange(1000, 9999)
        local = f"{ascii_name(first)}{ascii_name(last)}{digits}"
        asn, org, country = rng.choice(RESIDENTIAL)
        add({"created_at": farm_start + timedelta(seconds=k * 240 + rng.uniform(-120, 120) if hard
                                                  else k * 240 + rng.uniform(-20, 20)),
             "email": f"{local}@{rng.choice(['outlook.com', 'hotmail.com', 'gmail.com']) if hard else 'outlook.com'}", "username": f"{ascii_name(first)}_{ascii_name(last)}{digits}",
             "ip": ip_in(rng, asn), "asn": asn, "asn_org": org,
             "user_agent": user_agent(rng) if hard else STALE_BUILD,
             "device_id": farm_devices[k % 4], "country": country, "referrer": ""},
            "abuse_proxy_farm", f"residential proxies, {len(farm_devices)} devices")

    # abuse_daily_drip: a few accounts a night from one rented server.
    for day in range(7):
        for k in range(3):
            w1, w2 = rng.sample(WORDS, 2)
            local = f"{w1}{w2}{rng.randrange(100, 999)}"
            add({"created_at": START + timedelta(days=2 + day, hours=rng.uniform(1, 6)) if hard
                 else START + timedelta(days=2 + day, hours=3, minutes=10 + k * 2, seconds=rng.uniform(0, 60)),
                 "email": f"{local}@yahoo.com", "username": f"{w1}.{w2}",
                 "ip": ip_in(rng, HETZNER[0], 88), "asn": HETZNER[0], "asn_org": HETZNER[1],
                 "user_agent": user_agent(rng), "device_id": device(rng), "country": "DE", "referrer": ""},
                "abuse_daily_drip", "nightly batch from one server")

    # abuse_slow_humanlike: copies ordinary users in every recorded field.
    for _ in range(25):
        add(human(rng, background_time(rng)), "abuse_slow_humanlike", "indistinguishable by design")

    # Real providers never give two people one inbox, so make every ordinary
    # address unique after Gmail-style normalisation (dots and +tags ignored).
    seen: set[str] = set()
    for row in rows:
        if row["label"] != "organic":
            continue
        local, _, domain = row["email"].partition("@")
        while (key := local.split("+")[0].replace(".", "") + "@" + domain) in seen:
            local += str(rng.randrange(10))
        seen.add(key)
        row["email"] = f"{local}@{domain}"

    rows.sort(key=lambda r: r["created_at"])
    for i, row in enumerate(rows, 1):
        row["id"] = f"u{i:05d}"
        row["created_at"] = row["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return rows


COLUMNS = ["id", "created_at", "email", "username", "ip", "asn", "asn_org", "user_agent", "device_id",
           "country", "referrer", "label", "note"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the simulated free-tier signup dataset.")
    parser.add_argument("--background", type=int, default=N_BACKGROUND)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hard", action="store_true", help="smarter attackers the detector was not tuned on")
    parser.add_argument("--out", default=str(Path(__file__).parent / "signups" / "demo_signups.csv"))
    args = parser.parse_args()
    rows = generate(args.seed, args.background, args.hard)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    abuse = sum(r["label"] != "organic" for r in rows)
    print(f"Wrote {len(rows)} signups ({abuse} abusive) to {out}")


if __name__ == "__main__":
    main()
