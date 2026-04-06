"""
foh_scraper.py — Fires of Heaven authenticated scraper

Usage (CLI):
    python foh_scraper.py --login                        # test login only
    python foh_scraper.py --thread 7113 --pages 5        # fetch last 5 pages of politics thread
    python foh_scraper.py --thread 7113 --pages 5 \
        --keyword "ukraine" --out ukraine_posts.json     # keyword filter + save

    # Date-range scan (new):
    python foh_scraper.py --after 2026-02-01 --out feb.json
    python foh_scraper.py --after 2026-01-01 --before 2026-01-31 --out january.json
    python foh_scraper.py --after 2025-01-01 --keyword iran --out iran_year.json

    # Combine with enrichment:
    python foh_scraper.py --after 2026-02-01 --query "iran AND oil" --verbose --tweets --out iran_feb.json

Credentials are stored in foh_credentials.json (created on first run).
Session cookie is cached in foh_session.json so you only log in once per session.
"""
from __future__ import annotations

import requests
import json
import re
import os
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from foh_parser import extract_posts
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL    = "https://www.firesofheaven.org"
LOGIN_PAGE  = f"{BASE_URL}/login/"
LOGIN_POST  = f"{BASE_URL}/login/login"
_SCRIPT_DIR  = Path(__file__).resolve().parent
CRED_FILE    = _SCRIPT_DIR / "data" / "foh_credentials.json"
SESSION_FILE = _SCRIPT_DIR / "data" / "foh_session.json"
_OUTPUT_DIR  = _SCRIPT_DIR.parent / "output" / "foh-data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL,
}


# ── Credential management ──────────────────────────────────────────────────────
def load_or_prompt_credentials() -> dict[str, str]:
    if CRED_FILE.exists():
        with open(CRED_FILE) as f:
            creds = json.load(f)
        print(f"[auth] Using saved credentials for: {creds['username']}")
        return creds
    print("First-time setup — enter your Fires of Heaven credentials.")
    print("These will be saved locally to foh_credentials.json.")
    username = input("  Username: ").strip()
    password = input("  Password: ").strip()
    creds = {"username": username, "password": password}
    with open(CRED_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    print(f"[auth] Credentials saved to {CRED_FILE}")
    return creds


# ── Session management ─────────────────────────────────────────────────────────
def load_session() -> requests.Session | None:
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            data = json.load(f)
        session = requests.Session()
        session.headers.update(HEADERS)
        session.cookies.update(data["cookies"])
        return session
    return None


def save_session(session: requests.Session) -> None:
    data = {"cookies": dict(session.cookies)}
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print("[auth] Session cleared.")


# ── Login ──────────────────────────────────────────────────────────────────────
def get_csrf_token(session: requests.Session) -> str:
    resp = session.get(LOGIN_PAGE, timeout=15)
    resp.raise_for_status()
    match = re.search(r'_xfToken["\'][^>]*value=["\']([^"\']+)', resp.text)
    if not match:
        match = re.search(r'"csrf"\s*:\s*"([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not find _xfToken on login page.")
    return match.group(1)


def login(creds: dict[str, str]) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    print("[auth] Fetching login page for CSRF token...")
    token = get_csrf_token(session)
    print(f"[auth] Got token: {token[:20]}...")
    payload = {
        "login":    creds["username"],
        "password": creds["password"],
        "_xfToken": token,
        "remember": "1",
    }
    print("[auth] Posting credentials...")
    resp = session.post(LOGIN_POST, data=payload, timeout=15, allow_redirects=True)
    resp.raise_for_status()
    if "xf_user" in session.cookies:
        print("[auth] Login successful.")
        save_session(session)
        return session
    err = re.search(r'class="[^"]*blockMessage[^"]*"[^>]*>([^<]+)', resp.text)
    msg = err.group(1).strip() if err else "Unknown error"
    raise RuntimeError(f"Login failed: {msg}")


def get_authenticated_session(force_login: bool = False) -> requests.Session:
    if not force_login:
        session = load_session()
        if session:
            print("[auth] Testing cached session...")
            resp = session.get(BASE_URL, timeout=10)
            if "xf_user" in session.cookies or resp.url == BASE_URL:
                print("[auth] Cached session is valid.")
                return session
            print("[auth] Cached session expired, re-authenticating...")
            clear_session()
    creds = load_or_prompt_credentials()
    return login(creds)


# ── Date helpers ───────────────────────────────────────────────────────────────
def parse_date_arg(s: str) -> datetime:
    """
    Parse a date string. Accepts YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS.
    Returns timezone-aware UTC datetime.
    """
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date '{s}'. Use YYYY-MM-DD.")


def post_datetime(post: dict[str, Any]) -> datetime | None:
    """
    Return a UTC-aware datetime for a post, or None if unparseable.
    Tries the 'datetime' field first (ISO format), falls back to 'date'.
    Handles timezone offsets in both +HHMM and -HHMM forms.
    """
    raw = post.get("datetime") or post.get("date")
    if not raw:
        return None
    raw = raw.strip().rstrip("Z")
    # Strip any timezone offset: +05:00, -0500, +0000, etc.
    raw = re.sub(r'[+-]\d{2}:?\d{2}$', '', raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ── Page fetcher ───────────────────────────────────────────────────────────────
def fetch_thread_page(session: requests.Session, thread_url: str, page_num: int, silent: bool = False) -> list[dict[str, Any]]:
    url = f"{thread_url}page-{page_num}"
    if not silent:
        print(f"[fetch] {url}")
    resp = session.get(url, timeout=20)
    if resp.status_code == 403:
        raise RuntimeError(f"403 Forbidden on page {page_num} — session may have expired.")
    if resp.status_code == 404:
        raise RuntimeError(f"404 on page {page_num} — thread may not exist.")
    resp.raise_for_status()
    tmp = Path("_tmp_page.html")
    tmp.write_text(resp.text, encoding="utf-8")
    posts = extract_posts(str(tmp))
    tmp.unlink()
    return posts


def get_latest_page_number(session: requests.Session, thread_url: str) -> int:
    resp = session.get(thread_url, timeout=15)
    resp.raise_for_status()
    pages = re.findall(r'page-(\d+)', resp.text)
    return max(int(p) for p in pages) if pages else 1


def fetch_pages(session: requests.Session, thread_url: str, num_pages: int = 3, start_page: int | None = None) -> list[dict[str, Any]]:
    """Original page-based fetch. Fully backward compatible."""
    if start_page is None:
        print("[fetch] Detecting latest page number...")
        last = get_latest_page_number(session, thread_url)
        start_page = max(1, last - num_pages + 1)
        print(f"[fetch] Latest page: {last}. Fetching pages {start_page}–{last}.")
    all_posts = []
    for page_num in range(start_page, start_page + num_pages):
        try:
            posts = fetch_thread_page(session, thread_url, page_num)
            print(f"[fetch] Page {page_num}: {len(posts)} posts")
            all_posts.extend(posts)
            time.sleep(1.5)
        except RuntimeError as e:
            print(f"[fetch] Stopping: {e}")
            break
    return all_posts


# ── Binary search: find the page for a target date ─────────────────────────────
def get_page_first_date(session: requests.Session, thread_url: str, page_num: int) -> datetime | None:
    """
    Fetch a page silently and return the datetime of the first post on it.
    Returns None if the page can't be fetched or has no parseable dates.
    """
    try:
        posts = fetch_thread_page(session, thread_url, page_num, silent=True)
    except Exception:
        return None
    for p in posts:
        dt = post_datetime(p)
        if dt:
            return dt
    return None


def find_start_page(session: requests.Session, thread_url: str, target_dt: datetime, last_page: int) -> int:
    """
    Binary search for the earliest page whose content reaches target_dt.
    Returns the page number to begin fetching from.

    Binary search makes O(log N) fetches — about 10 probes for a 1000-page thread.
    The 0.5s polite delay between probes adds roughly 5 seconds total.
    """
    lo, hi = 1, last_page
    best   = last_page   # default: start at the end if date not found

    print(f"[date-search] Binary searching {last_page} pages for {target_dt.date()}...")

    iterations = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        iterations += 1
        first_dt = get_page_first_date(session, thread_url, mid)
        time.sleep(0.5)

        if first_dt is None:
            hi = mid - 1
            continue

        print(f"[date-search]   page {mid:5d}: first post {first_dt.date()}")

        if first_dt <= target_dt:
            # This page starts before our target — target might be here or later
            best = mid
            lo   = mid + 1
        else:
            # This page starts after our target — go earlier
            hi = mid - 1

    # Back up one page to catch any posts that straddle the boundary
    result = max(1, best - 1)
    print(f"[date-search] Starting at page {result} ({iterations} probes).")
    return result


# ── Date-range fetch ───────────────────────────────────────────────────────────
def fetch_date_range(session: requests.Session, thread_url: str, after_dt: datetime | None = None, before_dt: datetime | None = None) -> list[dict[str, Any]]:
    """
    Fetch all posts in [after_dt, before_dt].
    Uses binary search to locate the start page, then reads forward until
    all posts are past before_dt (or the thread ends).
    """
    print("[fetch] Detecting latest page number...")
    last_page = get_latest_page_number(session, thread_url)
    print(f"[fetch] Thread has {last_page} pages.")

    # Find the starting page
    if after_dt is not None:
        start_page = find_start_page(session, thread_url, after_dt, last_page)
    else:
        start_page = 1

    total_estimate = last_page - start_page + 1
    est_minutes    = total_estimate * 1.5 / 60
    print(f"\n[fetch] Starting at page {start_page}. "
          f"Up to {total_estimate} pages to scan.")
    if total_estimate > 20:
        print(f"[fetch] Estimated time: ~{est_minutes:.0f} min at 1.5s/page.")
        print(f"[fetch] Tip: add --keyword or --query to filter while scanning.")

    all_posts  = []
    done_early = False

    for page_num in range(start_page, last_page + 1):
        try:
            posts = fetch_thread_page(session, thread_url, page_num)
        except RuntimeError as e:
            print(f"[fetch] Stopping at page {page_num}: {e}")
            break

        in_window = []
        for p in posts:
            dt = post_datetime(p)
            if after_dt  and dt and dt < after_dt:
                continue   # before our window
            if before_dt and dt and dt > before_dt:
                done_early = True
                continue   # past our window
            in_window.append(p)

        all_posts.extend(in_window)
        pages_left = last_page - page_num
        print(f"[fetch] Page {page_num}: {len(in_window)}/{len(posts)} in window "
              f"| total: {len(all_posts)} | {pages_left} pages left")

        # If the first post on this page is already past before_dt, stop
        if done_early and posts:
            first_dt = post_datetime(posts[0])
            if first_dt and before_dt and first_dt > before_dt:
                print("[fetch] Passed --before boundary, stopping early.")
                break

        time.sleep(1.5)

    after_str  = after_dt.date().isoformat()  if after_dt  else "beginning"
    before_str = before_dt.date().isoformat() if before_dt else "now"
    print(f"\n[fetch] Done: {len(all_posts)} posts from {after_str} to {before_str}.")
    return all_posts


# ── Keyword filter ─────────────────────────────────────────────────────────────
def keyword_filter(posts: list[dict[str, Any]], keywords: list[str] | None) -> list[dict[str, Any]]:
    if not keywords:
        return posts
    pattern = re.compile('|'.join(re.escape(k) for k in keywords), re.IGNORECASE)
    matched = []
    for post in posts:
        searchable = post.get('body', '')
        for q in post.get('quotes', []):
            searchable += ' ' + q.get('quoted_text', '')
        if pattern.search(searchable):
            matched.append(post)
    return matched


# ── Boolean query filter ───────────────────────────────────────────────────────
def boolean_query_filter(posts: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    """Supports AND, OR, NOT, parentheses, "quoted phrases"."""
    if not query:
        return posts

    def tokenize(q):
        tokens, i = [], 0
        while i < len(q):
            if q[i] == '"':
                j = q.find('"', i + 1)
                if j == -1: j = len(q)
                tokens.append(('PHRASE', q[i+1:j])); i = j + 1
            elif q[i] == '(':
                tokens.append(('LPAREN',  '(')); i += 1
            elif q[i] == ')':
                tokens.append(('RPAREN',  ')')); i += 1
            elif q[i:i+3].upper() == 'AND' and (i+3 >= len(q) or not q[i+3].isalnum()):
                tokens.append(('AND', 'AND')); i += 3
            elif q[i:i+2].upper() == 'OR' and (i+2 >= len(q) or not q[i+2].isalnum()):
                tokens.append(('OR',  'OR'));  i += 2
            elif q[i:i+3].upper() == 'NOT' and (i+3 >= len(q) or not q[i+3].isalnum()):
                tokens.append(('NOT', 'NOT')); i += 3
            elif q[i].isspace():
                i += 1
            else:
                j = i
                while j < len(q) and q[j] not in ' "()': j += 1
                if j > i: tokens.append(('WORD', q[i:j]))
                i = j
        return tokens

    def parse_or(t, p):
        l, p = parse_and(t, p)
        while p < len(t) and t[p][0] == 'OR':
            p += 1; r, p = parse_and(t, p); l = ('OR', l, r)
        return l, p

    def parse_and(t, p):
        l, p = parse_not(t, p)
        while p < len(t) and t[p][0] == 'AND':
            p += 1; r, p = parse_not(t, p); l = ('AND', l, r)
        return l, p

    def parse_not(t, p):
        if p < len(t) and t[p][0] == 'NOT':
            p += 1; op, p = parse_primary(t, p); return ('NOT', op), p
        return parse_primary(t, p)

    def parse_primary(t, p):
        if p >= len(t): return ('WORD', ''), p
        tt, tv = t[p]
        if tt == 'LPAREN':
            e, p = parse_or(t, p + 1)
            if p < len(t) and t[p][0] == 'RPAREN': p += 1
            return e, p
        elif tt in ('WORD', 'PHRASE'):
            return (tt, tv), p + 1
        return ('WORD', ''), p + 1

    def evaluate(tree, text):
        n = tree[0]
        if n in ('WORD', 'PHRASE'):
            return bool(re.search(re.escape(tree[1]), text, re.IGNORECASE))
        if n == 'AND':  return evaluate(tree[1], text) and evaluate(tree[2], text)
        if n == 'OR':   return evaluate(tree[1], text) or  evaluate(tree[2], text)
        if n == 'NOT':  return not evaluate(tree[1], text)
        return False

    try:
        tokens = tokenize(query)
        tree, _ = parse_or(tokens, 0)
    except Exception as e:
        print(f"[filter] Query parse error: {e}. Using literal search.")
        return keyword_filter(posts, [query])

    matched = []
    for post in posts:
        searchable = post.get('body', '')
        for q in post.get('quotes', []):
            searchable += ' ' + q.get('quoted_text', '')
        if evaluate(tree, searchable):
            matched.append(post)
    return matched


# ── Enrichment ─────────────────────────────────────────────────────────────────
def fetch_article_content(url: str, session: requests.Session, timeout: int = 15) -> dict[str, Any] | None:
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200: return None
        html = resp.text
        html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL|re.IGNORECASE)
        title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL|re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title_m.group(1)).strip() if title_m else ''
        text  = re.sub(r'<[^>]+>', ' ', html)
        text  = re.sub(r'&[a-z]+;', ' ', text)
        text  = re.sub(r'\s+', ' ', text).strip()
        words = text.split()
        return {'url': url, 'title': title, 'body': ' '.join(words[:600]), 'word_count': len(words)}
    except Exception:
        return None


def fetch_tweet_content(tweet_url: str, timeout: int = 10) -> dict[str, str | None]:
    try:
        api  = f"https://publish.twitter.com/oembed?url={tweet_url}&omit_script=true"
        resp = requests.get(api, timeout=timeout, headers=HEADERS)
        if resp.status_code != 200:
            return {'url': tweet_url, 'author': '', 'text': '', 'error': f'HTTP {resp.status_code}'}
        data   = resp.json()
        html   = data.get('html', '')
        author = data.get('author_name', '')
        text   = re.sub(r'<[^>]+>', ' ', html)
        text   = re.sub(r'\s+', ' ', text).strip()
        text   = re.sub(r'—\s*\S+\s*\(@[^)]+\)[^$]*$', '', text).strip()
        return {'url': tweet_url, 'author': author, 'text': text, 'error': None}
    except Exception as e:
        return {'url': tweet_url, 'author': '', 'text': '', 'error': str(e)}


def enrich_posts(posts: list[dict[str, Any]], session: requests.Session, fetch_articles: bool = False, fetch_tweets: bool = False) -> list[dict[str, Any]]:
    if not fetch_articles and not fetch_tweets:
        return posts
    article_cache, tweet_cache = {}, {}
    for post in posts:
        if fetch_articles:
            post['link_content'] = []
            for link in post.get('links', []):
                url = link.get('url', '')
                if not url: continue
                if url not in article_cache:
                    print(f"[article] {url[:80]}")
                    article_cache[url] = fetch_article_content(url, session)
                    time.sleep(1.5)
                if article_cache[url]:
                    post['link_content'].append(article_cache[url])
        if fetch_tweets:
            post['tweet_content'] = []
            for tw in post.get('tweets', []):
                url = tw.get('url', '')
                if not url: continue
                if url not in tweet_cache:
                    print(f"[tweet]   {url}")
                    tweet_cache[url] = fetch_tweet_content(url)
                    time.sleep(1.0)
                post['tweet_content'].append(tweet_cache[url])
    if fetch_articles: print(f"[enrich] Articles: {sum(1 for v in article_cache.values() if v)} unique")
    if fetch_tweets:   print(f"[enrich] Tweets:   {len(tweet_cache)} unique")
    return posts


# ── Output ─────────────────────────────────────────────────────────────────────
def print_summary(posts: list[dict[str, Any]], max_body: int = 200) -> None:
    print(f"\n{'='*60}\n  {len(posts)} posts\n{'='*60}")
    for p in posts:
        print(f"\n[{p['id']}] {p['username']} @ {p['date']}")
        for q in p.get('quotes', []):
            print(f"  >> {q['quoted_user']}: {q['quoted_text'][:100]}")
        body = p.get('body', '')
        print(f"  {body[:max_body]}{'...' if len(body) > max_body else ''}")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fires of Heaven scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard page-based (unchanged)
  python foh_scraper.py --pages 20 --keyword iran --out iran.json

  # Everything since February 1st
  python foh_scraper.py --after 2026-02-01 --out feb.json

  # January only
  python foh_scraper.py --after 2026-01-01 --before 2026-01-31 --out jan.json

  # Past year, Iran posts only, with full enrichment
  python foh_scraper.py --after 2025-03-01 --keyword iran --verbose --tweets --out iran_year.json

  # Full year with boolean filter
  python foh_scraper.py --after 2025-01-01 --query "(iran OR israel) AND oil" --out geo_year.json
        """
    )

    ap.add_argument("--login",      action="store_true")
    ap.add_argument("--relogin",    action="store_true")
    ap.add_argument("--thread",     default="7113")
    ap.add_argument("--thread-url", default=None)

    # Page mode (original)
    ap.add_argument("--pages",  type=int, default=3)
    ap.add_argument("--start",  type=int, default=None)

    # Date mode (new)
    ap.add_argument("--after",  default=None,
                    help="Fetch posts on or after YYYY-MM-DD")
    ap.add_argument("--before", default=None,
                    help="Fetch posts on or before YYYY-MM-DD (inclusive)")

    # Filters
    ap.add_argument("--keyword", nargs="+")
    ap.add_argument("--query",   default=None)

    # Enrichment
    ap.add_argument("--verbose", action="store_true", help="Fetch article content")
    ap.add_argument("--tweets",  action="store_true", help="Fetch tweet content")

    # Output
    ap.add_argument("--out", default=None)

    args = ap.parse_args()

    # Default bare filenames to the foh-data output folder
    if args.out and not os.path.isabs(args.out):
        if os.sep not in args.out and '/' not in args.out:
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            args.out = str(_OUTPUT_DIR / args.out)

    # Thread URL
    if args.thread_url:
        thread_url = args.thread_url.rstrip('/') + '/'
    else:
        thread_url = f"{BASE_URL}/threads/politics-thread.{args.thread}/"

    # Auth
    session = get_authenticated_session(force_login=args.relogin)
    if args.login:
        print("[auth] Login test complete.")
        return

    # Parse date args
    after_dt = before_dt = None
    if args.after:
        try:
            after_dt = parse_date_arg(args.after)
            print(f"[date] --after  : {after_dt.date()}")
        except ValueError as e:
            print(f"[error] {e}"); sys.exit(1)

    if args.before:
        try:
            raw       = parse_date_arg(args.before)
            before_dt = raw.replace(hour=23, minute=59, second=59)
            print(f"[date] --before : {before_dt.date()} (end of day, inclusive)")
        except ValueError as e:
            print(f"[error] {e}"); sys.exit(1)

    if after_dt and before_dt and after_dt > before_dt:
        print("[error] --after must be earlier than --before."); sys.exit(1)

    # Fetch
    if after_dt or before_dt:
        posts = fetch_date_range(session, thread_url,
                                 after_dt=after_dt, before_dt=before_dt)
    else:
        posts = fetch_pages(session, thread_url,
                            num_pages=args.pages, start_page=args.start)

    print(f"\n[parse] Total posts fetched: {len(posts)}")

    # Filter
    if args.query:
        posts = boolean_query_filter(posts, args.query)
        print(f"[filter] {len(posts)} match query: {args.query}")
    elif args.keyword:
        posts = keyword_filter(posts, args.keyword)
        print(f"[filter] {len(posts)} match keywords: {args.keyword}")

    # Enrich
    if args.verbose or args.tweets:
        posts = enrich_posts(posts, session,
                             fetch_articles=args.verbose,
                             fetch_tweets=args.tweets)

    # Output
    print_summary(posts)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        print(f"\n[out] Saved {len(posts)} posts to {args.out}")


if __name__ == "__main__":
    main()
