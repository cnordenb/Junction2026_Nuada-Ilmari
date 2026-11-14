# Glasshouse: links collected in this session

Checked status: most links were seen only as search-result snippets, not opened in full. Open each one before quoting it in the pitch. Links from earlier in the session (before the last context summary) are only those I still had on record.

## Our own documents
- Traffic scenarios sheet (Scenarios, README, Definitions, Failures run 1): https://claude.ai/artifact/EJWZwJDDgVJ7KxT3NExr2P
- Glasshouse plan doc: https://claude.ai/artifact/9uB8AekjSsFP2K73dNxzvM
- Interview sheet: https://claude.ai/artifact/JwwEWH8fcnbcZiNQJxqnSa

## Existing solutions we reuse
- TRACE-Bot repository: https://github.com/forthgoer1/TRACE-Bot
- Google: verify Googlebot: https://support.google.com/webmasters/answer/80553
- Google crawler IP ranges (JSON): https://developers.google.com/static/crawling/ipranges/common-crawlers.json
- Bing crawler IP ranges (JSON): https://www.bing.com/toolbox/bingbot.json
- Bing verify tool: https://www.bing.com/toolbox/verify-bingbot
- Bot verifier (reverse DNS plus ranges): https://trustmyip.com/bot-verifier
- Googlebot verifier: https://trustmyip.com/googlebot-verifier
- Common Crawl CCBot ranges: https://index.commoncrawl.org/ccbot.json
- Verify AI bots in logs: https://eseospace.com/blog/verify-ai-bots-in-server-logs/
- Forward-confirmed reverse DNS guide: https://dnsdoh.art/guides/when-blocklists-ban-search-crawlers.html
- Blocking fake Googlebot/Bingbot (Apache): https://www.the-art-of-web.com/system/blocking-fake-bots/
- FP-Agent paper (AI agents vs bot detection): https://arxiv.org/html/2605.01247v1
- "Shy Guys" log-only bot detection paper: https://www.alphaxiv.org/abs/2603.28546.md

## How big vendors build bot protection (open sources)
- Cloudflare bot management reference architecture: https://developers.cloudflare.com/reference-architecture/diagrams/bots/bot-management/
- Cloudflare bot management plans and engines: https://developers.cloudflare.com/bots/plans/bm-subscription
- Cloudflare heuristics engine blog: https://blog.cloudflare.com/ja-jp/bots-heuristics
- Cloudflare per-customer bot defenses: https://blog.cloudflare.com/per-customer-bot-defenses
- Cloudflare fake-bot managed rules (false positives): https://developers.cloudflare.com/waf/troubleshooting/fake-bot-managed-rules/
- Cloudflare: Bing Site Scan blocked: https://developers.cloudflare.com/waf/troubleshooting/blocked-bing-site-scans/
- cside two-stage neural detection (vendor): https://cside.com/blog/catching-bots-that-dont-want-to-be-caught
- Thales Imperva Bad Bot Report 2026: https://cpl.thalesgroup.com/ppc/application-security/bad-bot-report
- DataDome on AI agent spoofing: https://datadome.co/agent-trust-management/ai-agent-spoofing/
- Cleaner anti-crawler system design: https://besthub.dev/articles/design-and-implementation-of-the-cleaner-anti-crawler-system-for-real-time-bot-detection-73a2b1865f1b

## The Yandex source-code leak (reporting only; do not use leaked code)
- Search Engine Land: https://searchengineland.com/yandex-search-ranking-factors-leak-392323
- Techzine: https://www.techzine.eu/news/security/101200/massive-leak-of-yandex-code-reveals-1922-search-ranking-factors/
- Daily Security Feed (mentions antirobot archives): https://zabuqasem.github.io/daily-security-feed/posts/yandex-services-source-code-leak/

## Real cases: many people behind one IP
- School IP blocked, NANOG thread, Mar 2026: https://seclists.org/nanog/2026/Mar/144
- Library vendors block a campus NAT: https://archives.simplelists.com/serialst/cache/11717517/2.html
- HAProxy rate limiting on shared networks: https://discourse.haproxy.org/t/shared-ip-networks-haproxy-rate-limiting-stick-table/10067
- WAF blocks real customers (shared gateways): https://hostadvice.com/blog/web-hosting/security/when-your-waf-blocks-real-customers/

## Real cases: WordPress admin
- ModSecurity blocks wp-admin and wp-login: https://stackharbor.com/en/knowledge-base/cpfix-modsecurity-blocking-wp-admin-login/
- Cloudflare WAF blocks admin-ajax.php: https://stackharbor.com/en/knowledge-base/cffix-waf-blocking-admin-ajax/
- WP Cerber locks out shop visitors: https://talk.wpcerber.com/t/spam-form-submission-denied-bot-detected-wp-admin-admin-ajax-php/374

## Real cases: uptime monitors and feed readers
- OnlineOrNot and Cloudflare Bot Fight Mode: https://onlineornot.com/docs/cloudflare-support
- elmah.io uptime blocked: https://docs.elmah.io/uptime-monitoring-troubleshooting
- Pingdom and UptimeRobot refused by a plugin: https://remarpro.com/support/topic/code-403-for-pingdom-and-uptimerobot-bots
- Payment callbacks and webhooks vs Cloudflare: https://proxyops-dev.pages.dev/artiklar/cloudflare-blocking-legitimate-traffic-fix
- Cloudflare blocking RSS users (OpenRSS): https://openrss.org/blog/using-cloudflare-on-your-website-could-be-blocking-rss-users
- NewsBlur 403 errors: https://forum.newsblur.com/t/feed-retrieval-problems-403-errors/10761
- RSS and 403 (Make community): https://community.make.com/t/rss-and-403/99298
- curl blocked on a blog feed: https://forum.pretendo.network/t/im-getting-blocked-when-requesting-the-blog-rss-feed/7979

## Real cases: fake crawlers, Bingbot
- 692 of 799 "Googlebot" requests fake (SEJ): https://searchenginejournal.com/my-ai-assistant-traffic-was-fake-the-googlebot-number-was-worse/580052/
- Same author, Substack original: https://duaneforresterdecodes.substack.com/p/818-of-my-ai-assistant-traffic-was
- Imperva fake Googlebot study (2014): https://www.imperva.com/blog/?p=364
- AI crawler impostors and probing for env files: https://ipregistry.co/blog/ai-crawler-impostors-env-probing-ip-verification
- Real Bingbot subnet fails reverse DNS: https://techcommunity.microsoft.com/t5/microsoft-bing/verified-bingbot-is-not-returning-expected-hostname-as-per/m-p/3964759

## Real cases: attacks and scraping
- Fintech credential stuffing, one attempt per session (DataDome): https://datadome.co/threat-research/credential-stuffing-fintech-login-attack/
- Credential stuffing from 2.2M residential IPs (Castle): https://blog.castle.io/anatomy-of-a-6-day-credential-stuffing-attack-from-2-2m-residential-ips/
- Comment spam from 3,000+ IPs: https://nicj.net/how-to-deal-with-a-wordpress-wp-comments-post-php-spam-attack/
- Comment spam botnet (Imperva): https://www.imperva.com/blog/?p=5242
- AI bot to human visit ratios (TollBit): https://preproduction.tollbit.com/blog/scraper-index-and-audit/
- Contrast case, fake campaign emails in residents' names: https://www.gadgetreview.com/?p=397240

## Still open (no real case found yet)
- A real honest organised campaign by real people
- Fast scrapers, low-and-slow login attacks, vulnerability scanner variants, contact-form bots
