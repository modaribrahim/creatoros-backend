import httpx

from app.core.config import settings

THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
REPLIES_URL = "https://www.googleapis.com/youtube/v3/comments"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _parse_comment(comment: dict) -> dict:
    snippet = comment["snippet"]["topLevelComment"]["snippet"]
    return {
        "comment_id": comment["id"],
        "parent_id": None,
        "parent_text": None,
        "author": snippet.get("authorDisplayName"),
        "text": snippet.get("textOriginal", ""),
        "like_count": snippet.get("likeCount", 0),
        "published_at": snippet.get("publishedAt"),
    }


def _parse_reply(reply: dict, parent_id: str, parent_text: str) -> dict:
    snippet = reply["snippet"]
    return {
        "comment_id": reply["id"],
        "parent_id": parent_id,
        "parent_text": parent_text,
        "author": snippet.get("authorDisplayName"),
        "text": snippet.get("textOriginal", ""),
        "like_count": snippet.get("likeCount", 0),
        "published_at": snippet.get("publishedAt"),
    }


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict
) -> dict:
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def _fetch_replies(
    client: httpx.AsyncClient, parent_id: str, parent_text: str, per_thread_limit: int
) -> list[dict]:
    replies: list[dict] = []
    next_page_token: str | None = None
    while len(replies) < per_thread_limit:
        params = {
            "part": "snippet",
            "parentId": parent_id,
            "key": settings.youtube_api_key,
            "maxResults": min(100, per_thread_limit - len(replies)),
            "textFormat": "plainText",
        }
        if next_page_token:
            params["pageToken"] = next_page_token
        data = await _get_json(client, REPLIES_URL, params)
        for item in data.get("items", []):
            replies.append(_parse_reply(item, parent_id, parent_text))
        next_page_token = data.get("nextPageToken")
        if not next_page_token or len(replies) >= per_thread_limit:
            break
    return replies


async def fetch_comments(video_id: str, max_comments: int | None = None) -> list[dict]:
    """Fetch a video's comments including replies.

    Top-level comments come from `commentThreads`; for each thread that has
    replies (per ``totalReplyCount``) we also fetch its replies via
    ``comments.list?parentId=`` so threaded discussion is captured too.
    """
    limit = max_comments or settings.max_comments
    per_thread_replies = settings.max_replies_per_thread
    comments: list[dict] = []
    next_page_token: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while len(comments) < limit:
            thread_params = {
                "part": "snippet,replies",
                "videoId": video_id,
                "key": settings.youtube_api_key,
                "maxResults": min(100, limit - len(comments)),
                "textFormat": "plainText",
                "order": "relevance",
            }
            if next_page_token:
                thread_params["pageToken"] = next_page_token

            threads = await _get_json(client, THREADS_URL, thread_params)
            items = threads.get("items", [])
            if not items:
                break

            for thread in items:
                if len(comments) >= limit:
                    break
                top = _parse_comment(thread)
                comments.append(top)

                snippet = thread["snippet"]
                reply_count = int(snippet.get("totalReplyCount") or 0)
                thread_limit = min(per_thread_replies, limit - len(comments))
                if reply_count > 0 and thread_limit > 0:
                    try:
                        replies = await _fetch_replies(
                            client, thread["id"], top["text"], thread_limit
                        )
                    except httpx.HTTPStatusError:
                        replies = []
                    comments.extend(replies)
                    if len(comments) >= limit:
                        break

            next_page_token = threads.get("nextPageToken")
            if not next_page_token or len(comments) >= limit:
                break

    return comments


async def fetch_video_info(video_id: str) -> dict:
    """Fetch a video's title + channel name (best-effort, for chat context)."""
    params = {
        "part": "snippet",
        "id": video_id,
        "key": settings.youtube_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        data = await _get_json(client, VIDEOS_URL, params)
    items = data.get("items") or []
    if not items:
        return {}
    snippet = items[0].get("snippet", {})
    return {
        "title": snippet.get("title"),
        "channel_name": snippet.get("channelTitle"),
    }
