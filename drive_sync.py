import json
import io
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def load_user_vault(handle: str, default_data: dict) -> dict:
    """Fetches user JSON from Google Drive; creates default if new."""
    service = get_drive_service()
    folder_id = st.secrets["DRIVE_FOLDER_ID"]
    clean_handle = handle.replace("@", "").lower().strip()
    filename = f"user_{clean_handle}.json"

    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if not files:
        save_user_vault(handle, default_data)
        return default_data

    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    try:
        return json.loads(fh.read().decode('utf-8'))
    except Exception:
        return default_data

def save_user_vault(handle: str, data: dict):
    """Writes updated user vault dictionary back to Drive."""
    service = get_drive_service()
    folder_id = st.secrets["DRIVE_FOLDER_ID"]
    clean_handle = handle.replace("@", "").lower().strip()
    filename = f"user_{clean_handle}.json"

    media = MediaIoBaseUpload(
        io.BytesIO(json.dumps(data, indent=2).encode('utf-8')),
        mimetype='application/json',
        resumable=True
    )

    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        file_metadata = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
