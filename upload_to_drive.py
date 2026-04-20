import csv
import glob
import io
import os
import sys

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", "logs")
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
OAUTH_CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = "token.json"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                print("Token has expired or been revoked. Deleting token.json — re-run on a machine with a browser to re-authenticate.")
                os.remove(TOKEN_FILE)
                sys.exit(1)
        else:
            if not os.path.exists(OAUTH_CREDENTIALS_FILE):
                print(f"Error: OAuth credentials file not found: {OAUTH_CREDENTIALS_FILE}")
                print("Download it from Google Cloud Console > APIs & Services > Credentials > OAuth 2.0 Client ID")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def find_existing_file(service, name: str, folder_id: str) -> str | None:
    """Find an existing file by name in the given folder. Returns file ID or None."""
    query = f"name = '{name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def combine_csvs(csv_paths: list[str]) -> str:
    """Combine CSV files, writing the header once and all data rows."""
    output = io.StringIO()
    writer = None
    header_written = False

    for path in csv_paths:
        with open(path, newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header and not header_written:
                writer = csv.writer(output)
                writer.writerow(header)
                header_written = True
            if writer:
                for row in reader:
                    writer.writerow(row)

    return output.getvalue()


def upload_file(service, name: str, folder_id: str, content: str):
    """Upload or update a CSV file in Google Drive."""
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/csv",
    )

    existing_id = find_existing_file(service, name, folder_id)
    if existing_id:
        service.files().update(fileId=existing_id, media_body=media).execute()
        print(f"  Updated existing file: {name}")
    else:
        metadata = {"name": name, "parents": [folder_id]}
        service.files().create(body=metadata, media_body=media).execute()
        print(f"  Created new file: {name}")


def main():
    if not FOLDER_ID:
        print("Error: GOOGLE_DRIVE_FOLDER_ID not set in .env")
        sys.exit(1)

    service = get_drive_service()

    # Find device subdirectories
    if not os.path.isdir(LOG_DIR):
        print(f"Error: Log directory not found: {LOG_DIR}")
        sys.exit(1)

    device_dirs = [
        d for d in os.listdir(LOG_DIR)
        if os.path.isdir(os.path.join(LOG_DIR, d))
    ]

    if not device_dirs:
        print("No device directories found")
        return

    for device in sorted(device_dirs):
        device_path = os.path.join(LOG_DIR, device)
        csv_files = sorted(glob.glob(os.path.join(device_path, "esphome_*.csv")))

        if not csv_files:
            print(f"{device}: No CSV files found, skipping")
            continue

        # Take the 2 newest (or 1 if only 1 exists)
        newest = csv_files[-2:] if len(csv_files) >= 2 else csv_files

        print(f"{device}: Combining {len(newest)} CSV file(s)")
        combined = combine_csvs(newest)
        upload_file(service, f"{device}.csv", FOLDER_ID, combined)

    print("Done")


if __name__ == "__main__":
    main()
