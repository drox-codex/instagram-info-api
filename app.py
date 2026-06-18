from flask import Flask, jsonify, request
import requests
import time
import random
from functools import lru_cache
from itertools import cycle
import os

app = Flask(__name__)

# ===================== PROXIES =====================
# ضع proxies هنا أو في environment variable (comma separated)
PROXIES_LIST = os.getenv("PROXIES", "").split(",") if os.getenv("PROXIES") else []
proxy_cycle = cycle(PROXIES_LIST) if PROXIES_LIST else None

def get_next_proxy():
    if not proxy_cycle:
        return None
    proxy = next(proxy_cycle).strip()
    return proxy if proxy else None

# ===================== FETCH PROFILE =====================
@lru_cache(maxsize=1024)
def fetch_instagram_profile(username, proxy=None):
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "x-ig-app-id": "936619743392459",
        "Referer": f"https://www.instagram.com/{username}/",
    }
    session = requests.Session()
    proxies = {"http": proxy, "https": proxy} if proxy else None

    backoff = 1
    for attempt in range(5):
        try:
            resp = session.get(url, headers=headers, timeout=12, proxies=proxies)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 403):
                time.sleep(backoff)
                backoff *= 2.5
            elif resp.status_code == 404:
                return {"error": "not_found", "status_code": 404}
            else:
                return {"error": "http_error", "status_code": resp.status_code}
        except Exception:
            time.sleep(backoff)
            backoff *= 2
    return {"error": "request_failed"}


# ===================== STORIES =====================
def fetch_stories(user_id, proxy=None):
    url = f"https://i.instagram.com/api/v1/feed/user/{user_id}/reel_media/"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "x-ig-app-id": "936619743392459",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        if r.status_code == 200:
            return r.json().get("items", [])
    except:
        pass
    return []


# ===================== HIGHLIGHTS =====================
def fetch_highlights(user_id, proxy=None):
    url = f"https://i.instagram.com/api/v1/highlights/{user_id}/highlights_tray/"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "x-ig-app-id": "936619743392459",
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    highlights = []
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        if r.status_code == 200:
            tray = r.json().get("tray", [])
            for item in tray:
                highlight_id = item.get("id")
                if highlight_id:
                    # جلب القصص داخل الـ highlight
                    reel_url = f"https://i.instagram.com/api/v1/feed/reels_media/?reel_ids={highlight_id}"
                    try:
                        rr = requests.get(reel_url, headers=headers, proxies=proxies, timeout=10)
                        if rr.status_code == 200:
                            highlights.append({
                                "title": item.get("title"),
                                "cover": item.get("cover_media", {}).get("cropped_image_url"),
                                "stories": rr.json().get("items", [])
                            })
                    except:
                        pass
    except:
        pass
    return highlights


@app.route("/api/insta/<username>", methods=["GET"])
def insta_info(username):
    proxy = request.args.get("proxy") or get_next_proxy()
    include_stories = request.args.get("stories", "false").lower() == "true"
    include_highlights = request.args.get("highlights", "false").lower() == "true"

    data = fetch_instagram_profile(username, proxy=proxy)

    if "error" in data:
        return jsonify(data), (data.get("status_code") or 400)

    user = data.get("data", {}).get("user") or data.get("user") or data.get("data")
    if not user:
        return jsonify({"raw": data})

    out = {
        "id": user.get("id"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "biography": user.get("biography"),
        "is_private": user.get("is_private"),
        "is_verified": user.get("is_verified"),
        "profile_pic_url": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
        "followers_count": user.get("edge_followed_by", {}).get("count") or user.get("followers_count"),
        "following_count": user.get("edge_follow", {}).get("count") or user.get("following_count"),
        "media_count": user.get("media_count") or user.get("edge_owner_to_timeline_media", {}).get("count"),
        "recent_media": [],
        "stories": [],
        "highlights": []
    }

    # Recent media (نفس السابق)
    media = user.get("edge_owner_to_timeline_media") or user.get("media") or {}
    edges = media.get("edges") or media.get("items") or []
    for e in edges[:8]:
        node = e.get("node") if isinstance(e, dict) and e.get("node") else e
        if not node: continue
        caption = None
        if node.get("edge_media_to_caption"):
            cap_edges = node["edge_media_to_caption"].get("edges") or []
            if cap_edges:
                caption = cap_edges[0]["node"].get("text")
        else:
            caption = node.get("caption")
        out["recent_media"].append({
            "id": node.get("id"),
            "shortcode": node.get("shortcode"),
            "display_url": node.get("display_url") or node.get("display_src"),
            "taken_at": node.get("taken_at_timestamp") or node.get("taken_at"),
            "caption": caption,
        })

    # Stories + Highlights
    user_id = user.get("id")
    if user_id and (include_stories or include_highlights):
        p = proxy or get_next_proxy()
        if include_stories:
            out["stories"] = fetch_stories(user_id, p)
        if include_highlights:
            out["highlights"] = fetch_highlights(user_id, p)

    return jsonify(out)


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"[🚀] Instagram Scraper API جاهز على port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
