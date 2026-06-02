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

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_FILE = '/home/gdaniel1979/auth/client_secret_1073369059368-0kshmclsgvomtsdqoij42tdhe50ct4c4.apps.googleusercontent.com.json'
TOKEN_FILE = '/home/gdaniel1979/auth/gmail_api_token.json'
TOPICS = ["kulfold", "belfold", "gazdasag"]

TOPIC_TITLES = {
    "kulfold": "KÜLFÖLD",
    "belfold": "BELFÖLD",
    "gazdasag": "GAZDASÁG"
}


def gmail_authenticate():
    """Authenticate with Gmail. On refresh failure, deletes the bad token and
    falls back to a fresh interactive OAuth flow. Returns a service object or
    None if authentication cannot be completed."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except (RefreshError, Exception) as e:
                # Token is revoked or invalid — delete it and re-authenticate
                print(f"Token refresh failed ({e}). Deleting cached token and re-authenticating.")
                os.remove(TOKEN_FILE)
                creds = None

    if not creds or not creds.valid:
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"ERROR: OAuth credentials file not found: {CREDENTIALS_FILE}")
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
print("\nCHECKING EMAIL SERVICE")
gmail_service = gmail_authenticate()
if gmail_service is None:
    print("ERROR: Gmail authentication failed. Cannot send emails. Aborting.")
    sys.exit(1)
print("Gmail authentication OK. Proceeding with article collection.\n")


# =======================================================================================
#              SCRAPING ARTICLES
# =======================================================================================

import requests
import pandas as pd
import re
from bs4 import BeautifulSoup

pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', 200)

script_start = time.time()

weeks_back = 1
today = date.today()
cutoff_date = today - timedelta(weeks=weeks_back)

gpt_model = "gpt-4o-mini"
gpt_temperature = 0.7

print("GPT SETTINGS")
print(f"Model: {gpt_model}")
print(f"Temperature: {gpt_temperature}")
print()
print("COLLECTING ARTICLES")


def scrape_topic(rovat_label, rovat_url, cutoff_date):
    """Download articles of a given topic until cutoff_date."""
    base_url = f"https://telex.hu/rovat/{rovat_url}?oldal="
    page = 1
    articles = []
    seen_hrefs = set()

    while True:
        url = base_url + str(page)
        response = requests.get(url)
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

            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            lead = lead_tag.get_text(" ", strip=True) if lead_tag else ""

            article_date = "unknown"
            href = None
            if url_tag and url_tag.has_attr("href"):
                href = url_tag["href"]
                regex_date = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
                if regex_date:
                    ev, honap, nap = regex_date.groups()
                    article_date = f"{ev}-{honap}-{nap}"

            if article_date == "unknown":
                continue

            article_date_obj = datetime.strptime(article_date, "%Y-%m-%d").date()
            if article_date_obj < cutoff_date:
                if not is_highlight:
                    continue
                else:
                    continue

            if not is_highlight:
                page_has_valid_articles = True

            if href in seen_hrefs:
                continue

            if title and lead:
                seen_hrefs.add(href)
                articles.append({
                    "date": article_date,
                    "title": title,
                    "lead": lead
                })

        if not page_has_valid_articles:
            break

        page += 1

    print(f"✅ {len(articles)} articles collected in the topic '{rovat_label}'. ({date.today()})")
    return pd.DataFrame(articles)


topics = {
    "külföld": "kulfold",
    "belföld": "belfold",
    "gazdaság": "gazdasag"
}
scrapelt_cikkek = {}
for label, url in topics.items():
    scrapelt_cikkek[label] = scrape_topic(label, url, cutoff_date)

if all(df.empty for df in scrapelt_cikkek.values()):
    print("\nERROR: No articles collected for any topic. "
          "The telex.hu page structure may have changed again. Aborting.")
    sys.exit(1)


# =======================================================================================
#               OPENAI
# =======================================================================================

from openai import OpenAI
import yaml

credentials = yaml.load(open('/home/gdaniel1979/auth/openai_auth'), Loader=yaml.FullLoader)
api_key = credentials["openai_api_key"]
client = OpenAI(api_key=api_key)

batch_size = 5
today_str = date.today().strftime("%Y-%m-%d")

print("\nSENDING TO OPENAI")

with open("/home/gdaniel1979/my_projects/telex/prompts.yaml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

total_prompt_tokens = 0
total_completion_tokens = 0


def analyze_dataframe(df, rovat_label, rovat_url):
    global total_prompt_tokens, total_completion_tokens

    articles = df.to_dict(orient="records")

    batches = [
        articles[i:i + batch_size]
        for i in range(0, len(articles), batch_size)
    ]

    batch_prompt_template = (
        prompts[rovat_url]["batch_prompt"]
        .replace("({{TODAY}})", today_str)
        .replace("({{WEEKSBACK}})", str(weeks_back))
    )

    final_prompt_template = (
        prompts[rovat_url]["final_prompt"]
        .replace("({{TODAY}})", today_str)
        .replace("({{WEEKSBACK}})", str(weeks_back))
    )

    summaries = []

    print(f"📂 {rovat_label.upper()} — {len(batches)} batches")

    for i, batch in enumerate(batches, start=1):
        batch_text = ""
        for j, article in enumerate(batch, 1):
            batch_text += f"{j}. {article['date']}\n   {article['title']}\n   {article['lead']}\n\n"

        prompt = batch_prompt_template + "\n\n" + batch_text

        response = client.chat.completions.create(
            model=gpt_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=gpt_temperature
        )

        usage = response.usage
        total_prompt_tokens += usage.prompt_tokens
        total_completion_tokens += usage.completion_tokens

        summaries.append(response.choices[0].message.content.strip())

    final_prompt = final_prompt_template + "\n\n".join(summaries)

    final_response = client.chat.completions.create(
        model=gpt_model,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=gpt_temperature
    )

    usage = final_response.usage
    total_prompt_tokens += usage.prompt_tokens
    total_completion_tokens += usage.completion_tokens

    final_summary = final_response.choices[0].message.content.strip()

    return summaries, final_summary


summaries_kulfold, final_kulfold = analyze_dataframe(scrapelt_cikkek["külföld"], "külföld", "kulfold")
summaries_belfold, final_belfold = analyze_dataframe(scrapelt_cikkek["belföld"], "belföld", "belfold")
summaries_gazdasag, final_gazdasag = analyze_dataframe(scrapelt_cikkek["gazdaság"], "gazdaság", "gazdasag")

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


hungarian_stopwords = load_stopwords_from_file("hungarian_stopwords.txt")
stopwords = STOPWORDS.union(hungarian_stopwords)

cleaned_summaries = {
    "gazdasag": clean_summaries(summaries_gazdasag),
    "kulfold": clean_summaries(summaries_kulfold),
    "belfold": clean_summaries(summaries_belfold)
}

titles_with_accents = {
    "gazdasag": "Gazdaság",
    "kulfold": "Külföld",
    "belfold": "Belföld"
}

wordcloud_images = {}

for topic, text in cleaned_summaries.items():
    if not text.strip():
        print(f"⚠️  No content for '{topic}', skipping word cloud.")
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
    wordcloud_images[topic] = buf.getvalue()


# =======================================================================================
#               E-MAIL
# =======================================================================================

FINAL_TEXTS = {
    "kulfold": final_kulfold,
    "belfold": final_belfold,
    "gazdasag": final_gazdasag
}

"""
If sending from saved files:
FINAL_TEXTS = {
    "kulfold": open("Arcive/final_kulfold.txt", "r", encoding="utf-8").read(),
    "belfold": open("Arcive/final_belfold.txt", "r", encoding="utf-8").read(),
    "gazdasag": open("Arcive/final_gazdasag.txt", "r", encoding="utf-8").read()
}
"""


def text_to_html_lines(text):
    html = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            html += "<br>"
        elif line.startswith("### "):
            html += f"<h2>{line[4:].strip()}</h2>"
        elif line.startswith("## "):
            html += f"<h3>{line[3:].strip()}</h3>"
        elif line.startswith("# "):
            html += f"<h1>{line[2:].strip()}</h1>"
        elif line[0:2].isdigit() and line[2] == '.':
            html += f"<li>{line[3:].strip()}</li>"
        elif line.startswith("- "):
            html += f"<li>{line[2:].strip()}</li>"
        else:
            html += f"<p>{line}</p>"
    return html


def create_combined_email(to, subject, sections):
    """Create a single email with alternating text/wordcloud sections.

    sections: list of (title, body_text, image_bytes) tuples in display order.
    """
    msg = MIMEMultipart('related')
    msg['to'] = to
    msg['subject'] = subject

    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)

    plain_parts = []
    html_body = "<html><body>"

    for idx, (title, body_text, image_bytes) in enumerate(sections):
        cid = f"image_{idx}"
        plain_parts.append(f"=== {title} ===\n\n{body_text}\n\n")
        html_body += f"<h1>{title}</h1>"
        html_body += text_to_html_lines(body_text)
        html_body += f"<br><img src='cid:{cid}'><br><hr>"

    html_body += "</body></html>"

    msg_alt.attach(MIMEText("".join(plain_parts), 'plain'))
    msg_alt.attach(MIMEText(html_body, 'html'))

    for idx, (title, body_text, image_bytes) in enumerate(sections):
        cid = f"image_{idx}"
        image = MIMEImage(image_bytes)
        image.add_header('Content-ID', f'<{cid}>')
        image.add_header('Content-Disposition', 'inline', filename=f"wordcloud_{idx}.png")
        msg.attach(image)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw}


def send_email(service, message):
    sent = service.users().messages().send(userId="me", body=message).execute()
    return sent


def main():
    subject = f"Heti hírösszefoglaló, {date.today()}"
    sections = [
        ("Külföld",  FINAL_TEXTS["kulfold"],  wordcloud_images["kulfold"]),
        ("Belföld",  FINAL_TEXTS["belfold"],  wordcloud_images["belfold"]),
        ("Gazdaság", FINAL_TEXTS["gazdasag"], wordcloud_images["gazdasag"]),
    ]
    message = create_combined_email("gdaniel1979@yahoo.com", subject, sections)
    send_email(gmail_service, message)
    print(f"E-mail sent (combined), {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()


# =======================================================================================
#               LOG SUMMARY
# =======================================================================================

MODEL_PRICES = {
    "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.00000060},
    "gpt-4o": {"prompt": 0.000005, "completion": 0.000015},
    "gpt-4.1": {"prompt": 0.000005, "completion": 0.000015},
    "gpt-3.5-turbo": {"prompt": 0.0000015, "completion": 0.000002}
}

total_tokens = total_prompt_tokens + total_completion_tokens
total_cost_usd = (
    total_prompt_tokens * MODEL_PRICES[gpt_model]["prompt"] +
    total_completion_tokens * MODEL_PRICES[gpt_model]["completion"]
)

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
Estimated cost (USD): ${total_cost_usd:.5f}
-----------------------------------------------------------------------
"""

print(log_summary)
