#!/usr/bin/env python
# coding: utf-8

# =======================================================================================
#              GMAIL AUTHENTICATION (checked before collecting articles)
# =======================================================================================

import os
import sys
import base64
import time
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

BASE_DIR = '/home/gdaniel1979/my_projects/telex'
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_FILE = '/home/gdaniel1979/auth/client_secret_1073369059368-0kshmclsgvomtsdqoij42tdhe50ct4c4.apps.googleusercontent.com.json'
TOKEN_FILE = '/home/gdaniel1979/auth/gmail_api_token.json'
EMAIL_TO = "gdaniel1979@yahoo.com"

# telex.hu topic slug -> title used in the log and in the email (in display order)
TOPICS = {
    "kulfold": "Külföld",
    "belfold": "Belföld",
    "gazdasag": "Gazdaság"
}


def gmail_authenticate():
    """Authenticate with Gmail. If the refresh token is revoked, deletes it and
    falls back to a fresh interactive OAuth flow (only when run from a terminal).
    Returns a service object or None if authentication cannot be completed."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except RefreshError as e:
                # Token is revoked or invalid — delete it and re-authenticate
                print(f"Token refresh failed ({e}). Deleting cached token and re-authenticating.")
                os.remove(TOKEN_FILE)
                creds = None
            except Exception as e:
                # Network or other transient error — keep the token for the next run
                print(f"Token refresh failed ({e}).")
                return None

    if not creds or not creds.valid:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"ERROR: OAuth credentials file not found: {CREDENTIALS_FILE}")
            return None
        if not sys.stdin.isatty():
            print("Gmail needs a new authorization, which cannot be done from cron. "
                  f"Run `python3 {BASE_DIR}/telex.py` once from a terminal.")
            return None
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES, redirect_uri='http://localhost'
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            print("\nOpen this URL in your browser to authorize:")
            print(auth_url)
            print("\nAfter authorizing, your browser will show an error page (connection refused).")
            print("Copy the full URL from your browser's address bar and paste it here:")
            redirected_url = input("\nRedirected URL: ").strip()
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(redirected_url)
            code = parse_qs(parsed.query).get('code', [None])[0]
            if not code:
                raise ValueError("No authorization code found in the URL.")
            flow.fetch_token(code=code)
            creds = flow.credentials
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            print(f"Authentication failed: {e}")
            return None

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        print(f"Failed to build Gmail service: {e}")
        return None


# ---------- Pre-flight: verify email sending before doing any work ----------
script_start = time.time()

print("\nCHECKING EMAIL SERVICE")
gmail_service = gmail_authenticate()
if gmail_service is None:
    print("ERROR: Gmail authentication failed. Cannot send emails. Aborting.")
    sys.exit(1)
print("Gmail authentication OK.")

# ---------- Claude (headless Claude Code CLI, billed to the Claude subscription) ----------
import json
import subprocess

CLAUDE_BIN = '/home/gdaniel1979/.local/bin/claude'
# Optional long-lived token created with `claude setup-token`; if the file is
# missing, the CLI's own login (~/.claude/.credentials.json) is used.
CLAUDE_TOKEN_FILE = '/home/gdaniel1979/auth/claude_oauth_token.txt'
CLAUDE_SYSTEM_PROMPT = "Magyar nyelvű hírösszefoglalókat készítesz. Csak a kért szöveget add vissza."

claude_model = "sonnet"
# Number of Claude requests running at the same time
claude_workers = 2

CLAUDE_ENV = os.environ.copy()
# An API key would take precedence and bill the API instead of the subscription
CLAUDE_ENV.pop("ANTHROPIC_API_KEY", None)
if os.path.exists(CLAUDE_TOKEN_FILE):
    with open(CLAUDE_TOKEN_FILE) as f:
        CLAUDE_ENV["CLAUDE_CODE_OAUTH_TOKEN"] = f.read().strip()

CLAUDE_CMD = [
    CLAUDE_BIN, "-p",
    "--model", claude_model,
    "--output-format", "json",
    "--system-prompt", CLAUDE_SYSTEM_PROMPT,
    "--tools", "",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--setting-sources", "",
]


def ask_claude(prompt, retries=3):
    """Send a single prompt to Claude through `claude -p`.
    Returns (text, usage dict). Raises RuntimeError if all attempts fail."""
    error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            proc = subprocess.run(CLAUDE_CMD, input=prompt, capture_output=True,
                                  encoding="utf-8", env=CLAUDE_ENV, timeout=600)
            try:
                data = json.loads(proc.stdout)
            except ValueError:
                data = None
            if data and not data.get("is_error") and data.get("result"):
                return data["result"].strip(), data.get("usage") or {}
            error = (data or {}).get("result") or proc.stderr.strip() or proc.stdout.strip() or error
        except (OSError, subprocess.TimeoutExpired) as e:
            error = str(e)
        if attempt < retries:
            time.sleep(30 * attempt)

    raise RuntimeError(f"Claude call failed after {retries} attempts: {error}")


print("CHECKING CLAUDE")
try:
    ask_claude("Válaszolj egyetlen szóval: ok", retries=2)
except RuntimeError as e:
    print(f"ERROR: {e}\n"
          "If this is an authentication error, log in again with `claude auth login` "
          f"or save a `claude setup-token` token to {CLAUDE_TOKEN_FILE}. Aborting.")
    sys.exit(1)
print("Claude OK. Proceeding with article collection.\n")


# =======================================================================================
#              SCRAPING ARTICLES
# =======================================================================================

import re
import requests
from bs4 import BeautifulSoup

weeks_back = 1
today = date.today()
cutoff_date = today - timedelta(weeks=weeks_back)

print("CLAUDE SETTINGS")
print(f"Model: {claude_model}")
print()
print("COLLECTING ARTICLES")

http = requests.Session()
DATE_IN_URL = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")


def scrape_topic(rovat_url, cutoff_date):
    """Download articles of a given topic until cutoff_date."""
    base_url = f"https://telex.hu/rovat/{rovat_url}?oldal="
    page = 1
    articles = []
    seen_hrefs = set()

    while True:
        response = http.get(base_url + str(page), timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        regular_items = soup.select("div.list__item.list__item--article")
        highlight_items = soup.select("div.list__highlight__item") if page == 1 else []

        if not regular_items and not highlight_items:
            break

        page_has_valid_articles = False

        for item in regular_items + highlight_items:
            is_highlight = "list__highlight__item" in (item.get("class") or [])

            if is_highlight:
                title_tag = item.select_one(".list__highlight__item__title")
                lead_tag = item.select_one(".list__highlight__item__lead")
                url_tag = item.find("a", href=True)
            else:
                title_tag = item.select_one("a.list__item__title")
                lead_tag = item.select_one("div.list__item__lead")
                url_tag = item.select_one("a.list__item__title")

            if not url_tag or not url_tag.has_attr("href"):
                continue
            href = url_tag["href"]
            regex_date = DATE_IN_URL.search(href)
            if not regex_date:
                continue

            article_date = date(*map(int, regex_date.groups()))
            if article_date < cutoff_date:
                continue

            if not is_highlight:
                page_has_valid_articles = True

            if href in seen_hrefs:
                continue

            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            lead = lead_tag.get_text(" ", strip=True) if lead_tag else ""
            if title and lead:
                seen_hrefs.add(href)
                articles.append({
                    "date": article_date.isoformat(),
                    "title": title,
                    "lead": lead
                })

        if not page_has_valid_articles:
            break

        page += 1

    return articles


scrapelt_cikkek = {}
for rovat_url, title in TOPICS.items():
    scrapelt_cikkek[rovat_url] = scrape_topic(rovat_url, cutoff_date)
    print(f"✅ {len(scrapelt_cikkek[rovat_url])} articles collected in the topic '{title.lower()}'. ({today})")

if not any(scrapelt_cikkek.values()):
    print("\nERROR: No articles collected for any topic. "
          "The telex.hu page structure may have changed again. Aborting.")
    sys.exit(1)


# =======================================================================================
#               CLAUDE
# =======================================================================================

import yaml
from concurrent.futures import ThreadPoolExecutor

batch_size = 25
today_str = today.isoformat()

print("\nSENDING TO CLAUDE")

with open(os.path.join(BASE_DIR, "prompts.yaml"), "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

total_prompt_tokens = 0
total_completion_tokens = 0


def count_usage(usage):
    global total_prompt_tokens, total_completion_tokens
    total_prompt_tokens += (usage.get("input_tokens", 0)
                            + usage.get("cache_creation_input_tokens", 0)
                            + usage.get("cache_read_input_tokens", 0))
    total_completion_tokens += usage.get("output_tokens", 0)


def fill_template(template):
    return (template
            .replace("({{TODAY}})", today_str)
            .replace("({{WEEKSBACK}})", str(weeks_back)))


def build_batch_prompts(articles, rovat_url):
    """Split the articles into batches and return one prompt per batch."""
    template = fill_template(prompts[rovat_url]["batch_prompt"])
    batch_prompts = []
    for i in range(0, len(articles), batch_size):
        batch_text = ""
        for j, article in enumerate(articles[i:i + batch_size], 1):
            batch_text += f"{j}. {article['date']}\n   {article['title']}\n   {article['lead']}\n\n"
        batch_prompts.append(template + "\n\n" + batch_text)
    return batch_prompts


# Batches of all topics run in parallel; each topic's final summary starts
# as soon as its own batches are done.
summaries = {}
final_texts = {}

with ThreadPoolExecutor(max_workers=claude_workers) as pool:
    batch_futures = {}
    for rovat_url, title in TOPICS.items():
        batch_prompts = build_batch_prompts(scrapelt_cikkek[rovat_url], rovat_url)
        print(f"📂 {title.upper()} — {len(batch_prompts)} batches")
        batch_futures[rovat_url] = [pool.submit(ask_claude, p) for p in batch_prompts]

    final_futures = {}
    for rovat_url, futures in batch_futures.items():
        summaries[rovat_url] = []
        for future in futures:
            text, usage = future.result()
            count_usage(usage)
            summaries[rovat_url].append(text)

        if summaries[rovat_url]:
            final_prompt = (fill_template(prompts[rovat_url]["final_prompt"])
                            + "\n\n" + "\n\n".join(summaries[rovat_url]))
            final_futures[rovat_url] = pool.submit(ask_claude, final_prompt)
        else:
            final_texts[rovat_url] = "Ebben a rovatban nem jelent meg új cikk az időszakban."

    for rovat_url, future in final_futures.items():
        text, usage = future.result()
        count_usage(usage)
        final_texts[rovat_url] = text

print()


# =======================================================================================
#               WORDCLOUD
# =======================================================================================

from wordcloud import WordCloud, STOPWORDS
from io import BytesIO


def clean_summaries(summaries):
    """Clean summaries list and convert to a single text."""
    text = " ".join(summaries)
    text = re.sub(r"\*\*", "", text)
    text = text.replace("\n", " ")
    text = re.sub(r"Dátum:\s*\d{4}-\d{2}-\d{2}", "", text)
    text = re.sub(r"Fő gazdasági esemény:", "", text)
    text = re.sub(r"Érintett szektor\(ok\):", "", text)
    text = re.sub(r"Rövid leírás:", "", text)
    text = re.sub(r"Összefoglalás:", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_stopwords_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


stopwords = STOPWORDS.union(load_stopwords_from_file(os.path.join(BASE_DIR, "hungarian_stopwords.txt")))

wordcloud_images = {}

for rovat_url in TOPICS:
    text = clean_summaries(summaries[rovat_url])
    if not text:
        print(f"⚠️  No content for '{rovat_url}', skipping word cloud.")
        continue

    wc = WordCloud(
        width=800,
        height=800,
        background_color="white",
        collocations=False,
        stopwords=stopwords,
        colormap="viridis"
    ).generate(text)

    buf = BytesIO()
    wc.to_image().save(buf, format="PNG")
    wordcloud_images[rovat_url] = buf.getvalue()


# =======================================================================================
#               E-MAIL
# =======================================================================================

import html

NUMBERED_LINE = re.compile(r"^\d+\.\s+")


def inline_markup(line):
    """Escape HTML and turn **bold** into <b>bold</b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line))


def text_to_html_lines(text):
    out = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            out += "<br>"
        elif line.startswith("### "):
            out += f"<h2>{inline_markup(line[4:].strip())}</h2>"
        elif line.startswith("## "):
            out += f"<h3>{inline_markup(line[3:].strip())}</h3>"
        elif line.startswith("# "):
            out += f"<h1>{inline_markup(line[2:].strip())}</h1>"
        elif NUMBERED_LINE.match(line):
            out += f"<li>{inline_markup(NUMBERED_LINE.sub('', line))}</li>"
        elif line.startswith("- "):
            out += f"<li>{inline_markup(line[2:].strip())}</li>"
        else:
            out += f"<p>{inline_markup(line)}</p>"
    return out


def create_combined_email(to, subject, sections):
    """Create a single email with alternating text/wordcloud sections.

    sections: list of (title, body_text, image_bytes or None) tuples in display order.
    """
    msg = MIMEMultipart('related')
    msg['to'] = to
    msg['subject'] = subject

    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)

    plain_parts = []
    html_body = "<html><body>"

    for idx, (title, body_text, image_bytes) in enumerate(sections):
        plain_parts.append(f"=== {title} ===\n\n{body_text}\n\n")
        html_body += f"<h1>{title}</h1>"
        html_body += text_to_html_lines(body_text)
        if image_bytes:
            html_body += f"<br><img src='cid:image_{idx}'><br>"
        html_body += "<hr>"

    html_body += "</body></html>"

    msg_alt.attach(MIMEText("".join(plain_parts), 'plain'))
    msg_alt.attach(MIMEText(html_body, 'html'))

    for idx, (title, body_text, image_bytes) in enumerate(sections):
        if not image_bytes:
            continue
        image = MIMEImage(image_bytes)
        image.add_header('Content-ID', f'<image_{idx}>')
        image.add_header('Content-Disposition', 'inline', filename=f"wordcloud_{idx}.png")
        msg.attach(image)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw}


def send_email(service, message):
    return service.users().messages().send(userId="me", body=message).execute()


subject = f"Heti hírösszefoglaló, {today}"
sections = [
    (title, final_texts[rovat_url], wordcloud_images.get(rovat_url))
    for rovat_url, title in TOPICS.items()
]
send_email(gmail_service, create_combined_email(EMAIL_TO, subject, sections))
print(f"E-mail sent (combined), {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# =======================================================================================
#               LOG SUMMARY
# =======================================================================================

total_tokens = total_prompt_tokens + total_completion_tokens

script_end = time.time()
duration = int(script_end - script_start)
hours, remainder = divmod(duration, 3600)
minutes, seconds = divmod(remainder, 60)
duration_str = f"{hours:02}:{minutes:02}:{seconds:02}"

log_summary = f"""
RUN SUMMARY
Script start: {time.strftime('%H:%M:%S', time.localtime(script_start))}
Script end  : {time.strftime('%H:%M:%S', time.localtime(script_end))}
Duration    : {duration_str}
Total tokens used: {total_tokens} (prompt: {total_prompt_tokens}, completion: {total_completion_tokens})
-----------------------------------------------------------------------
"""

print(log_summary)
