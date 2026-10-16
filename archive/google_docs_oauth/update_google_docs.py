# -*- coding: utf-8 -*-
"""
update_google_docs.py
=============================================================================
Script tự động đẩy nội dung báo cáo đề tài vào Google Docs:
ID: 1wAQIVk8ZPgR4LHY94oAhMgj-2SliOxVTHJbj61yCKnU
Sử dụng Google OAuth 2.0 Desktop Client.
"""

import sys
import os
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DOCUMENT_ID = "16ZF8gM5jG7RZbJJYlxL5j1rBva5h0TWI5hsqZgsYV4g"
CLIENT_SECRET_FILE = Path("client_secret.json")
TOKEN_FILE = Path("token.json")
DOCS_CONTENT_FILE = Path("docs/NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md")

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file"
]


def get_credentials():
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
            print("-> Mở trình duyệt để xác thực cấp quyền tài khoản Google...", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        # Lưu lại token cho các lần sau
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        print(f"-> Đã lưu token xác thực vào: {TOKEN_FILE}", flush=True)

    return creds


def update_document(service, doc_id: str, new_text: str):
    """Xóa nội dung cũ và ghi nội dung mới vào Google Docs."""
    print(f"-> Đang kết nối tới Google Docs ID: {doc_id}...")
    doc = service.documents().get(documentId=doc_id).execute()
    title = doc.get("title", "")
    print(f"-> Đã kết nối thành công tài liệu: '{title}'")

    # Xác định độ dài tài liệu hiện tại
    body = doc.get("body", {})
    content = body.get("content", [])
    end_index = 1
    if content:
        last_elem = content[-1]
        end_index = last_elem.get("endIndex", 1)

    requests = []
    # 1. Xóa nội dung hiện có (nếu có nội dung > 1 ký tự)
    if end_index > 2:
        print(f"-> Đang xóa nội dung cũ (từ vị trí 1 đến {end_index - 1})...")
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index - 1
                }
            }
        })

    # 2. Chèn toàn bộ nội dung văn bản mới vào vị trí đầu tài liệu (index 1)
    print(f"-> Đang chèn {len(new_text)} ký tự nội dung mới vào tài liệu...")
    requests.append({
        "insertText": {
            "location": {
                "index": 1
            },
            "text": new_text
        }
    })

    result = service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests}
    ).execute()
    print("-> Đã hoàn thành cập nhật Google Docs thành công!")
    return result


def main():
    if not CLIENT_SECRET_FILE.exists():
        print(f"Lỗi: Không tìm thấy {CLIENT_SECRET_FILE}!")
        return

    if not DOCS_CONTENT_FILE.exists():
        print(f"Lỗi: Không tìm thấy {DOCS_CONTENT_FILE}!")
        return

    content_text = DOCS_CONTENT_FILE.read_text(encoding="utf-8")
    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)
    update_document(service, DOCUMENT_ID, content_text)
    print("\n" + "=" * 70)
    print("XONG! BẠN CÓ THỂ MỞ GOOGLE DOCS ĐỂ XEM KẾT QUẢ TRỰC TIẾP!")
    print(f"URL: https://docs.google.com/document/d/{DOCUMENT_ID}/edit")
    print("=" * 70)


if __name__ == "__main__":
    main()
