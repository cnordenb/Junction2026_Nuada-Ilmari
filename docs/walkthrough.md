# Demo walkthrough

About 2 minutes. *Italics: what to show on screen.*

## 1. The challenge (0:00–0:15)
*Open on demo.botswarm.tech.*

We took on Hostinger's challenge: build an AI-powered tool that detects bots and bad actors online. We chose "Spot the swarm": catching bot-nets by how they act together, not one account at a time.

## 2. The problem (0:15–0:30)

Propaganda needs a crowd. Astroturfing, brigading and fake reviews all run on thousands of fake accounts, and each one looks real on its own. Most are opened through free tiers, so site owners pay too, with free trials burned by bot-nets.

## 3. Our solution and its two applications (0:30–0:45)

So we built Sargas. It spots bot-nets by looking at groups of signups. That gives us two applications: it starves propaganda of the fake accounts it needs, and it stops bot-nets from exploiting free trials.

## 4. Live demo (0:45–1:20)
*botswarm.tech: sign up on your phone and show your score.*

Here's a free tier to protect: Neighbr, Tinder for horses. I sign up like a normal person and get a bot score of about 1 out of 100.

*attack.botswarm.tech: launch stealth-farm.*

Now a bot-net attacks: realistic names, a new home IP for every account. The first few get in.

*guard.botswarm.tech: point at the swarm card.*

But Sargas links them: fifteen accounts, three devices, one email template, faster than chance. The whole swarm is blocked, including the ones that already got in.

## 5. How it decides (1:20–1:40)
*Point at the formula panel.*

Every signup gets eighteen checks, weighted and combined in a logistic model, so every point of the score has a reason. We set the weights by how strong each piece of evidence is, then tested them on labelled bot attacks mixed with hard innocent cases, like a school class on one network. Result: zero of nearly seventeen thousand real people blocked.

## 6. AI and tech (1:40–1:55)

Two small Liquid AI models run on our own server: a decision model that spots machine-made emails and sorts the review queue, and a language model that explains each bot group in plain words. It all runs on a Hostinger VPS, with our domain, botswarm.tech, also from Hostinger.

## 7. Close (1:55–2:00)

Sargas: find the swarm before it speaks.

## Before recording

- Press **Reset demo** on the console, and **Reset** any of your own IP bans.
- Launch stealth-farm during section 4 so the swarm is ready by the time you reach the dashboard.
- If running long, trim section 6 to its last sentence.
