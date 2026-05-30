"""Export Gmail messages to CSV using the Gmail API.

This script uses an OAuth desktop flow for a personal Gmail account, fetches
messages matching a Gmail query, and writes the following fields to CSV:
- date
- time
- sender
- subject
- content

Usage:
    python export_gmail_to_csv.py --days 30 --output output/emails.csv

Required local files:
    credentials.json  # OAuth client JSON downloaded from Google Cloud Console

Generated locally after the first authorization:
    token.json
"""

from __future__ import annotations

import argparse
import base64
import csv
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
import re
import html as _html

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_CREDENTIALS_PATH = Path("credentials.json")
DEFAULT_TOKEN_PATH = Path("token.json")
DEFAULT_OUTPUT_PATH = Path("output/emails-clean.csv")
# final cleaned CSV fieldnames
CSV_FIELDNAMES = ["ID", "date", "received_time", "from", "text"]

# Allow very large CSV fields (Gmail HTML can be huge)
csv.field_size_limit(sys.maxsize)

# --- Cleaning helpers (from clean_emails.py) ---
def strip_html(s: str) -> str:
    if not s:
        return ""
    s = _html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def remove_noise(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"https?://\S+|www\.\S+", " ", text)

    noise_tokens = [
        "@media",
        "font-size",
        "line-height",
        "display:",
        "padding:",
        "margin:",
        "background:",
        "width:",
        "height:",
        "position:",
        "unsubscribe",
        "取消訂閱",
        "隱私權",
        "條款",
        "客服中心",
        "說明中心",
        "copyright",
        "all rights reserved",
        "this email",
        "you can unsubscribe",
        "opt out",
        "tracking",
        "stylesheet",
        "images",
    ]

    for token in noise_tokens:
        text = re.sub(re.escape(token), " ", text, flags=re.IGNORECASE)

    text = re.sub(r"[A-Za-z-]+\s*:\s*[^;]{1,40};?", " ", text)
    text = re.sub(r"[#\.][A-Za-z0-9_-]{3,}", " ", text)
    text = re.sub(r"\b[A-Za-z]{1,3}\d+[A-Za-z0-9_-]*\b", " ", text)
    text = re.sub(r"\(\s*\)|（\s*）", " ", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def trim_leading_garbage(text: str) -> str:
    if not text:
        return ""

    match = re.search(r"[\u4e00-\u9fff]{2,}", text)
    if match and match.start() > 40:
        return text[match.start():].strip()

    return text


def insert_sentence_breaks(text: str) -> str:
    if not text:
        return ""

    break_before = [
        "原價",
        "現價",
        "價格上升了",
        "比較航班",
        "系統於",
        "你還收藏了",
        "你收藏的航班",
        "管理收藏的航班",
        "停止所有警示",
        "立即加入",
        "立即升級",
        "活動辦法",
        "詳情參考",
        "取消訂閱",
        "說明中心",
        "客服中心",
    ]

    for keyword in break_before:
        text = text.replace(keyword, f"。{keyword}")

    return text


def format_date(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date)
        return f"{dt.year}/{dt.month}/{dt.day}"
    except Exception:
        return iso_date


def format_time(hms: str) -> str:
    if not hms:
        return ""
    parts = hms.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return hms


def clean_sender(sender: str) -> str:
    if not sender:
        return ""

    text = sender.strip().strip('"')

    if "<" in text:
        text = text.split("<", 1)[0].strip()

    if "「" in text:
        text = text.split("「", 1)[0].strip()

    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_meaningful_sentence(sentence: str) -> bool:
    if not sentence:
        return False

    sentence = sentence.strip()
    if sentence == "":
        return False

    lower = sentence.lower()
    if any(token in lower for token in [
        "@media",
        "font-size",
        "display:",
        "padding:",
        "margin:",
        "background:",
        "width:",
        "height:",
        "position:",
        "unsubscribe",
        "tracking",
    ]):
        return False

    if any(token in sentence for token in ["取消訂閱", "隱私權", "條款", "客服中心", "說明中心"]):
        return False

    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", sentence))
    ascii_count = len(re.findall(r"[A-Za-z]", sentence))
    alnum_count = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", sentence))

    if alnum_count < 6:
        return False

    if chinese_count < 4:
        return False

    if ascii_count > chinese_count * 3 and chinese_count < 10:
        return False

    return True


def keep_first_sentences(text: str, max_sentences: int = 3, max_part_length: int = 80) -> str:
    if not text:
        return ""

    text = remove_noise(text)
    text = insert_sentence_breaks(text)
    text = trim_leading_garbage(text)
    text = re.sub(r"\s+", " ", text).strip()
    if text == "":
        return ""

    parts = re.split(r"(?<=[。！？.!?；;])\s+|[，]\s*|\n+", text)
    parts = [part.strip() for part in parts if part.strip()]

    meaningful_parts: list[str] = []
    for part in parts:
        if is_meaningful_sentence(part):
            if len(part) > max_part_length:
                part = part[:max_part_length].rstrip() + "..."
            meaningful_parts.append(part)
        if len(meaningful_parts) >= max_sentences:
            break

    if meaningful_parts:
        return " ".join(meaningful_parts).strip()

    return text[:120].strip()

# --- end cleaning helpers ---


def load_credentials(
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> Credentials:
    """Load saved credentials or start an OAuth desktop flow."""
    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not credentials_path.is_file():
        raise FileNotFoundError(
            f"找不到 {credentials_path}，請先從 Google Cloud Console 下載 OAuth Desktop 憑證。"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    # Allow forcing console auth with environment variable (helpful on headless/remote)
    if os.environ.get("USE_CONSOLE_AUTH"):
        auth_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true")
        print("Please visit this URL to authorize this application:", auth_url)
        code = input("Enter the authorization code: ")
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    try:
        # Try local server without forcing opening a browser (safer in remote/headless)
        creds = flow.run_local_server(port=0, open_browser=False)
    except Exception:
        # Fallback to console flow if local server or browser opening fails
        creds = flow.run_console()

    # Persist the credentials so subsequent runs don't require re-auth.
    if creds:
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def gmail_service(creds: Credentials):
    """Build the Gmail API client."""
    return build("gmail", "v1", credentials=creds)


def list_message_ids(service, query: str, max_messages: int | None = None) -> list[str]:
    """Return Gmail message IDs that match the query.

    If `max_messages` is set, stop after collecting that many IDs.
    """
    message_ids: list[str] = []
    request = service.users().messages().list(userId="me", q=query, maxResults=500)

    while request is not None:
        response = request.execute()
        for message in response.get("messages", []):
            message_id = message.get("id")
            if message_id:
                message_ids.append(message_id)
                if max_messages and len(message_ids) >= max_messages:
                    return message_ids
        if max_messages and len(message_ids) >= max_messages:
            break
        request = service.users().messages().list_next(request, response)

    return message_ids


def _header_value(headers: Iterable[dict], target_name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == target_name.lower():
            return header.get("value", "")
    return ""


def _decode_base64url(data: str) -> str:
    if not data:
        return ""

    padding = "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(data + padding)
    return raw.decode("utf-8", errors="replace")


def _extract_text_from_payload(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime_type == "text/plain":
        return _decode_base64url(body.get("data", ""))

    if mime_type == "text/html":
        return _decode_base64url(body.get("data", ""))

    parts = payload.get("parts", [])
    for part in parts:
        extracted = _extract_text_from_payload(part)
        if extracted.strip():
            return extracted

    return _decode_base64url(body.get("data", ""))


def _collect_html_from_payload(payload: dict) -> str:
    """Recursively collect HTML parts from the payload and return concatenated HTML."""
    html_parts: list[str] = []

    def _collect(p: dict):
        mt = p.get("mimeType", "")
        if mt == "text/html":
            data = p.get("body", {}).get("data", "")
            if data:
                html_parts.append(_decode_base64url(data))
        for sub in p.get("parts", []):
            _collect(sub)

    _collect(payload)
    return "\n".join(html_parts)


def _strip_html_tags(html_text: str) -> str:
    """Remove HTML tags and unescape entities, collapse whitespace."""
    if not html_text:
        return ""
    # Unescape HTML entities first
    text = _html.unescape(html_text)
    # Remove tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_message_datetime(date_header: str) -> datetime:
    if not date_header:
        return datetime.now(timezone.utc)

    parsed = parsedate_to_datetime(date_header)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_message_row(service, message_id: str) -> dict[str, str]:
    message = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full",
    ).execute()

    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    message_date = _parse_message_datetime(_header_value(headers, "Date"))

    body_text = _extract_text_from_payload(payload).strip()
    sender = _header_value(headers, "From")
    subject = _header_value(headers, "Subject")

    # If extracted body looks like the generic HTML-only placeholder or is empty,
    # fall back to the message snippet, then try collecting HTML parts and
    # stripping tags, and finally fall back to the subject.
    placeholder_snippet = "To view the message, please use an HTML compatible email viewer"
    if not body_text or placeholder_snippet.lower() in body_text.lower() or len(body_text) < 20:
        snippet = message.get("snippet", "") or ""
        if snippet and len(snippet.strip()) > len(body_text):
            body_text = snippet.strip()

    if not body_text or placeholder_snippet.lower() in body_text.lower() or len(body_text) < 20:
        html_combined = _collect_html_from_payload(payload)
        if html_combined:
            stripped = _strip_html_tags(html_combined)
            if stripped:
                body_text = stripped

    if not body_text:
        body_text = subject or ""

    return {
        "date": message_date.astimezone().date().isoformat(),
        "time": message_date.astimezone().strftime("%H:%M:%S"),
        "sender": sender,
        "subject": subject,
        "content": body_text,
    }


def export_messages(
    days: int,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    token_path: Path = DEFAULT_TOKEN_PATH,
    limit: int | None = None,
    primary: bool = False,
) -> Path:
    """Fetch recent messages and write them to CSV."""
    creds = load_credentials(credentials_path=credentials_path, token_path=token_path)
    service = gmail_service(creds)

    query_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"after:{query_date}"
    if primary:
        query = f"{query} category:primary"
    message_ids = list_message_ids(service, query, max_messages=limit)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [fetch_message_row(service, message_id) for message_id in message_ids]
    rows.sort(key=lambda row: (row["date"], row["time"]), reverse=True)

    # Build cleaned rows (ID, date, received_time, from, text)
    cleaned_rows: list[dict[str, str]] = []
    for i, r in enumerate(rows, start=1):
        date = format_date(r.get("date", ""))
        time = format_time(r.get("time", ""))
        sender = clean_sender(r.get("sender", ""))
        content = r.get("content", "")
        text = keep_first_sentences(strip_html(content), max_sentences=3, max_part_length=80)
        cleaned_rows.append({
            "ID": str(i),
            "date": date,
            "received_time": time,
            "from": sender,
            "text": text,
        })

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Gmail messages to CSV")
    parser.add_argument("--days", type=int, default=30, help="Look back N days")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="CSV output path",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="OAuth client JSON file path",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Saved OAuth token file path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of messages to fetch (e.g. 10)",
    )
    parser.add_argument(
        "--primary",
        action="store_true",
        help="Only include messages in the Primary category",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = export_messages(
        days=args.days,
        output_path=args.output,
        credentials_path=args.credentials,
        token_path=args.token,
        limit=args.limit,
        primary=args.primary,
    )
    print(f"完成，已輸出到 {output_path}")


if __name__ == "__main__":
    main()
