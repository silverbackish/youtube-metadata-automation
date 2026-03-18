# YouTube Metadata Automation

Batch-rewrite your YouTube video titles and descriptions using the YouTube Data API v3 and OpenAI's GPT — based on any natural language instruction you provide.

---

## What it does

- Fetches every video on your YouTube channel (handles pagination automatically)
- Sorts them by view count (most watched first)
- Sends each video's title + description to GPT with your instruction
- Optionally updates them back on YouTube via the API
- Ships with a **Dry Run mode** so you can preview changes before anything goes live

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/silverbackish/youtube-metadata-automation.git
cd youtube-metadata-automation
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up your `.env` file
Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. Set up YouTube OAuth credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Data API v3**
3. Go to **Credentials** → Create **OAuth 2.0 Client ID** (Desktop App)
4. Download the JSON and rename it to `client_secret.json`
5. Place `client_secret.json` in the project root

> ⚠️ `client_secret.json` is in `.gitignore` — never commit it.

---

## Usage

### Dry Run (safe preview — no changes made)
Make sure `DRY_RUN = True` is set at the top of `main.py`, then:

```bash
# Pass your instruction as a command-line argument
python main.py "Update all years to 2025 and improve SEO clarity"

# Or run without arguments to be prompted interactively
python main.py
```

You'll see a preview of what each video's new title would be, without touching YouTube.

### Live Run (actually updates YouTube)
Once you're happy with the dry run output:
1. Open `main.py`
2. Set `DRY_RUN = False`
3. Run the same command again

---

## How it works

```
Authenticate via OAuth2
        ↓
Fetch uploads playlist ID (1 quota unit)
        ↓
Page through all videos (1 quota unit per 50 videos)
        ↓
Sort by view count (descending)
        ↓
For each video:
    → Send title + description + your instruction to GPT
    → Parse new title and description
    → Update on YouTube (or print preview in dry run)
    → Wait 2 seconds (rate limit protection)
```

---

## Configuration

In `main.py`:

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `True` | Preview mode — no YouTube writes |
| `DELAY_SECONDS` | `2` | Pause between API calls |
| Model | `gpt-4o-mini` | OpenAI model used |

---

## Tech Stack

- Python 3.8+
- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [OpenAI Python SDK](https://github.com/openai/openai-python) (v1.0+)
- `google-auth-oauthlib` for OAuth2
- `python-dotenv` for environment variables

---

## Notes

- Your OAuth token is cached in `token.pickle` after the first login — subsequent runs won't open a browser window
- The script fetches video IDs via the uploads playlist (not `search.list`) to stay well within YouTube's 10,000 daily quota limit
- Errors on individual videos are caught and logged — the script continues processing remaining videos

---

## License

MIT
