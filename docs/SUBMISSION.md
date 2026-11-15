# Junction submission

Ready to paste into the Junction form. Pitch deck: [docs/Sargas.pptx](Sargas.pptx).

## Project Name

Sargas

## Punchline (max 200 characters)

Propaganda needs a crowd. Sargas finds the bot-nets faking one through free-tier signups, and explains every verdict live.

## Description (markdown, max 5000 characters)

```markdown
## The problem
Propaganda online runs on fake accounts. Astroturfing, brigading and fake engagement all need many accounts that each look like a real person, and those accounts come from free tiers. The site owners who run those free tiers pay for it: burned compute and support time, and spam and phishing sent under their name. Each fake account looks real on its own, and farms rotate home IP addresses, so per-request blocking misses them.

## What we built
**Sargas** (Lithuanian for *guard*) judges **groups of accounts**, not single requests. It links signups that share rare details (one device behind 15 "different people", one inbox spelled ten ways, one email template, robotic mouse movement) and tests whether their timing beats chance against 4,000 random groups. When a swarm forms, every account in it is blocked, **including the ones that already got in**.

Live on our Hostinger VPS:
- **botswarm.tech**: Neighbr, a satirical "Tinder for horses" with a free tier, protected by Sargas. Sign up and watch your own bot score update live.
- **guard.botswarm.tech**: the dashboard: every person's score with each factor, swarms with plain-language summaries, a review queue, IP bans with on/off switches, and our accuracy on labelled data.
- **attack.botswarm.tech**: launch real bot campaigns against the site and watch them get caught.

## Explainable by design
One published equation scores every signup: `score = 100 / (1 + e^-z)`, `z = -4 + Σ weight × factor`, with 18 factors each measured from 0 to 1: inbox tricks, device reuse, hidden form field, typing rhythm, mouse movement, network latency, an on-server AI model, and the linked group's size, shared details and timing. Every point shows its reason in plain language. Natural human movement and school/company groups *lower* the score.

## Honest measurement (40% of the brief, so we took it seriously)
- Tested on 10 forged signup logs with an answer key, including attackers we never tuned for and innocent look-alikes: a class on one campus IP, a company team, families sharing a laptop, VPN users, a newsletter rush.
- **0 of 16,864 real people blocked. 85.7% of bots blocked.** AUC 0.93.
- False positives are designed against: weak signals can't block alone, there is a review band, and IP bans need two blocked accounts and can be switched off or reset.
- **Our known miss is on the dashboard:** a careful bot that replays human input gets in.

## AI where it measurably helps
We ran two open models on the VPS with llama.cpp (Liquid AI's d1-omni-600M and LFM3-VL-2B) and benchmarked them on labelled data, including a Hugging Face dataset of real Twitter bots. **As judges, both lost to our algorithm** (they flagged 10 and 17 of 60 real people; the algorithm flagged 0). So the algorithm decides, and AI does what it measured better at: reading machine-made email patterns (AUC 0.80), ranking the review queue (AUC 0.90 → 0.94), and summarising each swarm in plain words. Hand-picked examples made the LLM look perfect; the benchmark didn't. That's why we measure.

## Tech
Python, FastAPI, SQLite, NumPy/SciPy · llama.cpp server with Liquid AI d1-omni-600M and LFM3-VL-2B · Docker Compose and Caddy (HTTPS) on a Hostinger KVM 2 VPS · 91 passing automated tests plus prompt benchmarks.
```

## Links

- Live: https://botswarm.tech · https://guard.botswarm.tech · https://attack.botswarm.tech (demo key on request)
- Code: https://github.com/cnordenb/Junction2026_Nuada-Ilmari
