"""
Fires of Heaven vBulletin/XenForo Parser
- Extracts posts with username, date, body
- Preserves quoted context (who was quoted and what they said)
- Decodes forum-censored profanity to actual words
- Filters low-content posts (memes, short reactions, sig-only)
- Extracts embedded article links and tweet URLs from each post
"""
from __future__ import annotations

import re
import glob
from typing import Any

# ── Profanity decoder ──────────────────────────────────────────────────────────
PROFANITY_MAP = [
    (r'\bf\*{2,3}\b',           'fuck'),
    (r'\bfu\*{2}\b',            'fuck'),
    (r'\bfuc\*\b',              'fuck'),
    (r'\bf\*\*king\b',          'fucking'),
    (r'\bfu\*\*ing\b',          'fucking'),
    (r'\bf\*\*\*ing\b',         'fucking'),
    (r'\bs\*{2,3}\b',           'shit'),
    (r'\bsh\*t\b',              'shit'),
    (r'\ba\*{2}\b',             'ass'),
    (r'\ba\*\*hole\b',          'asshole'),
    (r'\bc\*{2,3}\b',           'cunt'),
    (r'\bb\*{2,3}h\b',          'bitch'),
    (r'\bd\*{2,2}\b',           'damn'),
    (r'\bp\*{3,4}\b',           'piss'),
    (r'\bc\*{2}k\b',            'cock'),
    (r'\bd\*{3}k\b',            'dick'),
    (r'\bb\*{6}\b',             'bastard'),
    (r'\bm\*\*\*erf\*\*\*er\b', 'motherfucker'),
    (r'\bwh\*{3}\b',            'whore'),
    (r'\bcr\*p\b',              'crap'),
]

def decode_profanity(text: str) -> str:
    for pattern, replacement in PROFANITY_MAP:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ── HTML cleaner ───────────────────────────────────────────────────────────────
def clean_html(html: str) -> str:
    """Strip tags, decode entities, collapse whitespace."""
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = (text
        .replace('&amp;',  '&')
        .replace('&lt;',   '<')
        .replace('&gt;',   '>')
        .replace('&quot;', '"')
        .replace('&#039;', "'")
        .replace('&nbsp;', ' ')
    )
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Link / tweet extractors ────────────────────────────────────────────────────

# Domains to skip entirely for article fetching
_SKIP_DOMAINS = {
    # Social / video (tweets handled separately)
    'twitter.com', 'x.com', 'facebook.com', 'instagram.com',
    'reddit.com', 'youtube.com', 'youtu.be', 'tiktok.com',
    'discord.com', 'discord.gg', 'twitch.tv',
    # Image / GIF hosts and CDN subdomains
    'imgur.com',        'i.imgur.com',
    'giphy.com',        'media.giphy.com',
    'media0.giphy.com', 'media1.giphy.com', 'media2.giphy.com',
    'media3.giphy.com', 'media4.giphy.com',
    'gfycat.com',       'thumbs.gfycat.com',
    'tenor.com',        'c.tenor.com',
    'i.ytimg.com',
    'cdn.drawception.com',
    'pbs.twimg.com',
    # Schema / structured-data namespaces
    'schema.org',
    # Forum software footer links
    'xenforo.com',      'www.xenforo.com',
    'dragonbyte-tech.com', 'www.dragonbyte-tech.com',
    # Forum itself
    'firesofheaven.org',
}

# File extensions that are media, never articles
_SKIP_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg',
    '.mp4', '.webm', '.mov', '.avi', '.mp3', '.pdf',
    '.bmp', '.ico', '.tiff',
}

def _get_host(url):
    """Extract hostname from a URL, lowercased, without www. prefix."""
    m = re.search(r'https?://([^/]+)', url)
    return m.group(1).lower().lstrip('www.') if m else ''

def _is_tweet_url(url):
    """Return True if this URL points to a tweet/post on X or Twitter."""
    host = _get_host(url)
    # Must be exactly twitter.com or x.com (not pbs.twimg.com etc.)
    if host not in ('twitter.com', 'x.com'):
        return False
    # Must have a path that looks like a tweet: /username/status/1234567
    return bool(re.search(r'/status/\d+', url))

def _is_fetchable(url):
    """Return True only if this URL is worth fetching as a readable article."""
    if not url or len(url) < 12 or not url.startswith('http'):
        return False
    # Skip media file extensions
    path = url.split('?')[0].lower()
    if any(path.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False
    # Skip footer UTM-tagged links regardless of domain
    if 'utm_medium=footer' in url or 'utm_content=footer' in url:
        return False
    host = _get_host(url)
    if not host:
        return False
    # Check host and all parent domains against skip list
    for skip in _SKIP_DOMAINS:
        if host == skip or host.endswith('.' + skip):
            return False
    return True


def _get_post_body_html(raw_block):
    """
    Extract just the bbWrapper post body HTML from a full post block.
    All link scanning should be scoped to this section to avoid picking
    up page chrome (header, user card, footer credits, etc.)
    Returns the raw HTML of the post body, or the full block as fallback.
    """
    m = re.search(
        r'class="[^"]*bbWrapper[^"]*">(.*?)(?=</div>\s*</div>\s*</div>\s*</article>'
        r'|<div class="message-actionBar)',
        raw_block, re.DOTALL
    )
    return m.group(1) if m else raw_block


def extract_links(raw_block: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Extract article URLs and tweet URLs from a post block BEFORE HTML is stripped.

    Returns:
        links  — list of {url, title, source}  for article fetching
        tweets — list of {url}                 for tweet oEmbed lookup
    """
    links  = []
    tweets = []
    seen   = set()

    def add_link(url, title='', source=''):
        url = url.strip().rstrip('.,;:)"\'')
        if not url or url in seen:
            return
        seen.add(url)
        if _is_tweet_url(url):
            tweets.append({'url': url})
        elif _is_fetchable(url):
            links.append({'url': url, 'title': title.strip(), 'source': source})

    # ── Strip script/style blocks first (removes JSON-LD with schema.org URLs) ──
    raw_clean = re.sub(
        r'<(script|style)[^>]*>.*?</\1>', ' ',
        raw_block, flags=re.DOTALL | re.IGNORECASE
    )

    # ── Scope all scanning to the post body section ──────────────────────────
    # This is the key fix — anchors and inline URLs are now only read from
    # inside the bbWrapper div, not from the page header, user card, or footer.
    body_html = _get_post_body_html(raw_clean)

    # ── 0. XenForo s9e/MediaSites tweet embeds ──────────────────────────────
    # When a user pastes a tweet/X URL, XenForo's s9e plugin replaces it with
    # a rendered embed. The original URL is gone. What remains is a <span> with
    # a single-quoted JSON array attribute, e.g.:
    #   data-s9e-mediaembed-iframe='["data-s9e-mediaembed","twitter","src",
    #     "https:\/\/s9e.github.io\/iframe\/2\/twitter.min.html
    #     #2031039827924410605#theme=dark"]'
    # The tweet ID is a URL fragment in the s9e.github.io src value.
    # Instagram uses the same pattern with instagram.min.html#<shortcode>.
    for m in re.finditer(r"data-s9e-mediaembed-iframe='([^']+)'", raw_clean, re.IGNORECASE):
        raw_val = m.group(1)
        # Unescape the forward slashes that s9e encodes as \/
        unescaped = raw_val.replace('\\/', '/')
        # Find the s9e.github.io src URL inside the array
        src_m = re.search(r"s9e[.]github[.]io/iframe/[0-9]+/([a-z]+)[.]min[.]html#([^#\]]+)",
                          unescaped, re.IGNORECASE)
        if not src_m:
            continue
        platform = src_m.group(1).lower()   # e.g. 'twitter', 'instagram'
        media_id  = src_m.group(2).strip()  # tweet ID or Instagram shortcode
        if platform == 'twitter':
            tweet_url = f'https://x.com/i/status/{media_id}'
            if tweet_url not in seen:
                seen.add(tweet_url)
                tweets.append({'url': tweet_url})
        # Instagram and other platforms: stored as a link for reference
        # but not fetched via oEmbed (no public unauthenticated endpoint)

    # ── 1. Unfurl / article-preview cards (scan full block — these live  ─────
    #        outside bbWrapper in XenForo's structure)
    for m in re.finditer(
        r'<[^>]+class="[^"]*(?:js-unfurl|unfurl)[^"]*"[^>]*>(.*?)</(?:div|article)>',
        raw_clean, re.DOTALL | re.IGNORECASE
    ):
        html    = m.group(0)
        url_m   = re.search(r'data-url=["\']([^"\']+)["\']', html) or \
                  re.search(r'href=["\']([^"\']+)["\']', html)
        url     = url_m.group(1) if url_m else ''
        title_m = re.search(
            r'(?:unfurl-title|contentRow-title)[^"]*"[^>]*>([^<]+)<',
            html, re.IGNORECASE
        ) or re.search(r'<(?:h[1-6]|strong)[^>]*>([^<]{5,120})<', html, re.IGNORECASE)
        plain   = clean_html(html).strip()
        title   = clean_html(title_m.group(1)) if title_m else (plain[:120] if len(plain) < 160 else '')
        if url:
            add_link(url, title, 'unfurl')
        else:
            fb = re.search(r'https?://\S+', plain)
            if fb:
                add_link(fb.group(0).rstrip('.,;:)"\''), title, 'unfurl')

    # ── 2. <a href> anchors — scoped to post body only ───────────────────────
    for m in re.finditer(
        r'<a\s[^>]*href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>',
        body_html, re.DOTALL | re.IGNORECASE
    ):
        href  = m.group(1).strip()
        label = clean_html(m.group(2)).strip()
        if href.startswith('/') or href.startswith('#'):
            continue
        add_link(href, label, 'anchor')

    # ── 3. Bare https:// URLs — scoped to post body only ────────────────────
    for m in re.finditer(r'https?://[^\s<>"\')\]]+', body_html):
        url = m.group(0).rstrip('.,;:)"\'')
        add_link(url, '', 'inline')

    return links, tweets


# ── Quote extractor ────────────────────────────────────────────────────────────
def extract_quotes(raw_block: str) -> list[dict[str, str]]:
    """Return list of dicts: {quoted_user, quoted_text}"""
    quotes = []
    for bq in re.finditer(r'<blockquote[^>]*>(.*?)</blockquote>', raw_block, re.DOTALL):
        bq_html     = bq.group(1)
        user_match  = re.search(r'bbCodeBlock-title.*?>\s*(.*?)\s+said:', bq_html, re.DOTALL)
        quoted_user = clean_html(user_match.group(1)) if user_match else 'unknown'
        text_match  = re.search(
            r'bbCodeBlock-expandContent[^>]*>(.*?)(?:</div>|<div class="bbCodeBlock-expandLink)',
            bq_html, re.DOTALL
        )
        if text_match:
            quoted_text = clean_html(text_match.group(1))
            quoted_text = decode_profanity(quoted_text)
            if len(quoted_text) > 20:
                quotes.append({'quoted_user': quoted_user, 'quoted_text': quoted_text})
    return quotes


# ── Main body extractor ────────────────────────────────────────────────────────
def extract_body(raw_block: str) -> str:
    """Extract post body from bbWrapper, strip quotes from it, clean up."""
    body_match = re.search(
        r'class="[^"]*bbWrapper[^"]*">(.*?)(?=</div>\s*</div>\s*</div>\s*</article>'
        r'|<div class="message-actionBar)',
        raw_block, re.DOTALL
    )
    if not body_match:
        return ''
    raw = body_match.group(1)
    raw = re.sub(r'<blockquote[^>]*>.*?</blockquote>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<div[^>]*class="[^"]*js-unfurl[^"]*"[^>]*>.*?</div>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<div[^>]*class="[^"]*bbMediaWrapper[^"]*"[^>]*>.*?</div>', '', raw, flags=re.DOTALL)
    text = clean_html(raw)
    text = re.sub(r'Toggle signature.*', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'\d+ Reactions?:.*', '', text).strip()
    text = re.sub(r'Click to expand\.\.\.', '', text).strip()
    text = re.sub(r'Last edited:.*', '', text).strip()
    text = decode_profanity(text)
    return text


# ── Full post parser ───────────────────────────────────────────────────────────
def extract_posts(filepath: str) -> list[dict[str, Any]]:
    with open(filepath, encoding='utf-8', errors='ignore') as f:
        content = f.read()

    posts  = []
    blocks = re.split(r'(?=<article[^>]+data-author=")', content)

    for block in blocks[1:]:
        author_m = re.search(r'data-author="([^"]+)"', block)
        id_m     = re.search(r'data-content="(post-\d+)"', block)
        date_m   = re.search(r'<time[^>]+datetime="([^"]+)"', block)

        if not author_m:
            continue

        quotes        = extract_quotes(block)
        body          = extract_body(block)
        links, tweets = extract_links(block)   # both captured before HTML stripped

        if len(body) < 60 and not quotes:
            continue
        if re.match(r'^https?://\S+$', body.strip()):
            continue

        posts.append({
            'username': author_m.group(1),
            'id':       id_m.group(1) if id_m else '',
            'date':     date_m.group(1)[:10] if date_m else '',
            'datetime': date_m.group(1) if date_m else '',   # full ISO for time filtering
            'quotes':   quotes,
            'body':     body,
            'links':    links,    # [{url, title, source}] — article URLs
            'tweets':   tweets,   # [{url}]                — tweet URLs
        })

    return posts


# ── Run on all pages ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys, os
    folder = sys.argv[1] if len(sys.argv) > 1 else '.'
    files  = sorted(glob.glob(os.path.join(folder, '*.htm')))

    all_posts = []
    for f in files:
        page_posts = extract_posts(f)
        print(f"{os.path.basename(f)}: {len(page_posts)} posts")
        all_posts.extend(page_posts)

    print(f"\nTotal: {len(all_posts)} posts\n{'='*60}")

    for p in all_posts[:8]:
        print(f"\n[{p['id']}] {p['username']} @ {p['date']}")
        if p['quotes']:
            for q in p['quotes']:
                print(f"  >> Quoting {q['quoted_user']}: {q['quoted_text'][:150]}")
        if p['links']:
            for lnk in p['links']:
                print(f"  LINK [{lnk['source']}] {lnk['url'][:80]}")
        if p['tweets']:
            for tw in p['tweets']:
                print(f"  TWEET {tw['url'][:80]}")
        print(f"  Body: {p['body'][:300]}")
        print("-" * 40)
