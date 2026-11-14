"""Reference lists for the signup detector.

Small built-in snapshots so the tool works offline and the demo never depends
on a download. For production, replace them with maintained lists:

  * Throwaway email domains: github.com/disposable-email-domains/disposable-email-domains
    (put the file at the path in SIGNUP_DISPOSABLE_FILE, one domain per line)
  * Datacenter and VPN networks: an IP-to-ASN database such as iptoasn.com or
    MaxMind GeoLite2 ASN, plus a hosting-ASN list (e.g. github.com/X4BNet/lists_vpn)

Every entry here was typed in by hand from well-known providers; none is
copied from those projects.
"""
from __future__ import annotations

import os
from pathlib import Path

DISPOSABLE_DOMAINS = {
    "mailinator.com", "yopmail.com", "guerrillamail.com", "guerrillamail.net", "guerrillamailblock.com",
    "sharklasers.com", "grr.la", "10minutemail.com", "temp-mail.org", "tempmail.net", "maildrop.cc",
    "dispostable.com", "trashmail.com", "trashmail.de", "getnada.com", "throwawaymail.com",
    "fakeinbox.com", "mintemail.com", "mohmal.com", "emailondeck.com", "tempail.com", "burnermail.io",
    "mailnesia.com", "mytemp.email", "tempr.email", "discard.email", "moakt.com", "inboxkitten.com",
    "mailcatch.com", "emailfake.com", "tempinbox.com", "spam4.me", "mailpoof.com", "harakirimail.com",
}

# Big free mailbox providers. Sharing one of these says nothing about two people.
FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com",
    "icloud.com", "me.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de", "mail.ru",
    "yandex.com", "yandex.ru", "aol.com", "zoho.com", "fastmail.com", "tutanota.com", "qq.com",
}

# Providers where several spellings reach one inbox.
DOTS_IGNORED = {"gmail.com", "googlemail.com"}
PLUS_TAGS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "icloud.com",
             "proton.me", "protonmail.com", "fastmail.com"}

# Cloud, hosting and VPN networks (ASN -> what it is). Ordinary people rarely
# sign up from these, but VPN users do, so this is only ever weak evidence.
HOSTING_ASNS = {
    16509: "Amazon Web Services", 14618: "Amazon Web Services", 15169: "Google", 396982: "Google Cloud",
    8075: "Microsoft Azure", 14061: "DigitalOcean", 16276: "OVH", 24940: "Hetzner", 63949: "Akamai Linode",
    20473: "Vultr", 51167: "Contabo", 60781: "Leaseweb", 47583: "Hostinger", 13335: "Cloudflare",
    31898: "Oracle Cloud", 45102: "Alibaba Cloud", 132203: "Tencent Cloud", 9009: "M247 (VPN hosting)",
    60068: "Datacamp (VPN hosting)", 212238: "Datacamp (VPN hosting)",
}

# User-agent fragments that only automation tools send.
AUTOMATION_UA = ("headlesschrome", "python-requests", "python-urllib", "aiohttp", "curl/", "wget/",
                 "go-http-client", "okhttp", "phantomjs", "selenium", "puppeteer", "playwright",
                 "scrapy", "node-fetch", "axios/", "java/", "libwww-perl", "httpclient")


def disposable_domains() -> set[str]:
    """Built-in list, plus a maintained file if SIGNUP_DISPOSABLE_FILE points to one."""
    domains = set(DISPOSABLE_DOMAINS)
    extra = os.environ.get("SIGNUP_DISPOSABLE_FILE")
    if extra and Path(extra).is_file():
        for line in Path(extra).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                domains.add(line)
    return domains
