"""The User-Agent every outbound request uses, and why it is worded this way.

We identify ourselves honestly — a name, a version, and a URL a sysadmin can
follow to find out who is asking and how to reach us. That much is basic
manners for anything that fetches other people's pages.

What we do *not* do is describe the job in the string, and that is a
deliberate correction rather than a style choice. Web application firewalls
in front of several UK publishers match on words, not behaviour:

    uk-open-data-index/0.2 (+https://open-data.org.uk/about)                200
    uk-open-data-index/0.2 (source discovery; +https://...)                 403
    uk-open-data-index/0.2 (harvester; +https://...)                        403
    uk-open-data-index/0.2 (platform; +https://...)                         200
    uk-open-data-index/0.2 (bot; +https://...)                              200

Measured against data-api.ssen.co.uk. "discovery" and "harvester" are
refused; "platform" and even "bot" are waved through — so the filter is
keyword matching, not an assessment of what we are.

That cost us real coverage. SSEN was recorded as "site exists, no catalogue
API" when it runs an entirely ordinary CKAN, purely because the prober
introduced itself as doing discovery. Every negative result any of these
scripts has ever produced was suspect for the same reason.

One constant, imported everywhere, so a well-meant descriptive rewrite can't
quietly reintroduce it.
"""

from __future__ import annotations

USER_AGENT = "uk-open-data-index/0.2 (+https://open-data.org.uk/about)"

HEADERS = {"User-Agent": USER_AGENT}
