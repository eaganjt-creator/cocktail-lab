import os
import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from PIL import Image
import google.generativeai as genai
from drive_sync import load_user_vault, save_user_vault

st.set_page_config(
    page_title="COCKTaiL — Speakeasy Lab Bench",
    page_icon="🥃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Gemini
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    vision_model = genai.GenerativeModel("gemini-1.5-flash")
    chat_model = genai.GenerativeModel("gemini-1.5-pro")
else:
    vision_model = None
    chat_model = None

# Default template for new accounts
DEFAULT_VAULT = {
    "vault_spirits": [
        {"id": "b1", "name": "Bottled-in-Bond Bourbon", "proof": 100, "vol_oz": 21.5, "max_oz": 25.4, "color": "#c06014"},
        {"id": "b2", "name": "100-Proof Rye Whiskey", "proof": 100, "vol_oz": 12.0, "max_oz": 25.4, "color": "#a04812"},
        {"id": "b3", "name": "Craft Soda Reduction (62° Brix)", "proof": 0, "vol_oz": 7.5, "max_oz": 12.0, "color": "#3d1616"},
        {"id": "b4", "name": "Aromatic Bitters", "proof": 89, "vol_oz": 3.2, "max_oz": 4.0, "color": "#571809"}
    ],
    "vault_woods": {
        "Bourbon Barrel Oak": 42,
        "Wild Cherrywood": 28,
        "Smoked Hickory": 18,
        "Torched Rosemary": 12
    }
}

# Sidebar - Speakeasy User Login & Drive Sync
st.sidebar.markdown("### 🔐 Speakeasy Ledger")
user_handle = st.sidebar.text_input("Speakeasy Handle", value="@TheAlchemist")

if "active_user" not in st.session_state or st.session_state.active_user != user_handle:
    st.session_state.active_user = user_handle
    with st.spinner("Fetching vault from Google Drive..."):
        user_data = load_user_vault(user_handle, DEFAULT_VAULT)
        st.session_state.vault_spirits = user_data.get("vault_spirits", DEFAULT_VAULT["vault_spirits"])
        st.session_state.vault_woods = user_data.get("vault_woods", DEFAULT_VAULT["vault_woods"])

def sync_to_drive():
    save_user_vault(st.session_state.active_user, {
        "vault_spirits": st.session_state.vault_spirits,
        "vault_woods": st.session_state.vault_woods
    })

if "current_pours" not in st.session_state:
    st.session_state.current_pours = [
        {"spirit_name": "Bottled-in-Bond Bourbon", "oz": 2.0},
        {"spirit_name": "Craft Soda Reduction (62° Brix)", "oz": 0.35},
        {"spirit_name": "Aromatic Bitters", "oz": 0.05}
    ]

# Top Bar
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("### 🥃 COCKT<span style='color:#d97736;'>AI</span>L — Speakeasy Lab Bench", unsafe_allow_html=True)
    st.caption(f"Folio #0001 • Active Handle: **{st.session_state.active_user}** • Cloud Drive Sync: **ONLINE**")
with col_h2:
    st.markdown("<div style='text-align:right; margin-top:10px;'><span style='background:#241c14; border:1px solid #d97736; color:#d97736; padding:4px 8px; border-radius:4px; font-family:monospace; font-size:11px;'>PERSISTENT VAULT</span></div>", unsafe_allow_html=True)

st.divider()

# Main Workspace
col_glass, col_recipe, col_lab = st.columns([1, 1.2, 1.2])

with col_glass:
    st.subheader("The Mixology Pad")
    smoke_option = st.selectbox(
        "🔥 Smoke Chamber Profile:",
        ["Unsmoked", "Bourbon Barrel Oak", "Wild Cherrywood", "Smoked Hickory", "Torched Rosemary"]
    )
    
    total_oz = sum(p["oz"] for p in st.session_state.current_pours)
    total_alcohol_oz = sum(
        p["oz"] * (next((s["proof"] for s in st.session_state.vault_spirits if s["name"] == p["spirit_name"]), 0) / 200.0)
        for p in st.session_state.current_pours
    )
    starting_proof = (total_alcohol_oz / total_oz * 200.0) if total_oz > 0 else 0.0
    diluted_vol = total_oz * 1.22
    serving_abv = (total_alcohol_oz / diluted_vol * 100.0) if diluted_vol > 0 else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Pour Vol", f"{total_oz:.2f} oz")
    m2.metric("Start Proof", f"{starting_proof:.1f}°")
    m3.metric("Served ABV", f"{serving_abv:.1f}%")

    if st.button("🍸 Stir & Serve (Log Pour)", use_container_width=True, type="primary"):
        for p in st.session_state.current_pours:
            for s in st.session_state.vault_spirits:
                if s["name"] == p["spirit_name"]:
                    s["vol_oz"] = max(0.0, s["vol_oz"] - p["oz"])
        if smoke_option != "Unsmoked" and smoke_option in st.session_state.vault_woods:
            st.session_state.vault_woods[smoke_option] = max(0, st.session_state.vault_woods[smoke_option] - 1)
        sync_to_drive()
        st.success("Poured! Levels deducted and synced to Google Drive.")
        st.rerun()

with col_recipe:
    st.subheader("Formula Composition")
    recipe_title = st.text_input("Formula Title", value="Smoked Oak Reduction Old Fashioned")
    spirit_names = [s["name"] for s in st.session_state.vault_spirits]
    
    new_pours = []
    for idx, pour in enumerate(st.session_state.current_pours):
        c_name, c_amt = st.columns([2.5, 1])
        with c_name:
            curr_idx = spirit_names.index(pour["spirit_name"]) if pour["spirit_name"] in spirit_names else 0
            sel_spirit = st.selectbox(f"Component {idx+1}", spirit_names, index=curr_idx, key=f"s_{idx}")
        with c_amt:
            amt = st.number_input("Oz", value=float(pour["oz"]), step=0.1, min_value=0.0, max_value=5.0, key=f"a_{idx}")
        new_pours.append({"spirit_name": sel_spirit, "oz": amt})
    st.session_state.current_pours = new_pours

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("+ Add Component"):
            st.session_state.current_pours.append({"spirit_name": spirit_names[0], "oz": 0.5})
            st.rerun()
    with col_b2:
        if len(st.session_state.current_pours) > 1 and st.button("- Remove Last"):
            st.session_state.current_pours.pop()
            st.rerun()

with col_lab:
    st.subheader("The Lab Bench")
    smoke_score = 1 if smoke_option == "Unsmoked" else (8 if smoke_option == "Smoked Hickory" else 6)
    sweet_score = min(10.0, sum(p["oz"] * 6.5 for p in st.session_state.current_pours if "Reduction" in p["spirit_name"]))
    proof_score = min(10.0, sum(p["oz"] * 2.5 for p in st.session_state.current_pours if "Bourbon" in p["spirit_name"] or "Rye" in p["spirit_name"]))

    fig = go.Figure(data=go.Scatterpolar(
        r=[proof_score, sweet_score, 2.0, 4.0, smoke_score, 3.0 + (sweet_score * 0.3)],
        theta=['Proof', 'Sweet', 'Tart', 'Botanical', 'Smoke/Wood', 'Texture'],
        fill='toself',
        fillcolor='rgba(217, 119, 54, 0.25)',
        line=dict(color='#d97736', width=2)
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=False, range=[0, 10]), angularaxis=dict(direction="clockwise", color="#9ca3af")),
        paper_bgcolor="#111317", plot_bgcolor="#111317",
        margin=dict(l=25, r=25, t=25, b=25), height=210
    )
    st.plotly_chart(fig, use_container_width=True)

    if chat_model:
        st.markdown("**🧪 Ask the Alchemist (Gemini AI)**")
        prompt_q = st.text_input("Ask for pairings or swaps:", placeholder="What if I swap for wheated bourbon?")
        if st.button("Analyze Formula"):
            if prompt_q:
                with st.spinner("Analyzing..."):
                    context = f"Drink: {recipe_title}. Components: {json.dumps(st.session_state.current_pours)}. Smoke: {smoke_option}. Question: {prompt_q}"
                    res = chat_model.generate_content(f"You are a master craft speakeasy bartender. Answer in 2-3 concise sentences: {context}")
                    st.info(res.text)

st.divider()

# Bottom Tabs: Inventory, Vision Scanner, Brix
tab1, tab2, tab3 = st.tabs(["📦 The Vault & Par Restock", "📸 Scan Bottle (Gemini Vision)", "⚗️ Reduction Brix Math"])

with tab1:
    c_v1, c_v2 = st.columns([2, 1])
    with c_v1:
        df_spirits = pd.DataFrame(st.session_state.vault_spirits)[["name", "proof", "vol_oz", "max_oz"]]
        df_spirits["Fill %"] = ((df_spirits["vol_oz"] / df_spirits["max_oz"]) * 100).round(1).astype(str) + "%"
        st.dataframe(df_spirits, hide_index=True, use_container_width=True)
    with c_v2:
        df_woods = pd.DataFrame(list(st.session_state.vault_woods.items()), columns=["Wood", "Pinches Left"])
        st.dataframe(df_woods, hide_index=True, use_container_width=True)
        restocks = [s["name"] for s in st.session_state.vault_spirits if (s["vol_oz"] / s["max_oz"]) <= 0.25]
        if restocks:
            st.warning(f"**Par Alert (Low Stock):** {', '.join(restocks)}")
        else:
            st.success("All reagents above par threshold.")

with tab2:
    st.write("Snap a photo of any bottle on your bar mat. Gemini Vision will read the label, detect proof, and estimate current fill level.")
    img_file = st.camera_input("Scan Bottle")
    if img_file and vision_model:
        img = Image.open(img_file)
        with st.spinner("Analyzing bottle via Gemini Vision..."):
            prompt = """Analyze this bottle photo for a bar catalog. Output ONLY valid JSON:
            {"name": "Full name of spirit or beverage", "proof": estimated integer proof, "fill_percentage": estimated integer 0 to 100}"""
            response = vision_model.generate_content([prompt, img])
            try:
                data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
                st.write(f"**Detected:** {data['name']} ({data['proof']}° Proof) • Fill: {data['fill_percentage']}%")
                if st.button(f"Add {data['name']} to Vault & Sync"):
                    vol = (data['fill_percentage'] / 100.0) * 25.4
                    st.session_state.vault_spirits.append({
                        "id": f"b{len(st.session_state.vault_spirits)+1}",
                        "name": data['name'],
                        "proof": data['proof'],
                        "vol_oz": vol,
                        "max_oz": 25.4,
                        "color": "#c06014"
                    })
                    sync_to_drive()
                    st.success("Bottle added and written to Google Drive!")
                    st.rerun()
            except Exception:
                st.write(response.text)

with tab3:
    r1, r2, r3 = st.columns(3)
    soda_ml = r1.number_input("Starting Soda Volume (ml)", value=710, step=50)
    added_sugar_g = r2.number_input("Added Sugar (g)", value=100, step=10)
    r3.metric("Simmer Off Target Weight", f"{int((soda_ml * 0.35) + added_sugar_g)} g", help="Take off flame at this weight for ~62° Brix.")
