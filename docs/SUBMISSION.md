# Junction submission (draft)

**Project:** Sargas: catching swarms of fake signups on free tiers
**Challenge:** Hostinger, Decode the Noise ("Spot the swarm", with parts of "Clean the traffic")
**Live:** https://botswarm.tech (victim site) · https://guard.botswarm.tech (dashboard) · https://attack.botswarm.tech (attack console, demo key on request)
**Code:** https://github.com/cnordenb/Junction2026_Nuada-Ilmari

## One-liner

Cloudflare stops bad requests. Sargas stops bad accounts: it links fake signups into swarms, explains every verdict with one published equation, and shows its own error rates.

## What it does

Free tiers get farmed by bots opening hundreds of accounts. Sargas scores every signup live with 18 factors (inbox tricks, devices, form behaviour, mouse and typing rhythm, latency, an on-server AI model, and the linked group's timing against chance), blocks swarms, catches farms that slip in as the group grows, and bans IPs behind repeated bot accounts. People see their own live score on their phone; site owners see every factor, a review queue and AI summaries of each swarm.

## Detection quality and honesty

- 10 forged signup logs with an answer key, including attackers we did not tune for and innocent look-alikes (a class on one IP, a company team, families on one laptop, VPN users, a newsletter rush): **0 of 16,864 real people blocked, 85.7% of bots blocked**.
- We benchmarked two AI models as judges on labelled data; both lost to the transparent algorithm (they flagged 10 and 17 real people out of 60), so AI is used only where it measured better: reading email patterns (AUC 0.80), ranking the review queue, and writing plain-language summaries.
- Known miss, shown on the dashboard: a careful bot that varies every detail and replays human input.

## Built with

Python, FastAPI, SQLite, NumPy/SciPy; llama.cpp server with Liquid AI d1-omni-600M and LFM3-VL-2B; Docker Compose and Caddy on a Hostinger KVM 2 VPS; Hugging Face dataset airt-ml/twitter-human-bots for prompt benchmarks.
