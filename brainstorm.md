# Brainstorm

Ideas under consideration for the Hostinger challenge. Nothing here is agreed until it moves to `suggestion.md`.

## Idea: example-based detector ("dumb detector")

**Added 2026-11-14.** Status: under consideration; competes with "Name the technique" in `suggestion.md`.

### The idea

The user manually enters five posts or comments. The system finds the signs they have in common, then uses those signs to detect similar posts in a larger dataset. The extracted signs act as the classifiers for the detections.

Fits the challenge direction "Spot the swarm" (coordinated behaviour, text reuse).

### Analysis

**Main problem:** five examples alone will make it detect the topic, not the manipulation. If all five posts are about immigration, it will flag every immigration post. The design has to work around this.

**What is good**

- The demo is easy to grasp: paste five posts, watch it find 200 more like them.
- The "common signs" double as the explanation, which the judges ask for.
- It is easy to measure honestly: hide known bad posts in a dataset and count how many it finds and how many innocents it flags.

**What needs fixing**

- **No negative examples.** A classifier cannot tell what is distinctive about five posts without something to contrast them with. It needs a background sample of ordinary posts as "not this".
- **Five is very few.** The first result will be rough. A confirm/reject step on the top results fixes this and is also the false-positive story.
- **It needs a dataset to scan.** Uploading arbitrary data is extra work; a pre-loaded dataset is enough for the demo.

### Possible implementation

1. **Extract signs.** Send the five posts plus about 20 random background posts to a model through the Hostinger AI Router. Ask for a short list of explicit signs the five share and the background lacks (repeated slogan, same link domain, template sentence structure, same call to action). Show them to the user as editable checkboxes; these are the "classifiers".
2. **Rank the dataset cheaply.** Compute an embedding for every post once, up front, with a small model such as MiniLM, which should run on the VPS CPU. Score each post by similarity to the five examples, plus near-duplicate text matching to catch copy-paste.
3. **Verify the top candidates.** Send only the top few hundred to the model with the sign list. It must say which signs match and quote the passage; anything without a real quote is dropped.
4. **Feedback loop.** The user marks results as right or wrong. Train a logistic regression on the embeddings, with confirmed posts as positives and rejected plus background posts as negatives, then re-rank.
5. **Accuracy page.** Show precision in the top 100 and the false-positive rate on the ordinary posts, before and after one feedback round.

**Dataset candidate:** the FiveThirtyEight Russian troll tweets (about 3 million, public on GitHub) mixed with ordinary tweets. Pick five from one troll campaign and measure how many of the rest it recovers. Licence and current availability not checked.

### Compared with "Name the technique"

| | Example-based detector | Name the technique |
|---|---|---|
| Challenge direction | Spot the swarm | Name the technique |
| Needs a dataset | Yes, loaded and embedded up front | No, works on pasted text |
| Evaluation | Clean: recover hidden known-bad posts | Needs a hand-labelled test set |
| Distinctiveness | Higher | Lower, a common approach |
| Main risk | Dataset not ready in time; topic matching instead of manipulation | Small test set gives rough numbers |

### Open decision

With about 24 hours left (as of Saturday 2026-11-14 morning), the team should not build both. This idea is more distinctive and has a cleaner evaluation, but it depends on getting a dataset loaded and embedded by early Saturday afternoon. If that slips, fall back to "Name the technique".

The non-technical member's five tasks carry over with small changes: the result screen becomes a ranked list with sign badges and confirm/reject buttons.

## Idea: visitor origin and VPN detection, with origin-based restrictions

**Added 2026-11-14.** Status: under consideration. Fits the challenge direction "Clean the traffic". Could be a standalone tool for site owners, or one signal inside another idea (see the end of this section).

### The idea

For each visitor to a website, estimate the country of origin and whether they come through a VPN, proxy, Tor or a data centre. Let the site owner set rules based on that, such as blocking, challenging or only flagging certain origins.

### Ways to detect country of origin

- **GeoIP database lookup.** Map the visitor's IP address to a country with an offline database. Free options: MaxMind GeoLite2 (free account and attribution required), DB-IP Lite, IP2Location LITE. These are generally reliable at country level and much weaker at city level.
- **Accept-Language header.** The browser's language preference. A weak hint only: many people use English browsers everywhere.
- **Browser timezone.** Read with JavaScript (`Intl.DateTimeFormat().resolvedOptions().timeZone`) and compared with the IP country. A mismatch suggests a VPN or a traveller.

### Ways to detect VPN, proxy, Tor and data-centre traffic

- **ASN lookup.** Find which network owns the IP. Traffic from hosting providers (AWS, DigitalOcean, Hetzner, OVH, M247 and similar) is rarely a normal home visitor. This is the cheapest and strongest single signal, and the free GeoLite2 ASN database covers it.
- **Public lists.** The Tor Project publishes its exit nodes (`https://check.torproject.org/torbulkexitlist`). Community lists of VPN and data-centre ranges exist on GitHub, for example X4BNet `lists_vpn`. IP2Proxy LITE is a free proxy database. Freshness and licences not checked.
- **Paid lookup APIs.** IPQualityScore, ipinfo (privacy detection), proxycheck.io and similar. Better coverage, but cost money and send visitor IPs to a third party.
- **Signal mismatches.** IP country against browser timezone and language; the operating system in the User-Agent against the TCP/IP fingerprint (the p0f tool); a lower MTU, which VPN tunnels often cause (also visible in p0f). Each one is a hint, not proof.
- **Behaviour.** Many sessions from one ASN in a short time, or no JavaScript execution at all, points more to bots than the VPN itself.

Avoid WebRTC IP-leak tricks. They reveal the user's real IP behind their VPN and are invasive.

### Ways to restrict visitors by origin

From blunt to gentle:

1. **Block at the firewall.** `ipset` with country IP ranges plus `iptables` or `nftables` on the VPS. Fast and cheap, but no explanation for the visitor and no logging of who was blocked in the app.
2. **Block at the web server.** nginx with the `geoip2` module, returning 403 or a short explanation page for chosen countries or ASNs.
3. **App middleware.** A FastAPI middleware that looks up each request and applies the site owner's rules. Easiest to make configurable and to log for the dashboard.
4. **Softer responses.** Show a CAPTCHA or challenge instead of blocking, apply a lower rate limit, allow read-only access but not logins or posting, or only flag the visit in the dashboard.

### Analysis

**What is good**

- Easy to build quickly with free offline databases. No model or AI Router credits needed.
- Very visual for a dashboard: a map, a breakdown by country and network type, blocked and challenged counts. This suits the non-technical member's UI/UX and diagram strengths.
- Useful to site owners, which matches Hostinger's own interest.

**What needs care**

- **Origin is not intent.** VPN users include privacy-minded people, journalists, corporate staff and people in censored countries. Blocking them is a false positive by the challenge's own standard. The honest framing is that origin raises or lowers risk; it is not a verdict.
- **Easy to evade.** Bad actors use residential proxies that look like home connections, so ASN checks miss them. Say so openly on the accuracy page.
- **Shared IPs.** Mobile networks and large companies put many people behind one IP (carrier-grade NAT), so one bad actor can get many innocent people blocked.
- **Privacy.** IP addresses are personal data under GDPR. Hash or truncate stored IPs and keep them only as long as needed.
- **Not new on its own.** Cloudflare and others already offer country blocking. Judges may see it as unoriginal unless it is combined with real bot detection and measured false-positive rates.

### How it could fit with other ideas

- **Inside "Clean the traffic"**: origin and network type become features next to request rate, User-Agent and path patterns when classifying bots in server logs.
- **Inside the example-based detector**: many flagged accounts posting from the same data-centre ASN is extra evidence of coordination, but only as a supporting signal, never on its own.

**Measuring it:** run it on a labelled log sample (known bots, known real visitors with and without VPN) and report how many real visitors would have been blocked or challenged under each rule.
