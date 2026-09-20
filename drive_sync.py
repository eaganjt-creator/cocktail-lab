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

def get_file_content(filename: str):
    """Fetches any JSON file from the vault folder."""
    try:
        service = get_drive_service()
        folder_id = st.secrets["DRIVE_FOLDER_ID"].strip()
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files:
            return None
        
        file_id = files[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return json.loads(fh.read().decode('utf-8'))
    except Exception:
        return None

def update_file_content(filename: str, data: dict):
    """Overwrites an existing JSON file in the vault folder."""
    try:
        service = get_drive_service()
        folder_id = st.secrets["DRIVE_FOLDER_ID"].strip()
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(data, indent=2).encode('utf-8')),
            mimetype='application/json',
            resumable=False
        )
        if files:
            service.files().update(fileId=files[0]['id'], media_body=media).execute()
            return True
        return False
    except Exception as e:
        st.error(f"Sync error: {e}")
        return False

def load_registry():
    data = get_file_content("users_registry.json")
    return data if data else {"@TheAlchemist": "alchemy100"}

def load_user_vault(handle: str, default_data: dict) -> dict:
    clean_handle = handle.replace("@", "").lower().strip()
    data = get_file_content(f"user_{clean_handle}.json")
    return data if data else default_data

def save_user_vault(handle: str, data: dict):
    clean_handle = handle.replace("@", "").lower().strip()
    update_file_content(f"user_{clean_handle}.json", data)
