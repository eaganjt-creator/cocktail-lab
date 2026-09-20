import os
import json
import base64
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from PIL import Image
import google.generativeai as genai
from drive_sync import load_registry, load_user_vault, save_user_vault

st.set_page_config(
    page_title="COCKTaiL — Speakeasy Lab Bench",
    page_icon="🥃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# STYLING OVERRIDE (Obsidian, Copper, Dark Cards)
# ---------------------------------------------------------
st.markdown("""
<style>
  .stApp { background-color: #0f1013 !important; color: #e5e7eb !important; }
  section[data-testid="stSidebar"] { background-color: #14161b !important; border-right: 1px solid #262931 !important; }
  div[data-testid="stMetric"] { background-color: #17191e !important; border: 1px solid #2d3139 !important; border-radius: 8px !important; padding: 10px 14px !important; }
  div[data-testid="stMetricValue"] > div { color: #d97736 !important; font-family: monospace !important; }
  div[data-testid="stMetricLabel"] > div { color: #9ca3af !important; text-transform: uppercase !important; font-size: 10px !important; letter-spacing: 0.05em !important; }
  div[data-baseweb="select"] > div, input, textarea { background-color: #1a1d24 !important; color: #f3f4f6 !important; border-color: #313744 !important; }
  button[kind="primary"] { background: linear-gradient(180deg, #d97736 0%, #b85e25 100%) !important; color: #0f1013 !important; font-weight: 800 !important; border: none !important; }
  button[kind="primary"]:hover { background: #e88645 !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# GEMINI MODEL SETUP (Configured for gemini-3.6-flash)
# ---------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY")
vision_model = None
chat_model = None

if api_key:
    clean_key = str(api_key).strip().replace('"', '').replace("'", "")
    genai.configure(api_key=clean_key)
    
    target_models = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
    selected_name = "gemini-3.6-flash"
    try:
        available = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if "generateContent" in m.supported_generation_methods
        ]
        for candidate in target_models:
            if candidate in available:
                selected_name = candidate
                break
        if not selected_name and available:
            selected_name = available[0]
    except Exception:
        selected_name = "gemini-3.6-flash"
        
    chat_model = genai.GenerativeModel(selected_name)
    vision_model = genai.GenerativeModel(selected_name)

DEFAULT_VAULT = {
    "vault_spirits": [
        {"id": "b1", "name": "Bottled-in-Bond Bourbon", "proof": 100, "vol_oz": 21.5, "max_oz": 25.4, "color": "#c06014"},
        {"id": "b2", "name": "100-Proof Rye Whiskey", "proof": 100, "vol_oz": 12.0, "max_oz": 25.4, "color": "#8c3809"},
        {"id": "b3", "name": "Craft Soda Reduction (62° Brix)", "proof": 0, "vol_oz": 7.5, "max_oz": 12.0, "color": "#381010"},
        {"id": "b4", "name": "Aromatic Bitters", "proof": 89, "vol_oz": 3.2, "max_oz": 4.0, "color": "#4a1205"}
    ],
    "vault_woods": {
        "Bourbon Barrel Oak": 42,
        "Wild Cherrywood": 28,
        "Smoked Hickory": 18,
        "Torched Rosemary": 12
    },
    "saved_recipes": [],
    "tasting_journal": []
}

# ---------------------------------------------------------
# SIDEBAR: SPEAKEASY LEDGER AUTHENTICATION
# ---------------------------------------------------------
st.sidebar.markdown("### 🔐 Speakeasy Ledger")
registry = load_registry()
user_list = list(registry.keys())

selected_user = st.sidebar.selectbox("Select Speakeasy Handle", user_list)
entered_pwd = st.sidebar.text_input("Vault Keycode / Password", type="password")

is_authenticated = (entered_pwd == registry.get(selected_user, ""))

if not is_authenticated:
    st.sidebar.warning("Enter keycode to access personal vault.")
    st.info("👈 Please select your handle and enter your keycode in the sidebar to unlock your bar vault.")
    st.stop()

st.sidebar.success(f"Unlocked: {selected_user}")

# Load active user vault from Google Drive with robust fallbacks
if "active_user" not in st.session_state or st.session_state.active_user != selected_user:
    st.session_state.active_user = selected_user
    with st.spinner("Accessing vault ledger..."):
        user_data = load_user_vault(selected_user, DEFAULT_VAULT)
        st.session_state.vault_spirits = user_data.get("vault_spirits", DEFAULT_VAULT["vault_spirits"])
        st.session_state.vault_woods = user_data.get("vault_woods", DEFAULT_VAULT["vault_woods"])
        st.session_state.saved_recipes = user_data.get("saved_recipes", [])
        st.session_state.tasting_journal = user_data.get("tasting_journal", [])

# Top-level session guarantees
if "saved_recipes" not in st.session_state:
    st.session_state.saved_recipes = []

if "tasting_journal" not in st.session_state:
    st.session_state.tasting_journal = []

if "scanned_bottle" not in st.session_state:
    st.session_state.scanned_bottle = None

def sync_to_drive():
    save_user_vault(st.session_state.active_user, {
        "vault_spirits": st.session_state.vault_spirits,
        "vault_woods": st.session_state.vault_woods,
        "saved_recipes": st.session_state.saved_recipes,
        "tasting_journal": st.session_state.tasting_journal
    })

if "current_pours" not in st.session_state:
    st.session_state.current_pours = [
        {"spirit_name": "Bottled-in-Bond Bourbon", "oz": 2.0},
        {"spirit_name": "Craft Soda Reduction (62° Brix)", "oz": 0.35},
        {"spirit_name": "Aromatic Bitters", "oz": 0.05}
    ]

# ---------------------------------------------------------
# HEADER & BRANDING
# ---------------------------------------------------------
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("### 🥃 COCKT<span style='color:#d97736;'>AI</span>L — Speakeasy Lab Bench", unsafe_allow_html=True)
    st.caption(f"Folio #0001 • Architect: **{st.session_state.active_user}** • Drive Sync: **ONLINE**")
with col_h2:
    st.markdown("<div style='text-align:right; margin-top:10px;'><span style='background:#241c14; border:1px solid #d97736; color:#d97736; padding:4px 8px; border-radius:4px; font-family:monospace; font-size:11px;'>AUTHENTICATED</span></div>", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------
# WORKSPACE: 3 COLUMNS
# ---------------------------------------------------------
col_glass, col_recipe, col_lab = st.columns([1.1, 1.2, 1.2])

# --- COLUMN 1: GLASSWARE SILHOUETTE & SMOKE RIG ---
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

    # DYNAMIC GLASS LIQUID RENDERING VIA STREAMLIT COMPONENTS
    liquid_layers = ""
    for p in reversed(st.session_state.current_pours):
        spirit = next((s for s in st.session_state.vault_spirits if s["name"] == p["spirit_name"]), None)
        color = spirit["color"] if spirit else "#c06014"
        layer_h = int((p["oz"] / max(3.0, total_oz)) * 95)
        if layer_h > 0:
            liquid_layers += f"<div style='height:{layer_h}px; background-color:{color}; width:100%; opacity:0.85;'></div>"

    smoke_plume = "<div style='height:14px; background:radial-gradient(circle, rgba(200,200,200,0.35) 0%, transparent 70%); border-radius:50%; margin-bottom:4px;'></div>" if smoke_option != "Unsmoked" else "<div style='height:14px;'></div>"

    glass_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {{ margin: 0; padding: 0; background: transparent; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
      </style>
    </head>
    <body>
      <div style='display:flex; flex-direction:column; align-items:center;'>
        {smoke_plume}
        <div style='border:2px solid #4a5160; border-top:none; border-radius:0 0 14px 14px; height:140px; width:120px; background:rgba(255,255,255,0.03); display:flex; flex-direction:column-reverse; overflow:hidden; position:relative; box-shadow:inset 0 -8px 16px rgba(0,0,0,0.6);'>
          <div style='position:absolute; bottom:6px; left:10px; right:10px; height:45px; background:rgba(200,235,255,0.12); border:1px solid rgba(255,255,255,0.25); border-radius:5px; text-align:center; line-height:45px; font-size:9px; font-family:monospace; color:rgba(255,255,255,0.45); pointer-events:none; z-index:10;'>2-INCH ICE</div>
          {liquid_layers}
        </div>
        <div style='width:130px; height:3px; background:radial-gradient(ellipse at center, rgba(217,119,54,0.45) 0%, transparent 75%); margin-top:4px;'></div>
      </div>
    </body>
    </html>
    """
    components.html(glass_html, height=185)

    if st.button("🍸 Stir & Serve (Log Pour)", use_container_width=True, type="primary"):
        for p in st.session_state.current_pours:
            for s in st.session_state.vault_spirits:
                if s["name"] == p["spirit_name"]:
                    s["vol_oz"] = max(0.0, s["vol_oz"] - p["oz"])
        if smoke_option != "Unsmoked" and smoke_option in st.session_state.vault_woods:
            st.session_state.vault_woods[smoke_option] = max(0, st.session_state.vault_woods[smoke_option] - 1)
        sync_to_drive()
        st.balloons()
        st.success("Served! Vault inventory depleted and synced to Google Drive.")
        st.rerun()

# --- COLUMN 2: REAGENTS & POUR COMPOSITION ---
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
            amt = st.number_input("Oz", value=float(pour["oz"]), step=0.05, min_value=0.0, max_value=5.0, key=f"a_{idx}")
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

# --- COLUMN 3: THE LAB BENCH, SENSORY REVIEW & INTERACTIVE ALCHEMIST ---
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
        margin=dict(l=25, r=25, t=25, b=25), height=200
    )
    st.plotly_chart(fig, use_container_width=True)

    # COCKTAIL SENSORY REVIEW
    st.markdown("#### COCKT<span style='color:#d97736;'>AI</span>L Review", unsafe_allow_html=True)
    if chat_model:
        if st.button("Analyze Formula", use_container_width=True):
            with st.spinner("Analyzing palate equilibrium and aroma profile..."):
                prompt = f"""
                You are the master alchemist and sensory judge of an underground speakeasy.
                Review this cocktail spec:
                - Drink Title: {recipe_title}
                - Formula Ingredients: {json.dumps(st.session_state.current_pours)}
                - Total Pour Volume: {total_oz:.2f} oz
                - Starting Proof: {starting_proof:.1f}°
                - Estimated Serving ABV (diluted over rock): {serving_abv:.1f}%
                - Smoke Profile: {smoke_option}

                Provide an eloquent, expert 1-paragraph sensory review. Cover the initial nose/aroma (including wood char), the palate structure (sweet-to-proof tension and mouthfeel), and a concluding verdict on balance.
                """
                try:
                    res = chat_model.generate_content(prompt)
                    st.session_state.latest_review = res.text
                except Exception as e:
                    st.error(f"Review Error: {e}")

        if "latest_review" in st.session_state:
            st.markdown(f"""
            <div style='background-color:#161920; border-left:3px solid #d97736; padding:10px 14px; border-radius:0 6px 6px 0; margin-top:8px; font-size:12.5px; line-height:1.55;'>
                {st.session_state.latest_review}
            </div>
            """, unsafe_allow_html=True)

        # INTERACTIVE ALCHEMIST DIALOGUE BOX
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        user_query = st.text_input("💬 Ask the Alchemist (Swaps, Pairings, Tweaks):", placeholder="e.g., What bitters pair best with wild cherrywood?")
        if st.button("Consult Alchemist"):
            if user_query:
                with st.spinner("Formulating consult..."):
                    chat_prompt = f"""
                    You are a master mixology consultant.
                    Cocktail spec: {recipe_title}, Ingredients: {json.dumps(st.session_state.current_pours)}, Smoke: {smoke_option}.
                    User question: {user_query}
                    Provide a concise, direct, 2-to-3 sentence master bartender recommendation.
                    """
                    try:
                        consult_res = chat_model.generate_content(chat_prompt)
                        st.info(consult_res.text)
                    except Exception as e:
                        st.error(f"Consult Error: {e}")
    else:
        st.caption("Provide GEMINI_API_KEY in secrets to activate sensory reviews.")

st.divider()

# ---------------------------------------------------------
# BOTTOM SECTION: 5 COMPLETE WORKBENCH TABS
# ---------------------------------------------------------
tab_card, tab_journal, tab_vault, tab_scanner, tab_reduction = st.tabs([
    "📜 Apothecary Recipe Card",
    "📝 Tasting Journal & Camera Log",
    "📦 The Vault & Restock",
    "📸 Scan Bottle (Gemini Vision)",
    "⚗️ Reduction Brix Math"
])

# --- TAB 1: APOTHECARY RECIPE CARD ---
with tab_card:
    st.markdown("#### Apothecary Recipe Folio Card")
    st.caption("Auto-generated spec card ready to review or save to your speakeasy archive.")
    
    ingredients_list_html = "".join([
        f"<li><span style='color:#e5e7eb;'>{p['spirit_name']}</span> — <strong style='color:#d97736;'>{p['oz']:.2f} oz</strong></li>"
        for p in st.session_state.current_pours
    ])

    card_html = f"""
    <div style='background:#14161b; border:2px solid #2d3139; border-radius:12px; padding:24px; max-width:540px; margin:10px auto; box-shadow:0 8px 24px rgba(0,0,0,0.6); font-family:sans-serif;'>
        <div style='border-bottom:1px solid #2d3139; padding-bottom:12px; display:flex; justify-content:space-between; align-items:center;'>
            <div>
                <span style='font-size:10px; letter-spacing:0.1em; color:#d97736; font-family:monospace; font-weight:700;'>APOTHECARY SPEC CARD</span>
                <h3 style='margin:4px 0 0 0; color:#f3f4f6; font-size:20px;'>{recipe_title}</h3>
            </div>
            <div style='text-align:right;'>
                <span style='font-size:10px; color:#9ca3af;'>ARCHITECT</span><br>
                <strong style='font-size:12px; color:#d97736;'>{st.session_state.active_user}</strong>
            </div>
        </div>
        <div style='display:flex; justify-content:space-between; margin:16px 0; background:#0f1013; padding:10px 14px; border-radius:6px; border:1px solid #242831; font-family:monospace; font-size:12px;'>
            <div>Vol: <strong style='color:#e5e7eb;'>{total_oz:.2f} oz</strong></div>
            <div>Proof: <strong style='color:#d97736;'>{starting_proof:.1f}°</strong></div>
            <div>Served ABV: <strong style='color:#e5e7eb;'>{serving_abv:.1f}%</strong></div>
            <div>Wood: <strong style='color:#d97736;'>{smoke_option}</strong></div>
        </div>
        <div style='margin:16px 0;'>
            <div style='font-size:11px; text-transform:uppercase; color:#9ca3af; letter-spacing:0.05em; margin-bottom:8px;'>Formula Reagents</div>
            <ul style='margin:0; padding-left:20px; line-height:1.7; font-size:13px;'>
                {ingredients_list_html}
            </ul>
        </div>
        <div style='border-top:1px solid #242831; padding-top:10px; display:flex; justify-content:space-between; font-size:10px; color:#6b7280; font-family:monospace;'>
            <span>COCKTaiL Speakeasy Lab Bench</span>
            <span>Folio Spec #0001</span>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)
    
    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if st.button("💾 Save Recipe to Personal Folio", use_container_width=True):
            entry = {
                "title": recipe_title,
                "pours": st.session_state.current_pours,
                "smoke": smoke_option,
                "proof": round(starting_proof, 1),
                "abv": round(serving_abv, 1)
            }
            st.session_state.saved_recipes.append(entry)
            sync_to_drive()
            st.success(f"'{recipe_title}' saved to your Google Drive folio!")

# --- TAB 2: TASTING JOURNAL & CAMERA LOG ---
with tab_journal:
    st.markdown("#### Tasting Experience & Photo Log")
    st.caption("Record live tasting impressions, attach a photo of your glass, and save to your vault archive.")

    j_col1, j_col2 = st.columns([1.2, 1])
    with j_col1:
        journal_rating = st.select_slider("Palate Score / Rating:", options=["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐ (Master Spec)"], value="⭐⭐⭐⭐")
        journal_notes = st.text_area("Tasting Notes & Impressions:", placeholder="Rich caramelized vanilla from the reduction cuts through the heavy barrel char. Silky mouthfeel with lingering warmth...", height=120)
        drink_img = st.file_uploader("Upload Drink Photo", type=["jpg", "jpeg", "png"])
        
        if st.button("📝 Record Tasting Entry", type="primary", use_container_width=True):
            if journal_notes:
                new_entry = {
                    "recipe": recipe_title,
                    "rating": journal_rating,
                    "notes": journal_notes,
                    "smoke": smoke_option
                }
                st.session_state.tasting_journal.append(new_entry)
                sync_to_drive()
                st.success("Tasting entry permanently saved to your Google Drive ledger!")
                st.rerun()
            else:
                st.warning("Please type a quick tasting note before saving.")

    with j_col2:
        if drink_img:
            st.image(drink_img, caption="Finished Glass on the Bar Mat", use_container_width=True)
        
        st.markdown("##### Past Journal Entries")
        if st.session_state.tasting_journal:
            for idx, entry in enumerate(reversed(st.session_state.tasting_journal)):
                st.markdown(f"""
                <div style='background:#17191e; border:1px solid #2d3139; border-radius:6px; padding:10px; margin-bottom:8px;'>
                    <div style='display:flex; justify-content:space-between;'>
                        <strong style='color:#d97736; font-size:13px;'>{entry.get('recipe', 'Custom Spec')}</strong>
                        <span style='font-size:12px;'>{entry.get('rating', '')}</span>
                    </div>
                    <div style='font-size:11.5px; color:#9ca3af; margin-top:4px;'>{entry.get('notes', '')}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No tasting journal entries recorded yet.")

# --- TAB 3: INVENTORY & PAR RESTOCK ---
with tab_vault:
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
            st.warning(f"**Par Alert:** {', '.join(restocks)}")
        else:
            st.success("All reagents above par threshold.")

# --- TAB 4: BOTTLE SCANNER WITH MANUAL OVERRIDE ---
with tab_scanner:
    st.markdown("#### Multimodal Label & Meniscus Scanner")
    st.caption("Snap or upload a bottle photo. Gemini Vision reads the details, then lets you fine-tune the spec before adding it to your bar.")
    
    img_file = st.camera_input("Scan Bottle", key="bottle_camera")

    if img_file and vision_model:
        # Only invoke model when a fresh snapshot arrives
        if st.session_state.scanned_bottle is None or st.session_state.get("last_scanned_img") != img_file.name:
            img = Image.open(img_file)
            with st.spinner("Analyzing label and liquid line..."):
                prompt = """Analyze this spirit bottle photo. Return ONLY a valid JSON object:
                {
                  "name": "Full distillery, brand, and finish title",
                  "proof": estimated integer proof,
                  "fill_percentage": estimated integer 0 to 100,
                  "bottle_size_oz": 25.4
                }"""
                try:
                    response = vision_model.generate_content([prompt, img])
                    clean_json = response.text.replace("```json", "").replace("```", "").strip()
                    st.session_state.scanned_bottle = json.loads(clean_json)
                    st.session_state.last_scanned_img = img_file.name
                except Exception as e:
                    st.error(f"Vision Parsing Error: {e}")

    # Editable Review Card
    if st.session_state.scanned_bottle:
        bottle = st.session_state.scanned_bottle
        st.markdown("---")
        st.markdown("##### 📝 Confirm & Adjust Bottle Specifications")

        with st.form("confirm_bottle_form"):
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                edit_name = st.text_input("Spirit / Compound Name", value=bottle.get("name", ""))
            with col_b2:
                edit_proof = st.number_input("Proof", value=int(bottle.get("proof", 80)), step=1, min_value=0, max_value=200)

            col_b3, col_b4, col_b5 = st.columns([1, 1, 1])
            with col_b3:
                edit_fill = st.slider("Meniscus Fill Level (%)", min_value=0, max_value=100, value=int(bottle.get("fill_percentage", 100)))
            with col_b4:
                bottle_size = st.selectbox("Bottle Size", [25.4, 33.8, 12.7, 59.2], index=0, format_func=lambda x: f"{x} oz (~{int(x*29.57)} ml)")
            with col_b5:
                tint_color = st.color_picker("Apothecary Tint", value="#a04812")

            calculated_oz = round((edit_fill / 100.0) * bottle_size, 2)
            st.caption(f"Calculated Available Volume: **{calculated_oz} oz** / {bottle_size} oz")

            add_submitted = st.form_submit_button("🥃 Commit Bottle to Vault & Drive", type="primary", use_container_width=True)
            if add_submitted:
                new_spirit = {
                    "id": f"b{len(st.session_state.vault_spirits) + 1}",
                    "name": edit_name.strip(),
                    "proof": int(edit_proof),
                    "vol_oz": calculated_oz,
                    "max_oz": float(bottle_size),
                    "color": tint_color
                }
                st.session_state.vault_spirits.append(new_spirit)
                sync_to_drive()
                st.session_state.scanned_bottle = None
                st.success(f"Added '{edit_name}' to active bar vault!")
                st.rerun()

# --- TAB 5: BRIX MATH ---
with tab_reduction:
    r1, r2, r3 = st.columns(3)
    soda_ml = r1.number_input("Starting Soda Volume (ml)", value=710, step=50)
    added_sugar_g = r2.number_input("Added Sugar (g)", value=100, step=10)
    r3.metric("Simmer Off Target Weight", f"{int((soda_ml * 0.35) + added_sugar_g)} g", help="Take off flame at this weight for ~62° Brix.")
