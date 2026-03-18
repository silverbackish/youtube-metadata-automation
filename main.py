import os
import sys
import time
import re
import pickle

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from openai import OpenAI

# ================= CONFIG =================

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
DELAY_SECONDS = 2
DRY_RUN = True   # 🔴 SET TO False ONLY WHEN YOU ARE READY TO ACTUALLY UPDATE VIDEOS

# ==========================================

load_dotenv()

# ---------- OPENAI CLIENT ----------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- AUTHENTICATE YOUTUBE ----------

def authenticate_youtube():
    """
    Authenticates via OAuth2 and caches the token in token.pickle
    so you don't need to re-authenticate every run.
    """
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.pickle", "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


youtube = authenticate_youtube()

# ---------- FETCH ALL VIDEO IDS (quota-efficient) ----------

def get_all_video_ids():
    """
    Uses the uploads playlist instead of search().list().
    Cost: ~1-3 quota units vs 100 per page with search().list()
    """
    # Step 1: Get uploads playlist ID for authenticated channel
    channel_response = youtube.channels().list(
        part="contentDetails",
        mine=True
    ).execute()

    items = channel_response.get("items", [])
    if not items:
        print("❌ No channel found for this account.")
        return []

    playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"📂 Uploads playlist ID: {playlist_id}")

    # Step 2: Page through the uploads playlist
    video_ids = []
    request = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=playlist_id,
        maxResults=50
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        request = youtube.playlistItems().list_next(request, response)

    print(f"✅ Found {len(video_ids)} videos.")
    return video_ids

# ---------- FETCH VIDEO DETAILS ----------

def get_video_details(video_ids):
    """
    Fetches snippet + statistics for a list of video IDs.
    YouTube API allows max 50 IDs per request.
    """
    if not video_ids:
        return []

    all_items = []

    # Batch into chunks of 50
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        response = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch)
        ).execute()
        all_items.extend(response.get("items", []))

    return all_items

# ---------- CHATGPT REWRITE LOGIC ----------

def rewrite(title, description, user_instruction):
    """
    Rewrites video title and description using GPT based on user_instruction.
    Returns (new_title, new_description) as strings.
    """
    prompt = f"""You are a YouTube SEO expert.

User instruction: {user_instruction}

Rules:
- Follow the user instruction strictly
- Keep the overall meaning of the title and description intact
- Rewrite description clearly and naturally
- Do NOT add emojis unless the user instruction asks for them
- Do NOT add hashtags unless already present or user instruction asks for them
- Return ONLY the result in the format below — no extra commentary

Original Title:
{title}

Original Description:
{description}

Return EXACTLY in this format (no extra text before or after):
Title: <rewritten title here>
Description: <rewritten description here>
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # ✅ Fixed: was "gpt-4.1-mini" which is not a valid model
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    text = response.choices[0].message.content.strip()

    # ✅ Fixed: safer parsing using split instead of fragile regex
    if "Title:" not in text or "Description:" not in text:
        raise ValueError(f"GPT response format invalid. Got:\n{text}")

    # Split on "Description:" to separate the two parts
    title_part, desc_part = text.split("Description:", 1)

    new_title = title_part.replace("Title:", "").strip()
    new_description = desc_part.strip()

    if not new_title or not new_description:
        raise ValueError("Parsed title or description is empty.")

    return new_title, new_description

# ---------- UPDATE VIDEO METADATA ----------

def update_video(video_id, title, description, category_id):
    """
    Updates the video's title and description on YouTube.
    Does nothing if DRY_RUN is True.
    """
    if DRY_RUN:
        print(f"  [DRY RUN] Would update → Title: {title[:80]}...")
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
    print(f"  ✅ Updated on YouTube.")

# ---------- MAIN EXECUTION ----------

def main():
    # Accept user instruction from command line, or prompt interactively
    if len(sys.argv) > 1:
        user_instruction = " ".join(sys.argv[1:])
    else:
        print("\n💬 Enter your instruction for rewriting video descriptions.")
        print("   Example: 'Update all years to 2025 and improve SEO clarity'")
        user_instruction = input("Your instruction: ").strip()

    if not user_instruction:
        print("❌ No instruction provided. Exiting.")
        sys.exit(1)

    print(f"\n📝 Instruction: {user_instruction}")
    print(f"🔁 DRY_RUN = {DRY_RUN}\n")

    # Fetch all videos
    video_ids = get_all_video_ids()
    if not video_ids:
        print("No videos found. Exiting.")
        sys.exit(0)

    videos = get_video_details(video_ids)

    # Sort by view count descending (most viewed first)
    videos.sort(
        key=lambda v: int(v["statistics"].get("viewCount", 0)),
        reverse=True
    )

    success_count = 0
    error_count = 0

    for video in videos:
        snippet = video["snippet"]
        stats = video["statistics"]

        old_title = snippet["title"]
        old_description = snippet.get("description", "")
        category_id = snippet["categoryId"]
        view_count = stats.get("viewCount", 0)

        print(f"\n🎬 Processing: {old_title} ({view_count} views)")

        try:
            new_title, new_description = rewrite(old_title, old_description, user_instruction)
            update_video(video["id"], new_title, new_description, category_id)
            success_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            error_count += 1

        time.sleep(DELAY_SECONDS)

    print(f"\n{'=' * 50}")
    if DRY_RUN:
        print(f"✅ Dry run complete. {success_count} videos processed, {error_count} errors.")
        print("   Set DRY_RUN = False in the script to apply changes for real.")
    else:
        print(f"✅ Done. {success_count} videos updated, {error_count} errors.")


if __name__ == "__main__":
    main()
