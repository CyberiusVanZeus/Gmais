"""Verified-source web search for the Validator Agent.

The Validator can corroborate claims against an allowlist of **government and
verified institutional sources** rather than the open web, in keeping with the
tradecraft requirement that source provenance be trustworthy (Admiralty
reliability axis). It also accepts **analyst-supplied sources** entered from the
web interface, which are treated as evidence and flagged as verified or
unverified by domain.

Design notes:
* No source is fabricated. If no real search API is configured and the analyst
  supplies none, the search simply returns nothing and the Validator proceeds on
  the intrinsic Admiralty grading alone.
* A real search is enabled by setting ``GMAIS_SEARCH_API`` to an HTTP endpoint
  that accepts a ``q`` query parameter and returns JSON ``[{url,title,snippet}]``
  (any SERP-style proxy works); results are filtered to the verified allowlist.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

# Allowlist of trustworthy domain suffixes and specific institutional hosts.
# Generic government/military/treaty-org suffixes plus named verified bodies.
VERIFIED_SUFFIXES = (".gov", ".mil", ".int", ".gov.uk", ".gov.ng", ".europa.eu")
VERIFIED_HOSTS = {
    "un.org", "who.int", "nato.int", "imf.org", "worldbank.org", "icrc.org",
    "au.int", "ecowas.int", "oecd.org", "iaea.org", "interpol.int", "unhcr.org",
    "reliefweb.int", "europol.europa.eu", "state.gov", "cisa.gov", "fbi.gov",
}


def domain_of(url: str) -> str:
    """Return the lowercased network location (host) of a URL."""
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def is_verified(url: str) -> bool:
    """True if the URL's host is on the verified government/institution allowlist."""
    host = domain_of(url)
    if not host:
        return False
    if host in VERIFIED_HOSTS:
        return True
    return any(host.endswith(suffix.lstrip("*")) for suffix in VERIFIED_SUFFIXES)


@dataclass
class SourceHit:
    """A single corroborating source returned by search or supplied by analyst."""

    url: str
    title: str
    snippet: str
    verified: bool
    origin: str  # "search" or "analyst"

    @property
    def domain(self) -> str:
        return domain_of(self.url)


def parse_user_sources(raw: str) -> List[SourceHit]:
    """Parse analyst-entered sources (one per line) into SourceHits.

    Each line may be a bare URL, or ``url | note`` to attach a description.
    Domain verification is applied automatically.
    """

    hits: List[SourceHit] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Split an optional "| note" suffix.
        if "|" in line:
            url, _, note = line.partition("|")
            url, note = url.strip(), note.strip()
        else:
            url, note = line, ""
        hits.append(
            SourceHit(
                url=url,
                title=note or domain_of(url) or url,
                snippet=note,
                verified=is_verified(url),
                origin="analyst",
            )
        )
    return hits


class VerifiedSourceSearch:
    """Corroborates claims against verified web sources and analyst sources."""

    def __init__(self, user_sources: Optional[List[SourceHit]] = None, *, timeout: float = 6.0):
        self.user_sources = user_sources or []
        self.timeout = timeout
        self.api = os.getenv("GMAIS_SEARCH_API")  # optional SERP-style proxy

    def _search_api(self, query: str, max_results: int) -> List[SourceHit]:
        """Query the configured search API and keep only verified-domain hits."""
        if not self.api:
            return []
        url = self.api + ("&" if "?" in self.api else "?") + urllib.parse.urlencode({"q": query})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GMAIS-Validator"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            # Network/parse failure: corroboration simply unavailable this run.
            return []
        results = data.get("results", data) if isinstance(data, (dict, list)) else []
        hits: List[SourceHit] = []
        for item in (results or [])[: max_results * 3]:
            u = item.get("url", "")
            if is_verified(u):  # discard anything outside the allowlist
                hits.append(SourceHit(
                    url=u,
                    title=item.get("title", domain_of(u)),
                    snippet=item.get("snippet", ""),
                    verified=True,
                    origin="search",
                ))
            if len(hits) >= max_results:
                break
        return hits

    def corroborate(self, query: str, *, max_results: int = 3) -> List[SourceHit]:
        """Return verified sources (search + analyst) relevant to a query."""
        # Analyst-supplied sources are always offered to the Validator.
        hits = list(self.user_sources)
        hits.extend(self._search_api(query, max_results))
        return hits

    @property
    def n_verified_user_sources(self) -> int:
        return sum(1 for s in self.user_sources if s.verified)
