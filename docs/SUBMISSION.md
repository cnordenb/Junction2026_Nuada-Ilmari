# Junction submission

Ready to paste into the Junction form. Pitch deck: [docs/Sargas.pptx](Sargas.pptx).

## Project Name

Sargas

## Punchline (max 200 characters)

Sargas spots bot-nets by looking at groups of signups, stopping the fake accounts behind propaganda and free-trial abuse.

## Description (markdown, max 5000 characters)

```markdown
## The problem
Propaganda online needs a crowd. Astroturfing, brigading and fake reviews run on thousands of fake accounts, and each one looks like a real person on its own. Most of those accounts are opened through free tiers, so site owners pay as well: free trials used up by bot-nets, and spam and phishing sent under their name. Blocking one request or one IP at a time misses them, because bot-nets rotate home IP addresses.

## What we built
Sargas finds fake accounts by looking at groups, not single signups. It links signups that share rare details, such as one device behind 15 "different people", one inbox spelled ten ways, or one email template, and checks whether they arrived faster than chance. When a group is confirmed, every account in it is blocked, including the ones that already got in.

It has two uses:
- **Against propaganda:** stopping the fake accounts that astroturfing and brigading depend on.
- **For site owners:** stopping bot-nets from exploiting free trials.

Live demo:
- **botswarm.tech:** Neighbr, a satirical "Tinder for horses" with a free tier, protected by Sargas. Sign up and see your own bot score live.
- **guard.botswarm.tech:** the dashboard. Every signup's score and reasons, detected groups, IP bans and test results.
- **attack.botswarm.tech:** launch bot campaigns against the site and watch them get caught.

## How the score works
Each signup is scored with one published formula: `score = 100 / (1 + e^-z)`, where `z = -4 + Σ weight × factor`. There are 18 factors, each measured from 0 to 1. They cover the signup itself (throwaway inbox, reused device, hidden form field filled), behaviour on the page (typing rhythm, mouse movement, network latency) and the group it belongs to (size, shared details, timing). Natural human movement and school or company groups lower the score. Every point is shown with its reason.

We built it by starting from the signals bot-nets can't easily hide. We set each weight by what the signal means, and tuned them on forged signup logs with planted bots and innocent look-alikes: a school class on one IP, a company team, families sharing a laptop, VPN users. We then tested on attackers we hadn't tuned for. Result: 0 of 16,864 real people blocked, and 85.7% of bots blocked. A bot that copies human behaviour closely still gets through, and the dashboard says so.

## AI
Two open models run on our own server: Liquid AI's d1-omni-600M and LFM3-VL-2B. We tested them as judges on labelled data and they did worse than the formula (they flagged 17 and 10 of 60 real people; the formula flagged 0). So the formula makes the decisions, and AI does what it did better in our tests: spotting machine-made email addresses, ranking the review queue, and summarising each detected group in plain words.

## Tech, and why
- **Python and FastAPI:** fast to build, and easy to read.
- **NumPy and SciPy:** for the statistics, such as comparing a group's timing against 4,000 random groups.
- **llama.cpp:** runs the AI models on our own server, so no user data leaves it and there's no API cost.
- **Docker Compose and Caddy:** one-command deploys with automatic HTTPS.
- **Hostinger:** everything runs on a Hostinger VPS, under our domain botswarm.tech, also from Hostinger. 91 automated tests.
```

## Links

- Live: https://botswarm.tech · https://guard.botswarm.tech · https://attack.botswarm.tech (demo key on request)
- Code: https://github.com/cnordenb/Junction2026_Sargas
