#!/usr/bin/env python
# coding: utf-8

# In[1]:


# =======================================================================================
#              SCRAPING ARTICLES
# =======================================================================================

import requests
import pandas as pd
from datetime import date, datetime, timedelta

# ------ Web scraping ------
from bs4 import BeautifulSoup
import re

pd.set_option('display.max_colwidth', None)
pd.set_option('display.max_rows', 200)

weeks_back = 1  # Collects articles from the past week
today = date.today()
cutoff_date = today - timedelta(weeks=weeks_back) # Calculating cut-off date

gpt_model = "gpt-4o-mini"
gpt_temperature = 0.7

# ---------------------------
print("\n=== GPT SETTINGS ===")
print(f"Model: {gpt_model}")
print(f"Temperature: {gpt_temperature}")
print("====================\n")
print("COLLECTING ARTICLES")

# ------ Function for scraping articles ------
def scrape_topic(rovat_label, rovat_url, cutoff_date):
    """Downloading articles of a given topic until cutoff_date"""
    
    # URL of articles
    base_url = f"https://telex.hu/rovat/{rovat_url}?oldal="
    
    # Starting page
    page = 1
    
    # Collected articles will be stored in this list
    articles = []

    while True:
        # Compiling URL corresponding to the given page number
        url = base_url + str(page)
        # print(f"🔄 {rovat_label.capitalize()} - downloading page {page}: {url}")

        # Retrieving HTML content from the given page
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Searching for all article blocks on this page
        # Articles are always in <div class="list__item article"> elements (at the time of project creaton, August 2025)
        article_blocks = soup.select("div.list__item.article")

        # Interrupting loop if there are no more articles on this page
        if not article_blocks:
            # print(f"❌ No more articles in the topic '{rovat_label}'.")
            break

        # Checking whether there is an article on this page with a date that is newer or equal to cutoff_date.
        page_has_valid_articles = False

        # Looping through all the articles on this page
        for item in article_blocks:
            # Getting title from this element: <a class="list__item__title"><div>... 
            title_tag = item.select_one("a.list__item__title div")
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Getting lead from this element: <div class="list__item__lead"><div>...
            lead_tag = item.select_one("div.list__item__lead div")
            lead = lead_tag.get_text(strip=True) if lead_tag else ""

            # Getting date from URL
            url_tag = item.select_one("a.list__item__title")
            article_date = "unknown"
            # Checking if we have found the link and if it has an 'href' attribute, because 'href' contains the URL of the article.
            if url_tag and url_tag.has_attr("href"):
                href = url_tag["href"]
                # Using Regex, we search for the year-month-day part in the URL, which has the format: /YYYY/MM/DD/
                #  (\d{4}) - exactly 4 digits (year)
                #  (\d{2}) - exactly 2 digits (month)
                #  (\d{2}) - exactly 2 digits (day)
                regex_date = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
                
                # If we find such a date format, we extract the year, month, and day values from the result as a group.
                if regex_date:
                    ev, honap, nap = regex_date.groups()
                    # Making a date string: 'YYYY-MM-DD'
                    article_date = f"{ev}-{honap}-{nap}"

            # Only if the date is known and adequate
            if article_date != "unknown":
                article_date_obj = datetime.strptime(article_date, "%Y-%m-%d").date()
                # Only if the date is not older than cutoff_date
                if article_date_obj < cutoff_date:
                    # This article is older, we will skip it.
                    continue
                else:
                    page_has_valid_articles = True
                    if title and lead:
                        # We only store it if both fields (title + lead) are available.
                        articles.append({
                            "date": article_date,
                            "title": title,
                            "lead": lead
                        })

        if not page_has_valid_articles:
            # print(f"❌ No more articles in the previous {weeks_back} week in the topic '{rovat_label}'.")
            break

        # Incrementing page number
        page += 1

    # At the end of the loop:
    print(f"✅ {len(articles)} articles collected in the topic '{rovat_label}'. ({date.today()})\n\n")
    return pd.DataFrame(articles)
# -------------------------------------------------------------------

# Loading all three topics into separate dataframe (?)
topics = {
    "külföld": "kulfold",
    "belföld": "belfold",
    "gazdaság": "gazdasag"
}
scrapelt_cikkek = {}
for label, url in topics.items():
    scrapelt_cikkek[label] = scrape_topic(label, url, cutoff_date)

# Printing articles: number, title, lead
#for rovat, df in scrapelt_cikkek.items():
#    print(f"\n=== {rovat.upper()} ===")
#    for i, article in df.iterrows():
#        print(f"{i+1}. ({article['date']}) {article['title']}")
#        print(f"    {article['lead']}\n")


# =======================================================================================
#               OPENAI
# =======================================================================================

from openai import OpenAI
import yaml
import sys

# --- OpenAI API authentication ---
credentials = yaml.load(open('/home/gdaniel1979/auth/openai_auth'), Loader=yaml.FullLoader)
api_key = credentials["openai_api_key"]
client = OpenAI(api_key=api_key)

# --- Settings ---
batch_size = 5
today_str = date.today().strftime("%Y-%m-%d") # Preparing date, which will be used in prompts.yaml

print("SENDING TO OPENAI")

# --- Loading prompts from external file ---
with open("/home/gdaniel1979/hobby_projects/Telex/prompts.yaml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

# --- Function for processing a given topic ---
def analyze_dataframe(df, rovat_label, rovat_url):
    
    articles = df.to_dict(orient="records") # "articles" defined in the section "SCRAPING ARTICLES"

    # API calls are made in batches due to OpenAI's token limit.
    # Each batch (batch_size) is sent to OpenAI in a separate prompt, and since the "memory" of each call is not shared, 
    # the model can only respond based on the given batch_size — it is unaware of the existence of other batches.
    # Solution: Step-by-step summary + final summary (averaging the average?)
    # 1. Step-by-step summary: I request a brief summary for each batch (e.g., main topics, countries, narrative), and I only save this (not the long answer).
    # 2. Final summary call: Once I have all the batch summaries, I send them to the model in a single prompt to generate a comprehensive, complete analysis.
    # Creating batches
    batches = [
        articles[i:i + batch_size]
        for i in range(0, len(articles), batch_size)
    ]

    # prompts.yaml: Replacing placeholder in batch_prompt and final_prompt. This is necessary because the model cannot see the dates in the batches.
    # Setting prompt templates
    batch_prompt_template = (
        prompts[rovat_url]["batch_prompt"] # rovat_url defined in the section "SCRAPING ARTICLES"
        .replace("({{TODAY}})", today_str)
        .replace("({{WEEKSBACK}})", str(weeks_back))
    )

    final_prompt_template = (
        prompts[rovat_url]["final_prompt"] # rovat_url defined in the section "SCRAPING ARTICLES"
        .replace("({{TODAY}})", today_str)
        .replace("({{WEEKSBACK}})", str(weeks_back))
    )

    # Articles from batches will be saved into this list
    summaries = []

    print(f"\n📂 {rovat_label.upper()} — There are {len(batches)} batches")

    for i, batch in enumerate(batches, start=1):
        # Deleting and rewriting a row
        # sys.stdout.write(f"\r📨 Sending batch {i} to OpenAI... ")
        # sys.stdout.flush()
        
        batch_text = ""
        for j, article in enumerate(batch, 1):
            batch_text += f"{j}. {article['title']}\n   {article['lead']}\n\n"

        # Entering prompt, which is written in an external file
        prompt = batch_prompt_template + "\n\n" + batch_text

        response = client.chat.completions.create(
            model=gpt_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=gpt_temperature
        )

        summaries.append(response.choices[0].message.content.strip())

    # At the end, a new line is necessary so that the next entry does not go on the same line.
    print()

    # Calling final summary, whose prompt is written in an external file.
    final_prompt = final_prompt_template + "\n\n".join(summaries)

    # print(f"📨 Requesting summary in the topic '{rovat_label}'...")
    final_response = client.chat.completions.create(
        model=gpt_model,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=gpt_temperature
    )

    final_summary = final_response.choices[0].message.content.strip()

    return summaries, final_summary

# --- Processing all three topics ---
summaries_kulfold, final_kulfold = analyze_dataframe(scrapelt_cikkek["külföld"], "külföld", "kulfold")
summaries_belfold, final_belfold = analyze_dataframe(scrapelt_cikkek["belföld"], "belföld", "belfold")
summaries_gazdasag, final_gazdasag = analyze_dataframe(scrapelt_cikkek["gazdaság"], "gazdaság", "gazdasag")

# print("\n📊 KÜLFÖLD summary:\n", final_kulfold)
# print("\n📊 BELFÖLD summary:\n", final_belfold)
# print("\n📊 GAZDASÁG summary:\n", final_gazdasag)

# =======================================================================================
#               WORLDCLOUD
# =======================================================================================

import re # regular expressions for text cleaning
from wordcloud import WordCloud, STOPWORDS
import matplotlib.pyplot as plt

# Cleaning up summaries (which comes from the section OpenAI) 
def clean_summaries(summaries):
    """Clears the summaries list and converts it into a single text."""
    text = " ".join(summaries)                             # In the case of a saved file (final_kulfold.txt), this line is to be deleted because spaces are inserted between the letters.
    text = re.sub(r"\*\*", "", text)                       # remove bold
    text = text.replace("\n", " ")                         # space instead of line break
    text = re.sub(r"Dátum:\s*\d{4}-\d{2}-\d{2}", "", text) # deleting dates
    text = re.sub(r"Fő gazdasági esemény:", "", text)
    text = re.sub(r"Érintett szektor\(ok\):", "", text)
    text = re.sub(r"Rövid leírás:", "", text)
    text = re.sub(r"Összefoglalás:", "", text)
    text = re.sub(r"\s+", " ", text).strip()               # removing extra spaces
    return text

# Stopwords from file
def load_stopwords_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()} # filters out empty rows
    
hungarian_stopwords = load_stopwords_from_file("hungarian_stopwords.txt")

stopwords = STOPWORDS.union(hungarian_stopwords)

# Cleaning up summaries lists
cleaned_summaries = {
    "gazdasag": clean_summaries(summaries_gazdasag),
    "kulfold": clean_summaries(summaries_kulfold),
    "belfold": clean_summaries(summaries_belfold)
}

# Assigning titles with accents
titles_with_accents = {
    "gazdasag": "Gazdaság",
    "kulfold": "Külföld",
    "belfold": "Belföld"
}

# Plotting all three WordClouds
plt.figure(figsize=(10, 15))

for i, (topic, text) in enumerate(cleaned_summaries.items(), 1):
    wc = WordCloud(
        width=800,
        height=800,
        background_color="white",
        collocations=False,
        stopwords=stopwords,
        colormap="viridis"
    ).generate(text)
    
    plt.subplot(3, 1, i)
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title(titles_with_accents[topic])

    # Saving WordCloud as an image
    wc.to_file(f"wordcloud_{topic}_{date.today()}.png")
    
plt.tight_layout()
plt.show()

# =======================================================================================
#               E-MAIL
# =======================================================================================

import os
import base64
from datetime import date, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
CREDENTIALS_FILE = '/home/gdaniel1979/auth/client_secret_1073369059368-0kshmclsgvomtsdqoij42tdhe50ct4c4.apps.googleusercontent.com.json'
TOKEN_FILE = '/home/gdaniel1979/auth/gmail_api_token.json'
TOPICS = ["kulfold", "belfold", "gazdasag"]

# Marking accented topics in the subject line of sent emails
TOPIC_TITLES = {
    "kulfold": "KÜLFÖLD",
    "belfold": "BELFÖLD",
    "gazdasag": "GAZDASÁG"
}

FINAL_TEXTS = {
    "kulfold": final_kulfold,
    "belfold": final_belfold,
    "gazdasag": final_gazdasag
}

"""
If I want to send e-mails from saved files, then:
FINAL_TEXTS = {
    "kulfold": open("Arcive/final_kulfold.txt", "r", encoding="utf-8").read(),
    "belfold": open("Arcive/final_belfold.txt", "r", encoding="utf-8").read(),
    "gazdasag": open("Arcive/final_gazdasag.txt", "r", encoding="utf-8").read()
}
"""

WORDCLOUD_FILES = {
    "kulfold": f"wordcloud_kulfold_{date.today()}.png",
    "belfold": f"wordcloud_belfold_{date.today()}.png",
    "gazdasag": f"wordcloud_gazdasag_{date.today()}.png"
}

# ---------- AUTHENTICATION ----------

def gmail_authenticate():
    creds = None
    # Loading token if exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        # If it has expired and there is a refresh token, we will automatically refresh it.
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Saving an updated token
            with open(TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())

    # If there is no token or it is invalid, manual authentication
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        print("Open this URL in your browser and copy the code you receive here:")
        print(auth_url)
        code = input("Authorization code: ")
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

# ---------- EMAIL SENDING ----------

def create_message_with_image(to, subject, body_text, image_path):
    #  Main package
    msg = MIMEMultipart('related')
    msg['to'] = to
    msg['subject'] = subject

    # alternative section for plain text and HTML
    msg_alt = MIMEMultipart('alternative')
    msg.attach(msg_alt)

    # Plain text
    msg_alt.attach(MIMEText(body_text, 'plain'))

    # Creating an HTML body for the embedded image
    html_body = "<html><body>"
    for line in body_text.split("\n"):
        line = line.strip()
        if not line:
            html_body += "<br>"
        elif line.startswith("### "):
            html_body += f"<h2>{line[4:].strip()}</h2>"
        elif line.startswith("## "):
            html_body += f"<h3>{line[3:].strip()}</h3>"
        elif line.startswith("# "):
            html_body += f"<h1>{line[2:].strip()}</h1>"
        elif line[0:2].isdigit() and line[2] == '.':
            html_body += f"<li>{line[3:].strip()}</li>"
        elif line.startswith("- "):
            html_body += f"<li>{line[2:].strip()}</li>"
        else:
            html_body += f"<p>{line}</p>"

    html_body += f"<br><img src='cid:image1'>"
    html_body += "</body></html>"

    msg_alt.attach(MIMEText(html_body, 'html'))

    # Attaching image
    with open(image_path, 'rb') as f:
        img_data = f.read()
    image = MIMEImage(img_data)
    image.add_header('Content-ID', '<image1>')
    image.add_header('Content-Disposition', 'inline', filename=os.path.basename(image_path))
    msg.attach(image)

    # Base64 coding
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw}


def send_email(service, message):
    sent = service.users().messages().send(userId="me", body=message).execute()
    return sent

# ---------- MAIN ----------
def main():
    service = gmail_authenticate()
    for topic in TOPICS:
        subject = f"Heti hírösszefoglaló {TOPIC_TITLES[topic]} témakörben, {date.today()}"
        body = FINAL_TEXTS[topic]
        image_file = WORDCLOUD_FILES[topic]
        message = create_message_with_image("gdaniel1979@yahoo.com", subject, body, image_file)
        send_email(service, message)
        print(f"E-mail sent ({TOPIC_TITLES[topic]}), {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()

