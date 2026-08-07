import httpx

from app.core.config import settings

API_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


def _parse_item(item: dict) -> dict:
    snippet = item["snippet"]["topLevelComment"]["snippet"]
    return {
        "comment_id": item["id"],
        "author": snippet.get("authorDisplayName"),
        "text": snippet.get("textOriginal", ""),
        "like_count": snippet.get("likeCount", 0),
        "published_at": snippet.get("publishedAt"),
    }


async def fetch_comments(video_id: str, max_comments: int | None = None) -> list[dict]:
    limit = max_comments or settings.max_comments
    comments: list[dict] = []
    next_page_token: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while len(comments) < limit:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "key": settings.youtube_api_key,
                "maxResults": min(100, limit - len(comments)),
                "textFormat": "plainText",
                "order": "relevance",
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                comments.append(_parse_item(item))

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break
            if len(comments) >= limit:
                break

    return comments
