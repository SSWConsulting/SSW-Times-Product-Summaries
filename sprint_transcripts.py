import datetime as _dt
import http.cookiejar as _cookiejar
import os as _os
import re as _re
import time as _time
from typing import Iterable, List

from openai import OpenAI
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

PLAYLISTS = {
    "YakShaver": "https://www.youtube.com/playlist?list=PLmfR0xIf_xEcXCxAldVDQGFitxvyEdAjz",
    "Tina.io": "https://www.youtube.com/playlist?list=PLPar4H9PHKVrHmaXk1oDxBBkTYEHmsvjv",
    "TinaCMS": "https://www.youtube.com/playlist?list=PLPar4H9PHKVqKlX1mqe07JZyl1L0zjqpZ",
    "TinaCloud": "https://www.youtube.com/playlist?list=PLPar4H9PHKVrahKk4PzKtcEstFDDMlxzr",
}

DAYS_BACK = 30
TITLE_KEYWORD = "sprint"
VERBOSE = True
OPENAI_MODEL = _os.getenv("OPENAI_MODEL", "gpt-5")
YTDLP_JS_RUNTIMES = _os.getenv("YTDLP_JS_RUNTIMES")
YTDLP_FFMPEG_LOCATION = _os.getenv("YTDLP_FFMPEG_LOCATION")
REQUEST_DELAY = 3  # seconds between YouTube requests to avoid IP bans
COOKIES_FILE = "cookies.txt"
MAX_BULLETS = 6
MAX_PRODUCT_CHARS = 60000
PLAYLIST_MAX_ITEMS = 12
PROMPT_FILE = "prompt.txt"


def _load_dotenv(path: str = ".env") -> None:
    if not _os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in _os.environ:
                    _os.environ[key] = value
    except OSError:
        return


def _safe_filename(title: str, video_id: str) -> str:
    base = _re.sub(r"[^A-Za-z0-9 _-]+", "_", title).strip()
    base = _re.sub(r"\s+", " ", base)
    if not base:
        base = "video"
    if len(base) > 80:
        base = base[:80].rstrip()
    return f"{base} - {video_id}.txt"


def _safe_product_filename(product: str) -> str:
    base = _re.sub(r"[^A-Za-z0-9 _-]+", "_", product).strip()
    base = _re.sub(r"\s+", " ", base)
    if not base:
        base = "product"
    if len(base) > 80:
        base = base[:80].rstrip()
    return f"{base}.txt"


def _within_days(upload_date: str, days: int) -> bool:
    if not upload_date:
        return False
    try:
        d = _dt.datetime.strptime(upload_date, "%Y%m%d").date()
    except ValueError:
        return False
    today = _dt.date.today()
    delta = (today - d).days
    return 0 <= delta <= days


def _flatten_playlist_entries(info: dict) -> Iterable[str]:
    entries = info.get("entries") or []
    for e in entries:
        if not e:
            continue
        vid = e.get("id")
        if vid:
            yield vid


def _fetch_video_info(ydl: YoutubeDL, video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    return ydl.extract_info(url, download=False)


def _get_transcript_text(video_id: str) -> str:
    import requests
    cookie_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), COOKIES_FILE)
    if _os.path.exists(cookie_path):
        cj = _cookiejar.MozillaCookieJar(cookie_path)
        cj.load(ignore_discard=True, ignore_expires=True)
        session = requests.Session()
        session.cookies = cj
        ytt_api = YouTubeTranscriptApi(http_client=session)
    else:
        ytt_api = YouTubeTranscriptApi()
    try:
        segments = ytt_api.fetch(video_id, languages=["en"])
    except Exception:
        tlist = ytt_api.list(video_id)
        transcript = None
        for t in tlist:
            transcript = t
            break
        if transcript is None:
            raise NoTranscriptFound(video_id)
        segments = transcript.fetch()

    lines: List[str] = []
    for s in segments:
        if isinstance(s, dict):
            text = s.get("text", "")
        else:
            text = getattr(s, "text", "")
        text = text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _normalize_bullets(text: str, max_items: int) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullets: List[str] = []
    for line in lines:
        line = _re.sub(r"^[-*•]\s*", "", line)
        line = _re.sub(r"^\d+[\).\s-]+", "", line).strip()
        if not line:
            continue
        bullets.append(f"- {line}")
    if not bullets:
        return "- No clearly delivered items were stated in the transcripts."
    return "\n".join(bullets[:max_items])


def _build_product_context(items: List[dict], max_chars: int) -> str:
    chunks: List[str] = []
    total = 0
    for item in items:
        header = (
            f"Title: {item['title']}\n"
            f"URL: {item['url']}\n"
            f"UploadDate: {item['upload_date']}\n"
        )
        transcript = item["transcript"]
        block = header + "\n" + transcript + "\n\n"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining <= 0:
                break
            block = block[:remaining] + "\n[Truncated]\n\n"
        chunks.append(block)
        total += len(block)
        if total >= max_chars:
            break
    return "".join(chunks)


def _summarize_product_from_transcripts(
    client: OpenAI,
    model: str,
    product: str,
    items: List[dict],
) -> str:
    context = _build_product_context(items, MAX_PRODUCT_CHARS)
    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(product=product, max_bullets=MAX_BULLETS)
    input_text = f"{prompt}\n\nTranscripts:\n{context}"
    response = client.responses.create(model=model, input=input_text)
    return response.output_text


def _load_prompt_template() -> str:
    default_prompt = (
        "You are writing internal product delivery updates for SSW employees. "
        "Summarize the main delivered items for product \"{product}\" based on the transcripts below. "
        "Focus on shipped/delivered work (not plans). "
        "Output up to {max_bullets} concise bullet points."
    )
    if not _os.path.exists(PROMPT_FILE):
        return default_prompt
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content or default_prompt
    except OSError:
        return default_prompt


def main() -> int:
    _load_dotenv()
    run_date = _dt.date.today().isoformat()
    out_dir = _os.path.join(_os.getcwd(), run_date)
    _os.makedirs(out_dir, exist_ok=True)

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }
    if YTDLP_JS_RUNTIMES:
        runtimes = [rt.strip() for rt in YTDLP_JS_RUNTIMES.split(",") if rt.strip()]
        ydl_opts["js_runtimes"] = {rt: {} for rt in runtimes}
    if YTDLP_FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = YTDLP_FFMPEG_LOCATION

    matches = 0
    product_items = {product: [] for product in PLAYLISTS}
    skipped_products = set()

    with YoutubeDL(ydl_opts) as ydl:
        for product, playlist_url in PLAYLISTS.items():
            if not playlist_url:
                skipped_products.add(product)
                if VERBOSE:
                    print(f"Skipping {product}: no playlist URL set")
                continue
            if VERBOSE:
                print(f"Fetching playlist ({product}): {playlist_url}")
            info = ydl.extract_info(playlist_url, download=False)
            video_ids = list(_flatten_playlist_entries(info))[:PLAYLIST_MAX_ITEMS]
            if VERBOSE:
                print(f"Found {len(video_ids)} videos in playlist.")
            for idx, video_id in enumerate(video_ids, start=1):
                try:
                    vinfo = _fetch_video_info(ydl, video_id)
                except Exception:
                    if VERBOSE:
                        print(f"[{idx}/{len(video_ids)}] Skipping {video_id}: metadata fetch failed")
                    continue

                title = vinfo.get("title", "")
                upload_date = vinfo.get("upload_date", "")
                if VERBOSE:
                    print(f"[{idx}/{len(video_ids)}] {upload_date} | {title}")
                if TITLE_KEYWORD not in title.lower():
                    continue
                if not _within_days(upload_date, DAYS_BACK):
                    continue

                url = f"https://www.youtube.com/watch?v={video_id}"
                filename = _safe_filename(f"{product} - {title}", video_id)
                out_path = _os.path.join(out_dir, filename)

                try:
                    transcript_text = _get_transcript_text(video_id)
                    header = (
                        f"Product: {product}\n"
                        f"Title: {title}\n"
                        f"URL: {url}\n"
                        f"UploadDate: {upload_date}\n\n"
                    )
                    content = header + transcript_text + "\n"
                    product_items[product].append(
                        {
                            "title": title,
                            "url": url,
                            "upload_date": upload_date,
                            "transcript": transcript_text,
                        }
                    )
                except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, CouldNotRetrieveTranscript) as e:
                    header = (
                        f"Product: {product}\n"
                        f"Title: {title}\n"
                        f"URL: {url}\n"
                        f"UploadDate: {upload_date}\n\n"
                        f"Transcript unavailable: {type(e).__name__}: {e}\n"
                    )
                    content = header
                except Exception as e:
                    header = (
                        f"Product: {product}\n"
                        f"Title: {title}\n"
                        f"URL: {url}\n"
                        f"UploadDate: {upload_date}\n\n"
                        f"Transcript error: {type(e).__name__}: {e}\n"
                    )
                    content = header

                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)
                matches += 1
                if VERBOSE:
                    print(f"Saved transcript: {out_path}")
                _time.sleep(REQUEST_DELAY)

    print(f"Wrote {matches} file(s) to {out_dir}")

    api_key = _os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set; skipping product summaries.")
        return 0

    client = OpenAI()
    for product in PLAYLISTS:
        summary_path = _os.path.join(out_dir, _safe_product_filename(product))

        if product in skipped_products:
            summary_text = "- Playlist URL not set for this product."
        else:
            items = product_items.get(product, [])
            if not items:
                summary_text = "- No Sprint transcripts found in the last 30 days for this product."
            else:
                try:
                    combined = _summarize_product_from_transcripts(client, OPENAI_MODEL, product, items)
                    summary_text = _normalize_bullets(combined, MAX_BULLETS)
                except Exception as e:
                    summary_text = f"- Summary error: {type(e).__name__}: {e}"

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_text + "\n")
        if VERBOSE:
            print(f"Saved summary: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
