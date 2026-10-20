# -*- coding: utf-8 -*-
"""push_to_google_docs.py.

Đẩy trực tiếp nội dung báo cáo từ docs/NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md
lên Google Docs: https://docs.google.com/document/d/1wAQIVk8ZPgR4LHY94oAhMgj-2SliOxVTHJbj61yCKnU
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

DOCUMENT_ID = "1wAQIVk8ZPgR4LHY94oAhMgj-2SliOxVTHJbj61yCKnU"
BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = BASE_DIR / "archive" / "google_docs_oauth" / "client_secret.json"
TOKEN_FILE = BASE_DIR / "archive" / "google_docs_oauth" / "token.json"
DOCS_CONTENT_FILE = BASE_DIR / "docs" / "NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def get_credentials() -> Credentials:
    """Lấy hoặc tạo mới token OAuth 2.0."""
    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("-> Đang làm mới (refresh) token OAuth 2.0...", flush=True)
            creds.refresh(Request())
        else:
            print("-> Mở trình duyệt để bạn đăng nhập và cấp quyền Google Docs...", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        print(f"-> Đã lưu token xác thực vào: {TOKEN_FILE}", flush=True)

    return creds


def update_document(service, doc_id: str, new_text: str):
    """Xóa nội dung cũ và ghi nội dung mới vào Google Docs."""
    print(f"-> Đang kết nối tới Google Docs ID: {doc_id}...", flush=True)
    doc = service.documents().get(documentId=doc_id).execute()
    title = doc.get("title", "")
    print(f"-> Đã kết nối thành công tài liệu: '{title}'", flush=True)

    body = doc.get("body", {})
    content = body.get("content", [])
    end_index = 1
    if content:
        last_elem = content[-1]
        end_index = last_elem.get("endIndex", 1)

    requests = []
    # 1. Xóa nội dung hiện có nếu có ký tự
    if end_index > 2:
        print(f"-> Đang xóa nội dung cũ (từ vị trí 1 đến {end_index - 1})...", flush=True)
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index - 1,
                }
            }
        })

    # 2. Chèn toàn bộ nội dung mới vào vị trí index 1
    print(f"-> Đang chèn {len(new_text)} ký tự nội dung mới vào tài liệu...", flush=True)
    requests.append({
        "insertText": {
            "location": {
                "index": 1,
            },
            "text": new_text,
        }
    })

    result = service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()
    print("-> Đã cập nhật thành công lên Google Docs!", flush=True)
    return result


def main():
    if not CLIENT_SECRET_FILE.exists():
        print(f"Lỗi: Không tìm thấy tệp {CLIENT_SECRET_FILE}!", flush=True)
        return 1

    if not DOCS_CONTENT_FILE.exists():
        print(f"Lỗi: Không tìm thấy tệp {DOCS_CONTENT_FILE}!", flush=True)
        return 1

    content_text = DOCS_CONTENT_FILE.read_text(encoding="utf-8")
    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)
    update_document(service, DOCUMENT_ID, content_text)

    print("\n" + "=" * 70)
    print("HOÀN TẤT! Toàn bộ nội dung đã được ghi trực tiếp vào Google Docs:")
    print(f"URL: https://docs.google.com/document/d/{DOCUMENT_ID}/edit")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
