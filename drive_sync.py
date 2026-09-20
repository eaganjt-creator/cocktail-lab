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
    """Fetches user JSON from Google Drive."""
    try:
        service = get_drive_service()
        folder_id = st.secrets["DRIVE_FOLDER_ID"].strip()
        clean_handle = handle.replace("@", "").lower().strip()
        filename = f"user_{clean_handle}.json"

        # Search for file inside the folder
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if not files:
            # File doesn't exist yet; return defaults without calling .create()
            return default_data

        file_id = files[0]['id']
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        return json.loads(fh.read().decode('utf-8'))
    except Exception as e:
        st.warning(f"Note: Drive sync offline or pending initialization. Using local defaults.")
        return default_data

def save_user_vault(handle: str, data: dict):
    """Updates an existing user vault file in Drive."""
    try:
        service = get_drive_service()
        folder_id = st.secrets["DRIVE_FOLDER_ID"].strip()
        clean_handle = handle.replace("@", "").lower().strip()
        filename = f"user_{clean_handle}.json"

        # Look up existing file owned by the Drive folder owner
        query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(data, indent=2).encode('utf-8')),
            mimetype='application/json',
            resumable=False
        )

        if files:
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            st.error(f"Cannot save: Please create '{filename}' manually in the Google Drive folder first.")
    except Exception as e:
        st.error(f"Failed to sync to Drive: {e}")
