import os
import json
import base64
import io
from datetime import datetime, date
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
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
# HEADLESS KEEP-ALIVE ROUTE
# ---------------------------------------------------------
if st.query_params.get("ping") == "true":
    st.write("Speakeasy Bench: Online")
    st.stop()

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
# SENSORY & VISION ENGINE SETUP (Updated to gemini-3.8-flash)
# ---------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY")
vision_model = None
chat_model = None

if api_key:
    clean_key = str(api_key).strip().replace('"', '').replace("'", "")
    genai.configure(api_key=clean_key)
    
    target_models = [
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3.0-flash"
    ]
    selected_name = "gemini-3.8-flash"
    try:
        available = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if "generateContent" in m.supported_generation_methods
        ]
        matched = False
        for candidate in target_models:
            if candidate in available:
                selected_name = candidate
                matched = True
                break
        if not matched:
            flash_models = [m for m in available if "flash" in m.lower()]
            if flash_models:
                selected_name = flash_models[0]
            elif available:
                selected_name = available[0]
    except Exception:
        selected_name = "gemini-3.8-flash"
        
    chat_model = genai.GenerativeModel(selected_name)
    vision_model = genai.GenerativeModel(selected_name)

DEFAULT_VAULT = {
    "vault_spirits": [
        {"id": "b1", "name": "Bottled-in-Bond Bourbon", "proof": 100, "vol_oz": 21.5, "max_oz": 25.4, "color": "#c06014", "price_paid": 45.0, "market_val": 50.0, "date_added": "2026-03-01", "last_valuation_date": "2026-03-01", "rating": 88, "tasting_notes": "Caramel, toasted pecan, rich oak."},
        {"id": "b2", "name": "100-Proof Rye Whiskey", "proof": 100, "vol_oz": 12.0, "max_oz": 25.4, "color": "#8c3809", "price_paid": 55.0, "market_val": 60.0, "date_added": "2026-04-10", "last_valuation_date": "2026-04-10", "rating": 91, "tasting_notes": "Mint, pepper, baking spices, dill finish."},
        {"id": "b3", "name": "Craft Soda Reduction (62° Brix)", "proof": 0, "vol_oz": 7.5, "max_oz": 12.0, "color": "#381010", "price_paid": 8.0, "market_val": 8.0, "date_added": "2026-08-01", "last_valuation_date": "2026-08-01", "rating": 95, "tasting_notes": "Viscous vanilla, cane sugar, root spice."},
        {"id": "b4", "name": "Aromatic Bitters", "proof": 89, "vol_oz": 3.2, "max_oz": 4.0, "color": "#4a1205", "price_paid": 12.0, "market_val": 12.0, "date_added": "2026-02-15", "last_valuation_date": "2026-02-15", "rating": 90, "tasting_notes": "Cinnamon, clove, gentian root."}
    ],
    "vault_woods": {
        "Bourbon Barrel Oak": 42,
        "Wild Cherrywood": 28,
        "Smoked Hickory": 18,
        "Torched Rosemary": 12
    },
    "saved_recipes": [],
    "tasting_journal": [],
    "infinity_bottle": {
        "name": "The Speakeasy Solera",
        "total_vol_oz": 0.0,
        "weighted_proof": 0.0,
        "contributions": []
    }
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

# Load active user vault
if "active_user" not in st.session_state or st.session_state.active_user != selected_user:
    st.session_state.active_user = selected_user
    with st.spinner("Accessing vault ledger..."):
        user_data = load_user_vault(selected_user, DEFAULT_VAULT)
        st.session_state.vault_spirits = user_data.get("vault_spirits", DEFAULT_VAULT["vault_spirits"])
        st.session_state.vault_woods = user_data.get("vault_woods", DEFAULT_VAULT["vault_woods"])
        st.session_state.saved_recipes = user_data.get("saved_recipes", [])
        st.session_state.tasting_journal = user_data.get("tasting_journal", [])
        st.session_state.infinity_bottle = user_data.get("infinity_bottle", DEFAULT_VAULT["infinity_bottle"])

# Top-level session safety guarantees
if "saved_recipes" not in st.session_state:
    st.session_state.saved_recipes = []
if "tasting_journal" not in st.session_state:
    st.session_state.tasting_journal = []
if "scanned_bottle" not in st.session_state:
    st.session_state.scanned_bottle = None
if "infinity_bottle" not in st.session_state:
    st.session_state.infinity_bottle = DEFAULT_VAULT["infinity_bottle"]

def sync_to_vault():
    save_user_vault(st.session_state.active_user, {
        "vault_spirits": st.session_state.vault_spirits,
        "vault_woods": st.session_state.vault_woods,
        "saved_recipes": st.session_state.saved_recipes,
        "tasting_journal": st.session_state.tasting_journal,
        "infinity_bottle": st.session_state.infinity_bottle
    })

# Ensure Infinity Bottle exists as a selectable spirit in the vault if it has volume
inf_data = st.session_state.infinity_bottle
if inf_data.get("total_vol_oz", 0) > 0:
    inf_name = f"♾️ {inf_data.get('name', 'Living Solera')}"
    existing_inf = next((s for s in st.session_state.vault_spirits if "♾️" in s["name"]), None)
    if not existing_inf:
        st.session_state.vault_spirits.append({
            "id": "inf_1",
            "name": inf_name,
            "proof": round(inf_data.get("weighted_proof", 100)),
            "vol_oz": round(inf_data.get("total_vol_oz", 0), 2),
            "max_oz": 25.4,
            "color": "#944208",
            "price_paid": 0.0,
            "market_val": 150.0,
            "date_added": str(date.today()),
            "last_valuation_date": str(date.today()),
            "rating": 92,
            "tasting_notes": "Custom living solera blend."
        })
    else:
        existing_inf["vol_oz"] = round(inf_data.get("total_vol_oz", 0), 2)
        existing_inf["proof"] = round(inf_data.get("weighted_proof", 100))

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
    st.caption(f"Folio #0001 • Architect: **{st.session_state.active_user}** • Ledger Sync: **ONLINE**")
with col_h2:
    st.markdown("<div style='text-align:right; margin-top:10px;'><span style='background:#241c14; border:1px solid #d97736; color:#d97736; padding:4px 8px; border-radius:4px; font-family:monospace; font-size:11px;'>AUTHENTICATED</span></div>", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------
# WORKSPACE: 3 COLUMNS
# ---------------------------------------------------------
col_glass, col_recipe, col_lab = st.columns([1.1, 1.2, 1.2])

# --- COLUMN 1: GLASSWARE SILHOUETTE, SMOKE & BATCHING ---
with col_glass:
    st.subheader("The Mixology Pad")
    
    col_smoke, col_garnish = st.columns(2)
    with col_smoke:
        smoke_option = st.selectbox(
            "🔥 Smoke Profile:",
            ["Unsmoked", "Bourbon Barrel Oak", "Wild Cherrywood", "Smoked Hickory", "Torched Rosemary"]
        )
    with col_garnish:
        garnish_options = st.multiselect(
            "🍊 Garnish Express:",
            [
                "Flamed Orange Peel", 
                "Expressed Lemon Twist", 
                "Luxardo Cherry & Barspoon", 
                "Charred Rosemary Sprig", 
                "Torched Cinnamon Stick",
                "Angostura Bitters Crown",
                "Dehydrated Citrus Wheel"
            ],
            default=["Flamed Orange Peel"]
        )
        garnish_str = ", ".join(garnish_options) if garnish_options else "None / Naked"
    
    batch_mode = st.radio("Serve Format:", ["Single Glass (1x)", "Travel Flask (4x)", "Party Pitcher (8x)"], horizontal=True)
    scale_multiplier = 1.0 if "Single" in batch_mode else (4.0 if "Flask" in batch_mode else 8.0)

    base_single_oz = sum(p["oz"] for p in st.session_state.current_pours)
    scaled_total_oz = base_single_oz * scale_multiplier
    
    total_alcohol_oz = sum(
        (p["oz"] * scale_multiplier) * (next((s["proof"] for s in st.session_state.vault_spirits if s["name"] == p["spirit_name"]), 0) / 200.0)
        for p in st.session_state.current_pours
    )
    starting_proof = (total_alcohol_oz / scaled_total_oz * 200.0) if scaled_total_oz > 0 else 0.0
    
    dilution_water_oz = round(scaled_total_oz * 0.22, 2)
    diluted_vol = scaled_total_oz + dilution_water_oz
    serving_abv = (total_alcohol_oz / diluted_vol * 100.0) if diluted_vol > 0 else 0.0

    m1, m2, m3 = st.columns(3)
    m1.metric("Pour Vol", f"{scaled_total_oz:.2f} oz")
    m2.metric("Start Proof", f"{starting_proof:.1f}°")
    m3.metric("Served ABV", f"{serving_abv:.1f}%")

    if scale_multiplier > 1.0:
        st.info(f"💧 **Batch Dilution:** Stir in **{dilution_water_oz:.1f} oz** of filtered water before bottling.")

    liquid_layers = ""
    for p in reversed(st.session_state.current_pours):
        spirit = next((s for s in st.session_state.vault_spirits if s["name"] == p["spirit_name"]), None)
        color = spirit["color"] if spirit else "#c06014"
        layer_h = int((p["oz"] / max(3.0, base_single_oz)) * 95)
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
                    s["vol_oz"] = max(0.0, s["vol_oz"] - (p["oz"] * scale_multiplier))
        if smoke_option != "Unsmoked" and smoke_option in st.session_state.vault_woods:
            st.session_state.vault_woods[smoke_option] = max(0, st.session_state.vault_woods[smoke_option] - int(scale_multiplier))
        sync_to_vault()
        st.balloons()
        st.success(f"Served {batch_mode}! Inventory deducted and ledger updated.")
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
            amt = st.number_input("Oz (Base)", value=float(pour["oz"]), step=0.05, min_value=0.0, max_value=5.0, key=f"a_{idx}")
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

# --- COLUMN 3: THE LAB BENCH, SENSORY REVIEW & MASTER ALCHEMIST ---
with col_lab:
    st.subheader("The Lab Bench")
    smoke_score = 1 if smoke_option == "Unsmoked" else (8 if smoke_option == "Smoked Hickory" else 6)
    sweet_score = min(10.0, sum(p["oz"] * 6.5 for p in st.session_state.current_pours if "Reduction" in p["spirit_name"] or "Syrup" in p["spirit_name"]))
    proof_score = min(10.0, sum(p["oz"] * 2.5 for p in st.session_state.current_pours if any(k in p["spirit_name"] for k in ["Bourbon", "Rye", "Whiskey", "Spirit", "Gin", "Mezcal", "Rum"])))

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

    # SENSORY REVIEW SECTION
    st.markdown("#### COCKT<span style='color:#d97736;'>AI</span>L Review", unsafe_allow_html=True)
    if chat_model:
        if st.button("Analyze Formula", use_container_width=True):
            with st.spinner("Analyzing palate equilibrium and aroma profile..."):
                prompt = f"""
                You are the master alchemist and sensory judge of an underground speakeasy.
                Review this cocktail spec:
                - Drink Title: {recipe_title}
                - Formula Ingredients: {json.dumps(st.session_state.current_pours)}
                - Total Pour Volume (Single Glass): {base_single_oz:.2f} oz
                - Starting Proof: {starting_proof:.1f}°
                - Estimated Serving ABV (diluted over rock): {serving_abv:.1f}%
                - Smoke Profile: {smoke_option}
                - Garnish Expressed: {garnish_str}

                Provide an eloquent, expert 1-paragraph sensory review. Cover the initial nose/aroma (including wood char and citrus oils), the palate structure (sweet-to-proof tension and mouthfeel), and a concluding verdict on balance.
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

        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        user_query = st.text_input("💬 Ask the Master Alchemist (Swaps, Pairings, Tweaks):", placeholder="e.g., What bitters pair best with wild cherrywood?")
        if st.button("Consult Master Alchemist"):
            if user_query:
                with st.spinner("Formulating alchemical consult..."):
                    chat_prompt = f"""
                    You are a master mixology consultant in an apothecary speakeasy.
                    Cocktail spec: {recipe_title}, Ingredients: {json.dumps(st.session_state.current_pours)}, Smoke: {smoke_option}, Garnish: {garnish_str}.
                    User question: {user_query}
                    Provide a concise, direct, 2-to-3 sentence master bartender recommendation.
                    """
                    try:
                        consult_res = chat_model.generate_content(chat_prompt)
                        st.info(consult_res.text)
                    except Exception as e:
                        st.error(f"Consult Error: {e}")
    else:
        st.caption("Sensory engine pending key verification.")

st.divider()

# ---------------------------------------------------------
# BOTTOM SECTION: 8 WORKBENCH TABS
# ---------------------------------------------------------
tab_card, tab_journal, tab_vault, tab_scanner, tab_reduction, tab_cloner, tab_neat, tab_liquidity = st.tabs([
    "📜 Folio & Specs",
    "📝 Tasting Journal",
    "📦 Vault & Reagents",
    "👓 Whiskey Glasses & Intake",
    "⚗️ Compound & Syrup Lab",
    "🔍 Speakeasy Cloner & Sommelier",
    "🥃 The Neat Cellar",
    "💰 Liquidity Report & Solera"
])

# --- TAB 1: APOTHECARY FOLIO & SAVED SPECS ---
with tab_card:
    col_fc1, col_fc2 = st.columns([1.2, 1])
    with col_fc1:
        st.markdown("#### Active Apothecary Spec Card")
        ingredients_list_html = "".join([
            f"<li><span style='color:#e5e7eb;'>{p['spirit_name']}</span> — <strong style='color:#d97736;'>{(p['oz'] * scale_multiplier):.2f} oz</strong></li>"
            for p in st.session_state.current_pours
        ])

        card_html = f"""
        <div style='background:#14161b; border:2px solid #2d3139; border-radius:12px; padding:20px; max-width:520px; margin:5px 0; box-shadow:0 8px 24px rgba(0,0,0,0.6); font-family:sans-serif;'>
            <div style='border-bottom:1px solid #2d3139; padding-bottom:10px; display:flex; justify-content:space-between; align-items:center;'>
                <div>
                    <span style='font-size:10px; letter-spacing:0.1em; color:#d97736; font-family:monospace; font-weight:700;'>APOTHECARY SPEC CARD</span>
                    <h3 style='margin:4px 0 0 0; color:#f3f4f6; font-size:18px;'>{recipe_title}</h3>
                </div>
                <div style='text-align:right;'>
                    <span style='font-size:10px; color:#9ca3af;'>ARCHITECT</span><br>
                    <strong style='font-size:12px; color:#d97736;'>{st.session_state.active_user}</strong>
                </div>
            </div>
            <div style='display:flex; justify-content:space-between; margin:14px 0; background:#0f1013; padding:8px 12px; border-radius:6px; border:1px solid #242831; font-family:monospace; font-size:11px;'>
                <div>Vol: <strong style='color:#e5e7eb;'>{scaled_total_oz:.2f} oz</strong></div>
                <div>Proof: <strong style='color:#d97736;'>{starting_proof:.1f}°</strong></div>
                <div>ABV: <strong style='color:#e5e7eb;'>{serving_abv:.1f}%</strong></div>
                <div>Wood: <strong style='color:#d97736;'>{smoke_option}</strong></div>
            </div>
            <div style='margin:14px 0;'>
                <div style='font-size:11px; text-transform:uppercase; color:#9ca3af; letter-spacing:0.05em; margin-bottom:6px;'>Formula Reagents ({batch_mode})</div>
                <ul style='margin:0; padding-left:18px; line-height:1.6; font-size:12.5px;'>
                    {ingredients_list_html}
                </ul>
            </div>
            <div style='border-top:1px solid #242831; padding-top:8px; display:flex; justify-content:space-between; font-size:10px; color:#6b7280; font-family:monospace;'>
                <span>COCKTaiL Speakeasy Bench</span>
                <span>Garnish: {garnish_str}</span>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        if st.button("💾 Save Active Recipe to Folio", use_container_width=True):
            entry = {
                "title": recipe_title,
                "pours": st.session_state.current_pours,
                "smoke": smoke_option,
                "garnish": garnish_str,
                "proof": round(starting_proof, 1),
                "abv": round(serving_abv, 1)
            }
            st.session_state.saved_recipes.append(entry)
            sync_to_vault()
            st.success(f"'{recipe_title}' archived to your speakeasy folio!")
            st.rerun()

    with col_fc2:
        st.markdown("#### 📂 Saved Folio Archive")
        if st.session_state.saved_recipes:
            for idx, r in enumerate(reversed(st.session_state.saved_recipes)):
                with st.container():
                    st.markdown(f"**{r.get('title', 'Custom Spec')}** ({r.get('proof', 0)}° • {r.get('smoke', 'Unsmoked')})")
                    c_load, c_del = st.columns([1, 1])
                    with c_load:
                        if st.button(f"🥃 Load into Pad", key=f"load_r_{idx}"):
                            st.session_state.current_pours = r.get("pours", st.session_state.current_pours)
                            st.success(f"Loaded '{r.get('title')}'!")
                            st.rerun()
                    with c_del:
                        if st.button(f"Retire Spec", key=f"del_r_{idx}"):
                            true_idx = len(st.session_state.saved_recipes) - 1 - idx
                            st.session_state.saved_recipes.pop(true_idx)
                            sync_to_vault()
                            st.rerun()
                    st.divider()
        else:
            st.caption("No archived recipes yet. Formulate a spec and save it!")

# --- TAB 2: TASTING JOURNAL & PHOTO LOG ---
with tab_journal:
    st.markdown("#### Tasting Experience & Persistent Photo Log")
    st.caption("Record live impressions and upload a photo of your glass. Photos are compressed to Base64 and stored permanently in your ledger.")

    j_col1, j_col2 = st.columns([1.2, 1])
    with j_col1:
        journal_rating = st.select_slider("Palate Score / Rating:", options=["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐ (Master Spec)"], value="⭐⭐⭐⭐")
        journal_notes = st.text_area("Tasting Notes & Impressions:", placeholder="Rich caramelized vanilla from the reduction cuts through the heavy barrel char. Silky mouthfeel with lingering warmth...", height=110)
        uploaded_drink_photo = st.file_uploader("Upload Glass Photo (Camera or Album)", type=["jpg", "jpeg", "png"], key="journal_photo_input")
        
        if st.button("📝 Permanently Record Tasting Entry", type="primary", use_container_width=True):
            if journal_notes:
                img_b64 = None
                if uploaded_drink_photo:
                    pil_img = Image.open(uploaded_drink_photo)
                    pil_img.thumbnail((500, 500))
                    buffer = io.BytesIO()
                    pil_img.save(buffer, format="JPEG", quality=75)
                    img_b64 = base64.b64encode(buffer.getvalue()).decode()

                new_entry = {
                    "recipe": recipe_title,
                    "rating": journal_rating,
                    "notes": journal_notes,
                    "smoke": smoke_option,
                    "image_b64": img_b64
                }
                st.session_state.tasting_journal.append(new_entry)
                sync_to_vault()
                st.success("Tasting entry permanently logged to your vault!")
                st.rerun()
            else:
                st.warning("Please enter a tasting note before recording.")

    with j_col2:
        st.markdown("##### Past Journal Entries")
        if st.session_state.tasting_journal:
            for entry in reversed(st.session_state.tasting_journal):
                st.markdown(f"""
                <div style='background:#17191e; border:1px solid #2d3139; border-radius:6px; padding:10px; margin-bottom:8px;'>
                    <div style='display:flex; justify-content:space-between;'>
                        <strong style='color:#d97736; font-size:13px;'>{entry.get('recipe', 'Custom Spec')}</strong>
                        <span style='font-size:12px;'>{entry.get('rating', '')}</span>
                    </div>
                    <div style='font-size:11.5px; color:#9ca3af; margin:4px 0;'>{entry.get('notes', '')}</div>
                </div>
                """, unsafe_allow_html=True)
                if entry.get("image_b64"):
                    st.image(base64.b64decode(entry["image_b64"]), width=160)
        else:
            st.caption("No tasting journal entries recorded yet.")

# --- TAB 3: THE VAULT & REAGENT MANAGER ---
with tab_vault:
    c_v1, c_v2 = st.columns([2, 1])
    with c_v1:
        st.markdown("#### Vault Spirit Inventory")
        df_spirits = pd.DataFrame(st.session_state.vault_spirits)[["name", "proof", "vol_oz", "max_oz"]]
        df_spirits["Fill %"] = ((df_spirits["vol_oz"] / df_spirits["max_oz"]) * 100).round(1).astype(str) + "%"
        st.dataframe(df_spirits, hide_index=True, use_container_width=True)
        
        with st.expander("🛠️ Reagent Maintenance / Retire Bottle / Dreg Dump"):
            reagent_to_edit = st.selectbox("Select Spirit to Adjust", [s["name"] for s in st.session_state.vault_spirits])
            s_obj = next((s for s in st.session_state.vault_spirits if s["name"] == reagent_to_edit), None)
            if s_obj:
                c_ea, c_eb, c_ec = st.columns(3)
                with c_ea:
                    new_vol = st.number_input("Override Volume (oz)", value=float(s_obj["vol_oz"]), step=0.5)
                with c_eb:
                    new_proof = st.number_input("Override Proof", value=int(s_obj["proof"]), step=1)
                with c_ec:
                    new_mkt = st.number_input("Market Value ($)", value=float(s_obj.get("market_val", 50.0)), step=5.0)
                
                c_sv, c_inf, c_rm = st.columns(3)
                with c_sv:
                    if st.button("Update Spec"):
                        s_obj["vol_oz"] = new_vol
                        s_obj["proof"] = new_proof
                        s_obj["market_val"] = new_mkt
                        s_obj["last_valuation_date"] = str(date.today())
                        sync_to_vault()
                        st.success(f"Updated {reagent_to_edit}!")
                        st.rerun()
                with c_inf:
                    if st.button("♾️ Dump Dregs to Solera"):
                        oz_to_dump = s_obj["vol_oz"]
                        if oz_to_dump > 0:
                            inf = st.session_state.infinity_bottle
                            curr_oz = inf.get("total_vol_oz", 0.0)
                            curr_proof = inf.get("weighted_proof", 0.0)
                            
                            new_total_oz = curr_oz + oz_to_dump
                            new_proof_calc = ((curr_oz * curr_proof) + (oz_to_dump * s_obj["proof"])) / new_total_oz
                            
                            inf["total_vol_oz"] = round(new_total_oz, 2)
                            inf["weighted_proof"] = round(new_proof_calc, 1)
                            inf["contributions"].append({
                                "spirit_name": s_obj["name"],
                                "oz": oz_to_dump,
                                "proof": s_obj["proof"],
                                "style": "Rye" if "Rye" in s_obj["name"] else ("Bourbon" if "Bourbon" in s_obj["name"] else "Single Malt/Other")
                            })
                            s_obj["vol_oz"] = 0.0
                            sync_to_vault()
                            st.success(f"Dumped {oz_to_dump} oz of {s_obj['name']} into Infinity Decanter!")
                            st.rerun()
                with c_rm:
                    if st.button("🗑️ Retire Bottle"):
                        st.session_state.vault_spirits = [s for s in st.session_state.vault_spirits if s["name"] != reagent_to_edit]
                        sync_to_vault()
                        st.warning(f"Retired {reagent_to_edit} from bar shelf.")
                        st.rerun()

    with c_v2:
        st.markdown("#### Smoked Woods Inventory")
        df_woods = pd.DataFrame(list(st.session_state.vault_woods.items()), columns=["Wood", "Pinches Left"])
        st.dataframe(df_woods, hide_index=True, use_container_width=True)
        restocks = [s["name"] for s in st.session_state.vault_spirits if (s["vol_oz"] / s["max_oz"]) <= 0.25]
        if restocks:
            st.warning(f"**Par Alert:** {', '.join(restocks)}")
        else:
            st.success("All reagents above par threshold.")

# --- TAB 4: WHISKEY GLASSES & BOTTLE INTAKE ---
with tab_scanner:
    st.markdown("#### 👓 Bottle Provisioning & Inspection")
    st.caption("Add bottles via optical inspection with the Whiskey Glasses, or fast-provision standard bottles by name.")

    provision_mode = st.radio("Intake Method:", ["⚡ Fast Provision (Text / Name)", "📸 Whiskey Glasses (Label & Meniscus Scan)"], horizontal=True)

    if provision_mode == "⚡ Fast Provision (Text / Name)":
        c_fp1, c_fp2, c_fp3 = st.columns([2, 1, 1])
        with c_fp1:
            fast_name_input = st.text_input("Bottle Name & Expression:", placeholder="e.g., Knob Creek 9, Maker's Mark 46, Buffalo Trace")
        with c_fp2:
            fast_bottle_size = st.selectbox("Capacity", [25.4, 33.8, 12.7, 59.2], index=0, format_func=lambda x: f"{x} oz (~{int(x*29.57)} ml)", key="fast_sz")
        with c_fp3:
            fast_fill_pct = st.slider("Fill Level (%)", min_value=0, max_value=100, value=100, key="fast_fill")

        if st.button("🔍 Fetch Specs & Value", type="primary", use_container_width=True):
            if fast_name_input and chat_model:
                with st.spinner(f"Consulting distillery records for {fast_name_input}..."):
                    lookup_prompt = f"""
                    Provide technical and valuation specs for this spirit bottle: "{fast_name_input}".
                    Return ONLY valid JSON matching this exact structure:
                    {{
                      "name": "Proper formal distillery and brand title",
                      "proof": standard integer bottling proof (e.g. 100, 94, 90),
                      "est_msrp": typical USD retail price integer,
                      "est_market": typical fair secondary or retail shelf price integer,
                      "tasting_notes": "Concise 1-sentence summary of primary palate notes",
                      "suggested_hex": "hex color code representing liquid hue (e.g. #c06014 for amber bourbon, #4a1205 for dark amaro, #f4e8c1 for tequila blanco)"
                    }}
                    """
                    try:
                        res = chat_model.generate_content(lookup_prompt)
                        clean_json = res.text.replace("```json", "").replace("```", "").strip()
                        fetched = json.loads(clean_json)
                        fetched["fill_percentage"] = fast_fill_pct
                        fetched["bottle_size_oz"] = fast_bottle_size
                        st.session_state.scanned_bottle = fetched
                    except Exception as e:
                        st.error(f"Lookup Error: {e}")
            else:
                st.warning("Please enter a bottle name.")

    else:
        img_file = st.camera_input("Scan Bottle with Whiskey Glasses", key="bottle_camera")
        if img_file and vision_model:
            if st.session_state.scanned_bottle is None or st.session_state.get("last_scanned_img") != img_file.name:
                img = Image.open(img_file)
                with st.spinner("Inspecting label geometry and liquid line..."):
                    prompt = """Analyze this spirit bottle photo. Return ONLY a valid JSON object:
                    {
                      "name": "Full distillery, brand, and finish title",
                      "proof": estimated integer proof,
                      "fill_percentage": estimated integer 0 to 100,
                      "bottle_size_oz": 25.4,
                      "est_msrp": estimated integer retail MSRP in USD,
                      "est_market": estimated integer fair secondary/shelf market value in USD,
                      "tasting_notes": "Short palate description",
                      "suggested_hex": "#a04812"
                    }"""
                    try:
                        response = vision_model.generate_content([prompt, img])
                        clean_json = response.text.replace("```json", "").replace("```", "").strip()
                        st.session_state.scanned_bottle = json.loads(clean_json)
                        st.session_state.last_scanned_img = img_file.name
                    except Exception as e:
                        st.error(f"Whiskey Glasses Optical Error: {e}")

    # Editable Review Card (Shared by both Fast Add and Camera)
    if st.session_state.scanned_bottle:
        bottle = st.session_state.scanned_bottle
        st.markdown("---")
        st.markdown("##### 📝 Review & Commit Bottle to Vault")

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
                bottle_size = st.selectbox(
                    "Bottle Size", 
                    [25.4, 33.8, 12.7, 59.2], 
                    index=[25.4, 33.8, 12.7, 59.2].index(bottle.get("bottle_size_oz", 25.4)) if bottle.get("bottle_size_oz", 25.4) in [25.4, 33.8, 12.7, 59.2] else 0,
                    format_func=lambda x: f"{x} oz (~{int(x*29.57)} ml)"
                )
            with col_b5:
                tint_color = st.color_picker("Apothecary Tint", value=bottle.get("suggested_hex", "#a04812"))

            col_v1, col_v2 = st.columns(2)
            with col_v1:
                price_paid = st.number_input("Purchase Price / MSRP ($)", value=float(bottle.get("est_msrp", 50.0)), step=5.0)
            with col_v2:
                market_val = st.number_input("Estimated Fair Market Value ($)", value=float(bottle.get("est_market", 65.0)), step=5.0)

            edit_notes = st.text_input("Tasting / Palate Profile:", value=bottle.get("tasting_notes", "Classic profile."))

            calculated_oz = round((edit_fill / 100.0) * bottle_size, 2)
            st.caption(f"Calculated Available Volume: **{calculated_oz} oz** / {bottle_size} oz")

            add_submitted = st.form_submit_button("🥃 Commit Bottle to Vault", type="primary", use_container_width=True)
            if add_submitted:
                today_str = str(date.today())
                new_spirit = {
                    "id": f"b{len(st.session_state.vault_spirits) + 1}",
                    "name": edit_name.strip(),
                    "proof": int(edit_proof),
                    "vol_oz": calculated_oz,
                    "max_oz": float(bottle_size),
                    "color": tint_color,
                    "price_paid": price_paid,
                    "market_val": market_val,
                    "date_added": today_str,
                    "last_valuation_date": today_str,
                    "rating": 88,
                    "tasting_notes": edit_notes
                }
                st.session_state.vault_spirits.append(new_spirit)
                sync_to_vault()
                st.session_state.scanned_bottle = None
                st.success(f"Added '{edit_name}' to active bar vault!")
                st.rerun()

# --- TAB 5: COMPOUND & SYRUP LAB ---
with tab_reduction:
    st.markdown("#### ⚗️ Apothecary Compound & Syrup Lab")
    st.caption("Calculate target Brix, monitor shelf-stability, or boil down craft sodas for high-viscosity Old Fashioned syrups.")

    syrup_mode = st.radio("Lab Mode:", ["🍯 Rich / Infused Syrup Formulation", "🔥 Thermal Soda Reduction"], horizontal=True)

    if syrup_mode == "🍯 Rich / Infused Syrup Formulation":
        c_s1, c_s2, c_s3 = st.columns([1.5, 1, 1])
        with c_s1:
            syrup_name = st.text_input("Syrup Name", value="Honey-Apricot Rich Syrup")
            sweetener_type = st.selectbox(
                "Primary Sweetener",
                ["Raw Honey (82° Brix)", "White Sucrose / Cane (100° Brix)", "Demerara / Turbinado (99° Brix)", "Agave Nectar (75° Brix)"]
            )
        with c_s2:
            sweetener_g = st.number_input("Sweetener Mass (g)", value=200, step=25)
            liquid_g = st.number_input("Liquid Base / Juice / Water (g)", value=100, step=25)
        with c_s3:
            brix_factor = 0.82 if "Honey" in sweetener_type else (0.75 if "Agave" in sweetener_type else 1.0)
            total_solids_g = sweetener_g * brix_factor
            total_batch_g = sweetener_g + liquid_g
            calculated_brix = (total_solids_g / total_batch_g * 100.0) if total_batch_g > 0 else 0.0

            st.metric("Computed Brix", f"{calculated_brix:.1f}° Bx")
            if calculated_brix >= 65:
                st.success("Shelf Stable (6+ mos)")
            elif calculated_brix >= 50:
                st.info("Refrigerate (~4-6 weeks)")
            else:
                st.warning("Low Sugar (~2 weeks max)")

        syrup_color = st.color_picker("Syrup Apothecary Tint", value="#c07820")
        
        if st.button(f"➕ Commit '{syrup_name}' Directly to Bar Vault", use_container_width=True):
            est_fl_oz = round((total_batch_g / 1.33) / 29.57, 1)
            today_str = str(date.today())
            st.session_state.vault_spirits.append({
                "id": f"b{len(st.session_state.vault_spirits) + 1}",
                "name": f"{syrup_name} ({calculated_brix:.0f}° Brix)",
                "proof": 0,
                "vol_oz": est_fl_oz,
                "max_oz": est_fl_oz,
                "color": syrup_color,
                "price_paid": 6.0,
                "market_val": 6.0,
                "date_added": today_str,
                "last_valuation_date": today_str,
                "rating": 90,
                "tasting_notes": f"Formulated at {calculated_brix:.1f}° Brix."
            })
            sync_to_vault()
            st.success(f"Added {est_fl_oz} oz of '{syrup_name}' to your active spirit shelf!")
            st.rerun()

    else:
        r1, r2, r3 = st.columns(3)
        with r1:
            soda_type = st.selectbox("Craft Soda Profile", ["Cream Soda / Vanilla", "Dr. Pepper / Spiced Cola", "Root Beer / Birch", "Ginger Beer"])
            soda_ml = r1.number_input("Starting Soda Volume (ml)", value=710, step=50)
        with r2:
            sugar_add_g = r2.number_input("Supplemental Sugar Added (g)", value=100, step=10)
            target_brix_goal = st.slider("Target Brix Goal", 55, 68, 62)
        with r3:
            starting_sugar = soda_ml * 0.12
            total_target_solids = starting_sugar + sugar_add_g
            target_saucepan_weight = int(total_target_solids / (target_brix_goal / 100.0))
            
            st.metric("Saucepan Pull Weight", f"{target_saucepan_weight} g", help="Weigh saucepan empty first. Simmer until contents reach this target weight.")
            st.caption(f"Evaporates ~{int(soda_ml + sugar_add_g - target_saucepan_weight)} ml of excess water.")

# --- TAB 6: SPEAKEASY CLONER & SOMMELIER'S TABLE ---
with tab_cloner:
    sub_cloner, sub_somm = st.tabs(["🔍 Speakeasy Cloner (Menu Deconstruct)", "🍽️ The Sommelier's Table (Dinner Pairing)"])
    
    with sub_cloner:
        st.caption("Had an unforgettable drink at a craft cocktail bar? Upload a menu snapshot or drink photo along with field notes, and the Master Alchemist will deconstruct the exact liquid spec.")

        c_cl1, c_cl2 = st.columns([1.2, 1])
        with c_cl1:
            clone_menu_img = st.file_uploader("Upload Bar Menu Photo", type=["jpg", "jpeg", "png"], key="clone_menu_up")
            clone_drink_img = st.file_uploader("Upload Glass / Drink Photo (Optional)", type=["jpg", "jpeg", "png"], key="clone_drink_up")
            clone_observations = st.text_area(
                "Tasting Observations & Bartender Clues:",
                placeholder="e.g. Tasted like a high-rye bourbon with toasted pecan notes. Very thick mouthfeel, served over a clear hand-carved rock with a charred orange twist...",
                height=100
            )
            
            if st.button("🧪 Reverse Engineer Formula", type="primary", use_container_width=True):
                if (clone_menu_img or clone_observations) and vision_model:
                    with st.spinner("Deconstructing drink architecture, proofs, and sugar ratios..."):
                        contents = ["You are a master mixologist and reverse engineering expert."]
                        if clone_menu_img:
                            contents.append(Image.open(clone_menu_img))
                        if clone_drink_img:
                            contents.append(Image.open(clone_drink_img))
                        
                        prompt = f"""
                        Reverse engineer the exact cocktail recipe from the menu photo, drink photo, and user observations.
                        User Observations: {clone_observations}

                        Return ONLY valid JSON matching this exact structure:
                        {{
                          "drink_title": "Deconstructed Cocktail Name",
                          "pours": [
                            {{"spirit_name": "Spirit or Compound Name", "oz": 2.0}},
                            {{"spirit_name": "Syrup or Modifier Name", "oz": 0.35}}
                          ],
                          "smoke": "Unsmoked or Wood Profile",
                          "garnish": "Garnish recommendation",
                          "alchemist_breakdown": "2-3 sentences explaining why these specific ratios match the drink profile."
                        }}
                        """
                        contents.append(prompt)
                        try:
                            res = vision_model.generate_content(contents)
                            clean_json = res.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.cloned_result = json.loads(clean_json)
                        except Exception as e:
                            st.error(f"Reverse Engineering Error: {e}")
                else:
                    st.warning("Please provide either a menu photo or tasting observations.")

        with c_cl2:
            if "cloned_result" in st.session_state and st.session_state.cloned_result:
                clone = st.session_state.cloned_result
                st.markdown(f"##### 🎯 Clone Spec: {clone.get('drink_title', 'Reverse Engineered Drink')}")
                st.caption(clone.get("alchemist_breakdown", ""))
                
                st.markdown("**Deconstructed Pour Architecture:**")
                for p in clone.get("pours", []):
                    st.markdown(f"• **{p.get('oz', 0)} oz** {p.get('spirit_name', '')}")
                
                st.markdown(f"• **Wood Smoke:** {clone.get('smoke', 'Unsmoked')}")
                st.markdown(f"• **Garnish Express:** {clone.get('garnish', 'None')}")

                if st.button("🥃 Import Cloned Spec into Mixology Pad", type="primary", use_container_width=True):
                    existing_names = [s["name"] for s in st.session_state.vault_spirits]
                    for p in clone.get("pours", []):
                        p_name = p.get("spirit_name", "Modifier")
                        if p_name not in existing_names:
                            today_str = str(date.today())
                            st.session_state.vault_spirits.append({
                                "id": f"b{len(st.session_state.vault_spirits) + 1}",
                                "name": p_name,
                                "proof": 80 if any(k in p_name for k in ["Whiskey", "Bourbon", "Rye", "Spirit", "Gin", "Rum", "Tequila"]) else 0,
                                "vol_oz": 12.0,
                                "max_oz": 25.4,
                                "color": "#c06014",
                                "price_paid": 50.0,
                                "market_val": 50.0,
                                "date_added": today_str,
                                "last_valuation_date": today_str,
                                "rating": 88,
                                "tasting_notes": "Imported from Speakeasy Cloner."
                            })
                            existing_names.append(p_name)
                    
                    st.session_state.current_pours = clone.get("pours", st.session_state.current_pours)
                    sync_to_vault()
                    st.success(f"Imported '{clone.get('drink_title')}' into your Mixology Pad! Scroll up to review.")
                    st.rerun()
            else:
                st.caption("Awaiting menu snapshot or observations to deconstruct a cocktail spec.")

    with sub_somm:
        st.caption("What's for dinner? The Master Sommelier reviews your plate and formulates an equilibrium cocktail pairing using your vault inventory.")
        
        col_sm1, col_sm2 = st.columns([1.2, 1])
        with col_sm1:
            dinner_input = st.text_input("Dinner / Dish Description:", placeholder="e.g., Ribeye steak with garlic butter and grilled asparagus")
            palate_pref = st.selectbox("Palate Goal:", ["Spirit-Forward & Bold", "Bright & Acidic", "Smoky & Herbaceous", "Rich / Dessert Balance"])
            
            commons_mode = st.radio(
                "Pantry Staples Assumption:",
                ["🏛️ Strict Vault Reagents Only", "🍋 Include Kitchen Commons (Lemon, Lime, Sugar, Honey, Mint, Rosemary)"],
                index=1
            )
            
            if st.button("🍷 Formulate Culinary Pairing", type="primary", use_container_width=True):
                if dinner_input and chat_model:
                    with st.spinner("Analyzing fat, acid, and tannin bridges..."):
                        available_inv = [{"name": s["name"], "proof": s["proof"]} for s in st.session_state.vault_spirits if s["vol_oz"] > 0]
                        commons_instruction = (
                            "You may freely use common kitchen pantry staples (fresh lemon/lime juice, simple syrup, honey, fresh herbs, or club soda) alongside vault spirits."
                            if "Include" in commons_mode else
                            "STRICT CONSTRAINT: You must ONLY use ingredients listed in the Available Vault Spirits below. Do NOT assume citrus, juices, or syrups not listed."
                        )
                        
                        prompt = f"""
                        You are an expert culinary mixologist and sommelier.
                        The guest is dining on: "{dinner_input}"
                        Palate Goal: {palate_pref}
                        {commons_instruction}

                        Available Vault Spirits:
                        {json.dumps(available_inv)}

                        Available Smoked Woods:
                        {json.dumps(list(st.session_state.vault_woods.keys()))}

                        Formulate the ideal cocktail spec. Return ONLY valid JSON:
                        {{
                          "drink_title": "Custom Paired Cocktail Title",
                          "pours": [
                            {{"spirit_name": "Spirit Name", "oz": 2.0}},
                            {{"spirit_name": "Modifier or Syrup Name", "oz": 0.5}}
                          ],
                          "smoke": "Wood Name or Unsmoked",
                          "garnish": "Garnish express",
                          "pairing_bridge": "2-3 concise sentences explaining why this drink balances the meal's fats, acids, or spices."
                        }}
                        """
                        try:
                            res = chat_model.generate_content(prompt)
                            clean_json = res.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.sommelier_pairing = json.loads(clean_json)
                        except Exception as e:
                            st.error(f"Pairing Error: {e}")
                else:
                    st.warning("Please enter a dinner dish description.")

        with col_sm2:
            if "sommelier_pairing" in st.session_state and st.session_state.sommelier_pairing:
                pair = st.session_state.sommelier_pairing
                st.markdown(f"##### 🎯 Paired Spec: **{pair.get('drink_title')}**")
                st.markdown(f"""
                <div style='background:#17191e; border-left:3px solid #d97736; padding:10px; border-radius:0 6px 6px 0; font-size:12px; line-height:1.55; margin-bottom:10px;'>
                    {pair.get('pairing_bridge')}
                </div>
                """, unsafe_allow_html=True)
                
                for p in pair.get("pours", []):
                    st.markdown(f"• **{p.get('oz')} oz** {p.get('spirit_name')}")
                st.caption(f"🔥 Wood: **{pair.get('smoke')}** | 🍊 Garnish: **{pair.get('garnish')}**")

                if st.button("🍸 Mount Paired Spec to Mixology Pad", use_container_width=True):
                    existing_names = [s["name"] for s in st.session_state.vault_spirits]
                    for p in pair.get("pours", []):
                        p_name = p.get("spirit_name", "Modifier")
                        if p_name not in existing_names:
                            st.session_state.vault_spirits.append({
                                "id": f"b{len(st.session_state.vault_spirits) + 1}",
                                "name": p_name,
                                "proof": 0,
                                "vol_oz": 10.0,
                                "max_oz": 10.0,
                                "color": "#c07820",
                                "price_paid": 4.0,
                                "market_val": 4.0,
                                "date_added": str(date.today()),
                                "last_valuation_date": str(date.today()),
                                "rating": 90,
                                "tasting_notes": "Kitchen Commons staple."
                            })
                            existing_names.append(p_name)
                    st.session_state.current_pours = pair.get("pours", st.session_state.current_pours)
                    st.success("Loaded pairing into Mixology Pad! Scroll up to review and serve.")
                    st.rerun()
            else:
                st.caption("Awaiting your menu selection to craft a culinary pairing.")

# --- TAB 7: THE NEAT CELLAR (RATINGS, TWINS & GAP ANALYSIS) ---
with tab_neat:
    st.markdown("#### 🥃 The Neat Cellar & Curator Intelligence")
    st.caption("Evaluate bottles neat, log personal tasting tags, identify flavor twins, and run collection gap audits.")

    neat_spirits = [s for s in st.session_state.vault_spirits if s["proof"] >= 70]
    if neat_spirits:
        sel_bottle_name = st.selectbox("Select Cellar Bottle to Inspect:", [s["name"] for s in neat_spirits])
        active_b = next(s for s in neat_spirits if s["name"] == sel_bottle_name)

        col_n1, col_n2 = st.columns([1.2, 1])
        with col_n1:
            st.markdown(f"##### 🏷️ Palate Dossier: **{active_b['name']}** ({active_b['proof']}° Proof)")
            
            with st.form("neat_bottle_review_form"):
                score_val = st.slider("Personal Score (100-Point Basis)", min_value=50, max_value=100, value=int(active_b.get("rating", 88)))
                notes_val = st.text_area("Neat Palate Tags & Nose Profile:", value=active_b.get("tasting_notes", ""), height=90)
                
                if st.form_submit_button("💾 Save Bottle Dossier"):
                    active_b["rating"] = score_val
                    active_b["tasting_notes"] = notes_val
                    sync_to_vault()
                    st.success(f"Updated dossier for {active_b['name']}!")
                    st.rerun()

            if chat_model and st.button("👯 Find Flavor Twins & Step-Ups"):
                with st.spinner(f"Analyzing mashbill and flavor twins for {active_b['name']}..."):
                    prompt = f"""
                    A spirits drinker enjoys this neat pour:
                    Bottle: {active_b['name']}
                    Proof: {active_b['proof']}
                    User Tasting Profile: {active_b.get('tasting_notes', 'Classic profile')}

                    Recommend 3 specific alternative bottles:
                    1. Direct Flavor Twin (similar mashbill or cask finish)
                    2. The Step-Up (higher proof or premium allocation)
                    3. The Wildcard (different category/region with surprising palate overlap)

                    Keep each bullet under 2 sentences with why it fits.
                    """
                    try:
                        res = chat_model.generate_content(prompt)
                        st.session_state.neat_twins = res.text
                    except Exception as e:
                        st.error(f"Curator Error: {e}")

            if "neat_twins" in st.session_state:
                st.markdown(f"""
                <div style='background:#17191e; border-left:3px solid #d97736; padding:12px; border-radius:0 6px 6px 0; margin-top:10px; font-size:12.5px; line-height:1.6;'>
                    {st.session_state.neat_twins}
                </div>
                """, unsafe_allow_html=True)

        with col_n2:
            st.markdown("##### 📊 Whole-Bar Gap Analysis")
            st.caption("Audit your entire collection to detect missing styles, proof brackets, or barrel finishes.")
            
            if chat_model:
                if st.button("🔍 Run Curator's Gap Audit", use_container_width=True):
                    with st.spinner("Auditing bar inventory against craft categories..."):
                        bottle_inventory = [f"{s['name']} ({s['proof']}°)" for s in neat_spirits]
                        gap_prompt = f"""
                        Analyze this personal spirits cellar:
                        {json.dumps(bottle_inventory)}

                        Provide a concise, 2-paragraph professional curator audit:
                        - Paragraph 1: Analyze current core strengths (e.g., heavily tilted to high-rye, high proof, or wine finishes).
                        - Paragraph 2: Highlight the 2-3 biggest glaring 'gaps' missing to make it a well-rounded bar (e.g., missing a wheated bourbon anchor, peated scotch, botanical gin, or aged rum) and recommend 2 specific bottles to fill those voids.
                        """
                        try:
                            gap_res = chat_model.generate_content(gap_prompt)
                            st.session_state.gap_report = gap_res.text
                        except Exception as e:
                            st.error(f"Audit Error: {e}")

                if "gap_report" in st.session_state:
                    st.markdown(f"""
                    <div style='background:#14161b; border:1px solid #2d3139; padding:14px; border-radius:8px; font-size:12.5px; line-height:1.6; margin-top:8px;'>
                        {st.session_state.gap_report}
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.info("No spirits above 70° proof found in your vault. Scan or add neat spirits to activate the Cellar.")

# --- TAB 8: LIQUIDITY REPORT & THE LIVING SOLERA ---
with tab_liquidity:
    st.markdown("#### 💰 Liquid Assets & Liquidity Report")
    st.caption("Real-time actuarial valuation adjusted by the pour for collection tracking and insurance riders.")

    def get_fallback_price(name):
        lower = name.lower()
        if "bitters" in lower:
            return 12.0
        elif "reduction" in lower or "syrup" in lower:
            return 8.0
        return 50.0

    total_replacement_cost = sum(float(s.get("market_val", get_fallback_price(s["name"]))) for s in st.session_state.vault_spirits if s["proof"] >= 40)
    current_asset_value = sum(
        float(s.get("market_val", get_fallback_price(s["name"]))) * (s["vol_oz"] / max(0.1, s["max_oz"]))
        for s in st.session_state.vault_spirits if s["proof"] >= 40
    )
    total_liquid_oz = sum(s["vol_oz"] for s in st.session_state.vault_spirits if s["proof"] >= 40)
    avg_pour_cost_2oz = (current_asset_value / total_liquid_oz * 2.0) if total_liquid_oz > 0 else 0.0

    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    c_m1.metric("Replacement Basis", f"${total_replacement_cost:,.2f}", help="Total unadjusted market replacement value for insurance rider.")
    c_m2.metric("Liquid Asset Value", f"${current_asset_value:,.2f}", help="Pro-rated value based on exact meniscus liquid on hand.")
    c_m3.metric("Liquid on Hand", f"{total_liquid_oz:.1f} oz", help="Total available spirit volume across all active bottles.")
    c_m4.metric("Avg 2-oz Neat Cost", f"${avg_pour_cost_2oz:.2f}", help="Average pro-rated cost of a 2 oz pour across the vault.")

    st.markdown("---")

    col_lr1, col_lr2 = st.columns([1.3, 1])
    with col_lr1:
        st.markdown("##### 📋 Actuarial Asset Ledger")
        today = date.today()
        liquidity_rows = []
        for s in st.session_state.vault_spirits:
            if s["proof"] >= 40:
                fill_pct = (s["vol_oz"] / s["max_oz"])
                mkt = float(s.get("market_val", get_fallback_price(s["name"])))
                pro_rated = mkt * fill_pct
                pour_cost = (pro_rated / s["vol_oz"] * 2.0) if s["vol_oz"] > 0 else 0.0
                
                v_date_str = s.get("last_valuation_date", s.get("date_added", "2024-01-01"))
                try:
                    v_date = datetime.strptime(v_date_str, "%Y-%m-%d").date()
                    days_old = (today - v_date).days
                except Exception:
                    days_old = 365
                status_badge = f"⚠️ {days_old}d" if days_old >= 180 else f"✅ {days_old}d"

                liquidity_rows.append({
                    "Bottle Reagent": s["name"],
                    "Proof": f"{s['proof']}°",
                    "Liquid Left": f"{s['vol_oz']:.1f} oz ({int(fill_pct*100)}%)",
                    "Mkt Value": f"${mkt:.2f}",
                    "Asset Value": f"${pro_rated:.2f}",
                    "2oz Pour": f"${pour_cost:.2f}",
                    "Audit Age": status_badge
                })
        df_liq = pd.DataFrame(liquidity_rows)
        st.dataframe(df_liq, hide_index=True, use_container_width=True)

        csv_data = df_liq.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Liquidity Report (CSV / Insurance Rider)", data=csv_data, file_name="Speakeasy_Liquid_Assets.csv", mime="text/csv")

    with col_lr2:
        st.markdown("##### ♾️ The Infinity Decanter (Living Solera)")
        st.caption("A continuous micro-blend formulated from residual dregs and prized pours.")

        inf = st.session_state.infinity_bottle
        vol = inf.get("total_vol_oz", 0.0)
        p_wt = inf.get("weighted_proof", 0.0)

        c_if1, c_if2 = st.columns(2)
        c_if1.metric("Solera Volume", f"{vol:.1f} oz")
        c_if2.metric("Weighted Proof", f"{p_wt:.1f}°")

        if inf.get("contributions"):
            style_counts = {}
            for c in inf["contributions"]:
                style = c.get("style", "Bourbon")
                style_counts[style] = style_counts.get(style, 0.0) + c.get("oz", 0.0)
            
            fig_pie = px.pie(
                values=list(style_counts.values()),
                names=list(style_counts.keys()),
                color_discrete_sequence=["#d97736", "#8c3809", "#c06014", "#4a1205", "#e5e7eb"],
                hole=0.45
            )
            fig_pie.update_layout(
                paper_bgcolor="#111317",
                font_color="#e5e7eb",
                margin=dict(l=10, r=10, t=10, b=10),
                height=180,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            with st.expander("📜 View Solera Pour History"):
                for c in reversed(inf["contributions"]):
                    st.caption(f"• Added **{c['oz']:.1f} oz** of *{c['spirit_name']}* ({c['proof']}° {c.get('style', '')})")
        else:
            st.info("Your decanter is empty! Head to **Tab 3 (Vault & Reagents)** -> **🛠️ Reagent Maintenance** to dump residual ounces into your Solera.")
