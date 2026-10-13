# Telex News Scraper & Analyzer

This project scrapes articles from the Hungarian news portal **[telex.hu](https://telex.hu/)**, analyzes them with **Claude** (through the Claude Code CLI, using a Claude subscription), generates **summaries and word clouds**, and finally sends **weekly news reports via Gmail**.  
The workflow is automated with a **Bash script** and can be scheduled with `cron`.

---

## Features

- **Web scraping**: Collects recent articles from Telex in three categories:
  - ```🇭🇺``` Belföld (Domestic)
  - 🌍 Külföld (Foreign)
  - 💰 Gazdaság (Economy)
- **AI-based text analysis**: Sends batches of articles to Claude (`sonnet` by default) via `claude -p` and produces a final summary per topic. Usage is billed to the Claude subscription, not to API credits.
- **Batch Processing:** Handles article batches to respect token limits.  
- **WordCloud visualization**: Generates word cloud images from summaries for each topic.
- **Automated email reports**: Sends one combined email with the summaries and embedded word clouds via Gmail API.
- **Pre-flight checks**: Verifies Gmail and Claude authentication before scraping, and aborts early with a clear message if either fails.
- **Usage tracking**: Logs Claude token usage per run.
- **Automation**: `telex_automation.sh` runs the script from cron and writes the log.

---

## Project Structure

- ```telex.py``` -> Main Python script (scraping, analysis, wordcloud, email)
- ```telex_automation.sh``` -> Bash automation script (logging)
- ```prompts.yaml``` -> External YAML file with prompt templates
- ```hungarian_stopwords.txt``` -> Custom Hungarian stopword list (used in WordCloud)
- ```telex_automation.log``` -> Run logs (with tokens and timestamps)

---

## Requirements

- **Claude Code CLI** installed at ```/home/gdaniel1979/.local/bin/claude``` and a Claude subscription (Pro or higher)
- **Gmail API credentials:**
  - OAuth client secret JSON: ```/home/gdaniel1979/auth/client_secret_XXXX.json```
  - Token file (auto-generated after first login): ```/home/gdaniel1979/auth/gmail_api_token.json```

---

## Authentication Setup
### 1. Claude
Create a long-lived token for unattended (cron) runs:
```
claude setup-token
```
Save the token into ```/home/gdaniel1979/auth/claude_oauth_token.txt``` (```chmod 600```).
If this file is missing, the script falls back to the CLI's own login (```claude auth login```).

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

**Cron job** runs every Sunday at 23:00 PM:
```0 23 * * 0 /home/gdaniel1979/my_projects/telex/telex_automation.sh```

---

## Logging & Usage Tracking
Each run logs:
- Start/end time
- Duration
- Token usage (prompt & completion)
Example (```telex_automation.log```):

```yaml
RUN SUMMARY
Script start: 13:09:05
Script end  : 13:22:20
Duration    : 00:13:15
Total tokens used: 102128 (prompt: 66772, completion: 35356)
```

---

## Customization
- **Change topics**: Modify ```topics``` in ```telex.py```.
- **Update prompts**: Edit ```prompts.yaml``` to refine the summaries.
- **Model selection**: Change ```claude_model``` in ```telex.py``` (e.g. ```sonnet```, ```haiku```, ```opus```).
- **Batch size**: Change ```batch_size``` in ```telex.py``` (default 25 articles per request).
- **Stopwords**: Extend ```hungarian_stopwords.txt``` for better WordCloud filtering.

---

## Email Example
Subject:
```
Heti hírösszefoglaló, 2026-10-13
```
Body (for Külföld, Belföld and Gazdaság):
- Final summary (written by Claude)
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
