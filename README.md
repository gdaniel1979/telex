# Telex News Scraper & Analyzer

This project scrapes articles from the Hungarian news portal **[telex.hu](https://telex.hu/)**, analyzes them using **OpenAI GPT models**, generates **summaries and word clouds**, and finally sends **weekly news reports via Gmail**.  
The workflow is automated with a **Bash script** and can be scheduled with `cron`.

---

## Features

- **Web scraping**: Collects recent articles from Telex in three categories:
  - ```🇭🇺``` Belföld (Domestic)
  - 🌍 Külföld (Foreign)
  - 💰 Gazdaság (Economy)
- **AI-based text analysis**: Uses OpenAI GPT models (`gpt-4o-mini` by default) to summarize batches of articles and produce final summaries.
- **Batch Processing:** Handles article batches to respect token limits.  
- **WordCloud visualization**: Generates word cloud images from summaries for each topic.
- **Automated email reports**: Sends formatted summaries with embedded word clouds via Gmail API.
- **Cost tracking**: Logs OpenAI token usage and estimated USD cost per run.
- **Automation**: `telex_automation.sh` handles scheduling, logging, and archiving of word clouds.

---

## Project Structure

- ```telex.py``` -> Main Python script (scraping, analysis, wordcloud, email)
- ```telex_automation.sh``` -> Bash automation script (logging + archiving)
- ```prompts.yaml``` -> External YAML file with GPT prompt templates
- ```hungarian_stopwords.txt``` -> Custom Hungarian stopword list (used in WordCloud)
- ```Wordcloud_archive/``` -> Archived WordCloud PNG files
- ```telex_automation.log``` -> Runs logs (with tokens, costs, and timestamps)

---

## Requirements

- **OpenAI API Key** stored in: ```/home/gdaniel1979/auth/openai_auth```
- **Gmail API credentials:**
  - OAuth client secret JSON: ```/home/gdaniel1979/auth/client_secret_XXXX.json```
  - Token file (auto-generated after first login): ```/home/gdaniel1979/auth/gmail_api_token.json```

---

## Authentication Setup
### 1. OpenAI
Creates a file at: ```/home/gdaniel1979/auth/openai_auth```
with content: ```openai_api_key: "YOUR_OPENAI_KEY"```

### 2. Gmail API
OAuth client secret JSON in ```/home/gdaniel1979/auth/```. 
On the first run, the script will ask for an authentication code. After fisrt run authentication is automatic.

---

## Usage
Automation with script:
```
telex_automation.sh
```
This will:
- run ```telex.py```
- save logs to ```telex_automation.log``` (newest entry on top)
- move generated WordClouds to ```Wordcloud_archive/```

**Cron job** runs every Sunday at 23:00 PM:
```0 23 * * 0 /home/gdaniel1979/hobby_projects/Telex/telex_automation.sh```

---

## Logging & Cost Tracking
Each run logs:
- Start/end time
- Duration
- Token usage (prompt & completion)
- Estimated OpenAI cost in USD
Example (```telex_automation.log```):

```yaml
RUN SUMMARY
Script start: 13:09:05
Script end  : 13:22:20
Duration    : 00:13:15
Total tokens used: 102128 (prompt: 66772, completion: 35356)
Estimated cost (USD): $0.03123
```

---

## Customization
- **Change topics**: Modify ```topics``` in ```telex.py```.
- **Update prompts**: Edit ```prompts.yaml``` to refine GPT outputs.
- **Model selection**: Change ```gpt_model``` in ```telex.py```.
- **Stopwords**: Extend ```hungarian_stopwords.txt``` for better WordCloud filtering.

---

## Email Example
Subject:
```
Heti hírösszefoglaló GAZDASÁG témakörben, 2025-08-19
```
Body:
- Final summary (analyzed by GPT)
- Embedded WordCloud image

---

## Author
**Dániel Galó**
- Data science hobbyist | Python, SQL, Bash learner
- LinkedIn: [linkedin.com/in/danielgalo](https://linkedin.com/in/danielgalo)

---

## License
This project is for personal and educational use only.
Not affiliated with Telex.hu.
