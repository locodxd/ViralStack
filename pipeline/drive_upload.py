import logging
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config.settings import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Folder IDs per account (set these after creating folders in Drive)
DRIVE_FOLDERS = {
    "terror": "",       # Set in .env or here after setup
    "historias": "",
    "dinero": "",
}


def _get_drive_service():
    """Build Google Drive API service."""
    creds_path = Path(settings.google_service_account_file)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google service account file not found: {creds_path}\n"
            "Download it from Google Cloud Console > IAM & Admin > Service Accounts"
        )

    credentials = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def _ensure_folder(service, folder_name: str, parent_id: str = None) -> str:
    """Create folder if it doesn't exist, return folder ID."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]

    folder = service.files().create(body=file_metadata, fields="id").execute()
    logger.info("Created Drive folder: %s (%s)", folder_name, folder["id"])
    return folder["id"]


async def upload_to_drive(video_path: str, account: str, title: str) -> dict:
    """Upload a video to Google Drive in the account's folder.

    Returns dict with file_id and web_link.
    """
    service = _get_drive_service()

    # Ensure folder structure: TikTok Videos / {Account}
    root_folder_id = _ensure_folder(service, "TikTok Videos")
    account_display = account.capitalize()
    account_folder_id = _ensure_folder(service, account_display, root_folder_id)

    # Upload the video
    file_name = f"{title[:50]}_{Path(video_path).stem}.mp4"
    file_metadata = {
        "name": file_name,
        "parents": [account_folder_id],
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
    )

    logger.info("Uploading %s to Drive folder %s", file_name, account_display)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = file["id"]
    web_link = file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

    logger.info("Uploaded to Drive: %s (%s)", file_name, web_link)

    return {
        "file_id": file_id,
        "web_link": web_link,
    }
