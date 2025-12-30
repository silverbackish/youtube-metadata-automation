import os
import time
import re

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI

# ================= CONFIG =================

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
YEAR_TO_SET = "2025"
DRY_RUN = True          # 🔴 KEEP TRUE FOR TESTING
DELAY_SECONDS = 2

# ==========================================

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- AUTHENTICATE YOUTUBE ----------

def authenticate_youtube():
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json",
        SCOPES
    )
    credentials = flow.run_local_server(port=0)
    return build("youtube", "v3", credentials=credentials)

youtube = authenticate_youtube()

# ---------- FETCH ALL VIDEO IDS ----------

def get_all_videos():
    video_ids = []

    request = youtube.search().list(
        part="id",
        forMine=True,
        maxResults=50,
        type="video"
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            video_ids.append(item["id"]["videoId"])

        request = youtube.search().list_next(request, response)

    return video_ids

# ---------- FETCH VIDEO DETAILS ----------

def get_video_details(video_ids):
    if not video_ids:
        return []

    response = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids)
    ).execute()

    return response.get("items", [])

# ---------- CHATGPT REWRITE LOGIC ----------

def rewrite(title, description):
    prompt = f"""
You are a YouTube SEO expert.

Rules:
- Replace any year in the title with {YEAR_TO_SET}
- Keep the meaning unchanged
- Rewrite description clearly and naturally
- Do NOT add emojis
- Do NOT add hashtags unless already present

Original Title:
{title}

Original Description:
{description}

Return EXACTLY in this format:
Title:
Description:
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    text = response.choices[0].message.content

    new_title = re.search(r"Title:\s*(.*)", text)
    new_desc = re.search(r"Description:\s*([\s\S]*)", text)

    if not new_title or not new_desc:
        raise ValueError("ChatGPT response format invalid")

    return new_title.group(1).strip(), new_desc.group(1).strip()

# ---------- UPDATE VIDEO METADATA ----------

def update_video(video_id, title, description, category_id):
    if DRY_RUN:
        print("[DRY RUN] Would update:", title)
        return

    youtube.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": category_id
            }
        }
    ).execute()

# ---------- MAIN EXECUTION ----------

video_ids = get_all_videos()
videos = get_video_details(video_ids)

# Sort videos by views (descending)
videos.sort(
    key=lambda v: int(v["statistics"].get("viewCount", 0)),
    reverse=True
)

for video in videos:
    snippet = video["snippet"]
    stats = video["statistics"]

    old_title = snippet["title"]
    old_description = snippet["description"]
    category_id = snippet["categoryId"]

    print(f"\nProcessing: {old_title} ({stats.get('viewCount', 0)} views)")

    try:
        new_title, new_description = rewrite(old_title, old_description)
        update_video(video["id"], new_title, new_description, category_id)
    except Exception as e:
        print("❌ Error processing this video:", e)

    time.sleep(DELAY_SECONDS)

print("\n✅ Done (dry run).")
