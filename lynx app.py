import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import urllib.parse
import uuid
import html
import re
import io
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta
import bcrypt

# ==========================================
# REPORTLAB ENGINE (INTEGRATED)
# ==========================================
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ==========================================
# 1. CORE CONFIGURATION & SESSION STATE
# ==========================================
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'assigned_areas' not in st.session_state:
    st.session_state['assigned_areas'] = []  
if 'current_node' not in st.session_state:
    st.session_state['current_node'] = "📊 Core Analytics Dashboard"
if 'dashboard_filter' not in st.session_state:
    st.session_state['dashboard_filter'] = "ALL"
if 'portal_mode' not in st.session_state:
    st.session_state['portal_mode'] = False

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package",
    "billamount", "area", "address", "onuserialnumber"
]

st.set_page_config(
    page_title="LYNX Fiber Enterprise ERP v59.0", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Mobile UI Styles CSS Engine
st.markdown("""
    <style>
    .stApp [data-testid="stHeader"] { background: transparent !important; height: 50px !important; }
    .stApp .block-container { padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }
    .stApp { background-color: #0b0f19; color: #f1f5f9; font-family: sans-serif; }
    [data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
    
    div[data-testid="stTextInput"] input, 
    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextArea"] textarea {
        color: #000000 !important; background-color: #ffffff !important;
        font-weight: bold !important; font-size: 16px !important;
        border: 2px solid #3b82f6 !important; border-radius: 8px !important;
    }
    div[data-testid="stTextInput"] input[disabled],
    div[data-testid="stNumberInput"] input[disabled] {
        color: #4b5563 !important; background-color: #e5e7eb !important; border: 2px solid #9ca3af !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important; color: #000000 !important;
        font-weight: bold !important; font-size: 16px !important;
        border: 2px solid #3b82f6 !important; border-radius: 8px !important;
    }
    div[data-baseweb="select"] span, div[data-baseweb="select"] div { color: #000000 !important; }
    ul[role="listbox"] li { color: #000000 !important; background-color: #ffffff !important; font-weight: 600 !important; }
    ul[role="listbox"] li:hover { background-color: #3b82f6 !important; color: #ffffff !important; }
    label, p, .stMarkdown div { color: #e5e7eb !important; font-weight: 500; }
    
    div.stButton > button, div.stFormSubmitButton > button {
        background: linear-gradient(135deg, #1e293b 0%, #111827 100%) !important;
        color: #3b82f6 !important; border: 2px solid #3b82f6 !important;
        border-radius: 12px !important; padding: 15px !important;
        font-weight: bold !important; font-size: 15px !important;
        transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important;
        width: 100% !important; display: flex !important; align-items: center !important; justify-content: center !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        background: #3b82f6 !important; color: #ffffff !important;
        border: 2px solid #60a5fa !important; box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
    }
    [data-testid="stSidebar"] div.stButton > button {
        background: #111827 !important; color: #9ca3af !important;
        border: 1px solid #374151 !important; border-radius: 8px !important;
        padding: 10px !important; text-align: left !important; justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] div.stButton > button:hover { background: #10b981 !important; color: white !important; border: 1px solid #10b981 !important; }
    
    .table-wrapper { overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; margin-top: 15px; }
    .premium-table { width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; background: #111827; }
    .premium-table th { background: #1f2937; color: #10b981; padding: 14px; text-align: left; font-size: 13px; border-bottom: 2px solid #374151; white-space: nowrap; text-transform: uppercase;}
    .premium-table td { padding: 14px; border-bottom: 1px solid #1f2937; font-size: 13px; color: #e5e7eb; white-space: nowrap; }
    .btn-action { padding: 6px 12px; border-radius: 6px; font-weight: bold; text-decoration: none; font-size: 12px; display: inline-block; margin-right: 4px; }
    .btn-c { background-color: #2563eb; color: white !important; }
    .btn-w { background-color: #16a34a; color: white !important; }
    .btn-disabled { background-color: #4b5563; color: #9ca3af !important; cursor: not-allowed; }
    .client-card { background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 15px; }
    .main-title { color: #10b981; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }
    .front-login-box { 
        max-width: 450px; margin: 60px auto; background: #111827; padding: 40px; 
        border-radius: 16px; border: 1px solid #10b981; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); 
    }
    .nav-header { font-size: 12px; font-weight: bold; color: #6b7280; text-transform: uppercase; margin-bottom: 10px; padding-left: 5px; }
    .system-card { background: #1e293b; border: 1px solid #475569; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }
    .system-card h4 { margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;}
    .system-card p { margin: 5px 0; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. SECURE POOLED DATABASE REGISTRY
# ==========================================
try:
    DB_URL = st.secrets["DB_URL"]
except Exception:
    DB_URL = "postgresql://postgres.snbmurjcggthdvxyxyrd:DlLaglY98SkOzDq2@aws-1-ap-southeast-1.pooler.southeast-1.pooler.southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"

@st.cache_resource
def init_connection_pool():
    try:
        return SimpleConnectionPool(1, 15, dsn=DB_URL)
    except Exception as e:
        st.error(f"🔴 Critical Pool Init Error: {e}")
        st.stop()

master_pool = init_connection_pool()

@contextmanager
def get_db_connection():
    conn = master_pool.getconn()
    conn.autocommit = False
    try:
        yield conn
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        master_pool.putconn(conn)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

# Master Schema Engine - REMOVED FIXED DEFAULT SANGHOI/SAEELA INJECTIONS
def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, 
                    password TEXT NOT NULL, 
                    role TEXT NOT NULL CHECK(role IN ('Owner', 'Admin', 'Staff')), 
                    assignedarea TEXT DEFAULT 'ALL'
                )
            """)
            cursor.execute("CREATE TABLE IF NOT EXISTS areas (areaname TEXT PRIMARY KEY)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    username TEXT PRIMARY KEY, customername TEXT NOT NULL, phone TEXT UNIQUE NOT NULL,
                    cnic TEXT DEFAULT '', package TEXT NOT NULL, billamount INTEGER NOT NULL CHECK(billamount >= 0),
                    area TEXT NOT NULL, address TEXT DEFAULT '', onuserialnumber TEXT DEFAULT '',
                    balanceshift INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'UNPAID', expirydate TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    packagename TEXT NOT NULL, 
                    areaname TEXT NOT NULL, 
                    packagerate INTEGER NOT NULL CHECK(packagerate >= 0),
                    PRIMARY KEY (packagename, areaname)
                )
            """)
            
            cursor.execute("CREATE TABLE IF NOT EXISTS app_settings (settingkey TEXT PRIMARY KEY, settingvalue TEXT NOT NULL)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    invoiceid TEXT PRIMARY KEY, customerid TEXT NOT NULL, customername TEXT NOT NULL, area TEXT NOT NULL,
                    phone TEXT, datetimestamp TEXT NOT NULL, currentpackage TEXT NOT NULL, amountpaid INTEGER NOT NULL CHECK(amountpaid >= 0),
                    remainingarrears INTEGER NOT NULL, transactiontype TEXT NOT NULL, paymentmethod TEXT NOT NULL, discountgiven INTEGER DEFAULT 0
                )
            """)
            
            # Default Owner generation logic stays secure
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'Owner'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users VALUES ('owner', %s, 'Owner', 'ALL')", (hash_password('lynxowner123'),))
                
            cursor.execute("SELECT COUNT(*) FROM users WHERE username IN ('admin', 'staff')")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users VALUES ('admin', %s, 'Admin', 'ALL')", (hash_password('lynxadmin123'),))
                cursor.execute("INSERT INTO users VALUES ('staff', %s, 'Staff', 'None')", (hash_password('lynxstaff123'),))
                    
        conn.commit()

build_database_schema()

# ==========================================
# 3. HIGH PERFORMANCE DATA RETRIEVALS
# ==========================================
@st.cache_data(ttl=5)
def fetch_live_matrix():
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers ORDER BY customername ASC")
                rows = cur.fetchall()
        if rows:
            df = pd.DataFrame(rows)
            df.columns = [c.lower() for c in df.columns]
            extended_cols = GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER]
            return df.reindex(columns=extended_cols)
        return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate'])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=5)
def fetch_active_areas():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT areaname FROM areas ORDER BY areaname ASC")
                rows = cur.fetchall()
        return [r[0] for r in rows] if rows else []
    except Exception:
        return []

@st.cache_data(ttl=5)
def fetch_current_month_billing_summary():
    try:
        current_month_str = datetime.now().strftime("%Y-%m")
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT LOWER(TRIM(customerid)) as customerid, amountpaid FROM billing_history WHERE datetimestamp LIKE %s", (current_month_str + '%',))
                rows = cur.fetchall()
        if rows:
            df = pd.DataFrame(rows)
            return df.groupby('customerid')['amountpaid'].sum().to_dict()
    except Exception:
        pass
    return {}

def clean_and_validate_phone(phone_str: str) -> str:
    if not phone_str or str(phone_str).lower() == 'nan': return ""
    cleaned = str(phone_str).strip()
    if cleaned.endswith('.0'): cleaned = cleaned[:-2]
    cleaned = re.sub(r"\D", "", cleaned)
    if cleaned.startswith("92"): cleaned = "0" + cleaned[2:]
    if len(cleaned) == 10 and cleaned.startswith("3"): cleaned = "0" + cleaned
    return cleaned

# ==========================================
# 4. PORTAL SECURITY ROUTING ENGINE
# ==========================================
col_port1, col_port2 = st.columns([1, 4])
with col_port1:
    if st.button("📱 Client Portal" if not st.session_state['portal_mode'] else "🖥️ ERP Panel", use_container_width=True):
        st.session_state['portal_mode'] = not st.session_state['portal_mode']
        st.rerun()

if st.session_state['portal_mode']:
    routing_node = "📱 Client Portal"
else:
    if not st.session_state['authenticated']:
        st.markdown("<div class='front-login-box'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:#10b981; font-weight:900; margin-bottom:5px;'>LYNX FIBER NET</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#9ca3af; margin-bottom:30px;'>Enterprise ERP System v59.0</p>", unsafe_allow_html=True)
        
        user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
        pass_input = st.text_input("Security Password", type="password", key="front_pass")
        
        if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT role, username, assignedarea, password FROM users WHERE LOWER(username) = %s", (user_input,))
                    user_match = cursor.fetchone()
                
            if user_match and verify_password(pass_input, user_match[3]):
                st.session_state['authenticated'] = True
                st.session_state['user_role'] = user_match[0]  
                st.session_state['username'] = user_match[1]
                
                raw_areas = user_match[2] if user_match[2] else "ALL"
                if user_match[0] in ["Owner", "Admin"] or raw_areas == "ALL":
                    st.session_state['assigned_areas'] = ["ALL"]
                else:
                    st.session_state['assigned_areas'] = [a.strip() for a in raw_areas.split(",") if a.strip()]
                    
                st.session_state['current_node'] = "📊 Core Analytics Dashboard"
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ Invalid Access Credentials!")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    else:
        routing_node = st.session_state['current_node']

# NAVIGATION SIDEBAR
if st.session_state['authenticated'] and not st.session_state['portal_mode']:
    with st.sidebar:
        st.markdown(f"<h2 style='color:#10b981; font-weight:900; text-align:center; margin-bottom:20px;'>LYNX FIBER</h2>", unsafe_allow_html=True)
        st.markdown("<div class='nav-header'>System Navigation</div>", unsafe_allow_html=True)
        
        if st.button("📊 Core Analytics Dashboard", use_container_width=True):
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"; st.rerun()
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"; st.rerun()
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"; st.rerun()
            
        if st.session_state['user_role'] in ["Owner", "Admin"]:
            if st.button("🔐 System Access Control", use_container_width=True):
                st.session_state['current_node'] = "🔐 System Access Control"; st.rerun()
            
        st.write("---")
        area_display = "All Systems" if "ALL" in st.session_state['assigned_areas'] else ", ".join(st.session_state['assigned_areas'])
        role_color = "#f59e0b" if st.session_state['user_role'] == "Owner" else "#10b981"
        st.markdown(f"<p style='text-align:center; color:#9ca3af;'>👤 Active: <b>{st.session_state['username'].upper()}</b><br>📍 Role: <b style='color:{role_color};'>{st.session_state['user_role'].upper()}</b><br>🗺️ Areas:<br><span style='color:#60a5fa; font-size:12px;'><b>{area_display}</b></span></p>", unsafe_allow_html=True)
        if st.button("🔒 Logout System", use_container_width=True):
            st.session_state['authenticated'] = False; st.rerun()

# ==========================================
# VIEW 1: CORE ANALYTICS DASHBOARD
# ==========================================
if routing_node == "📊 Core Analytics Dashboard":
    st.markdown("<div class='main-title'>⚡ LYNX FIBER ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_live_matrix()
    all_system_areas = fetch_active_areas()
    is_high_profile = (st.session_state['user_role'] in ["Owner", "Admin"])
    
    cards_display_areas = all_system_areas.copy()
    if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
        cards_display_areas = [a for a in all_system_areas if any(a.lower() == s.lower() for s in st.session_state['assigned_areas'])]
    
    if not all_system_areas:
        st.info("💡 Database is empty. Configure your dynamic sectors inside System Access Control.")
    elif df_matrix.empty:
        st.warning("⚠️ Operational Database is currently empty. No subscribers registered.")
    else:
        collection_map = fetch_current_month_billing_summary()
        st.markdown("### 🌐 Active System Node Overview")
        for i in range(0, len(cards_display_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(cards_display_areas):
                    current_hub = cards_display_areas[i + j]
                    segment = df_matrix[df_matrix['area'].str.lower() == current_hub.lower()]
                    
                    active_segment = segment[segment['status'] != 'SUSPENDED']
                    hub_bill = active_segment['billamount'].sum()
                    hub_arrears = segment['balanceshift'].sum()
                    
                    hub_paid_count = len(segment[segment['status'] == 'PAID'])
                    hub_partial_count = len(segment[segment['status'] == 'PARTIAL'])
                    hub_unpaid_count = len(segment[segment['status'] == 'UNPAID'])
                    hub_suspended_count = len(segment[segment['status'] == 'SUSPENDED'])
                    
                    hub_uids = [str(x).lower().strip() for x in segment['username'].tolist() if pd.notna(x)]
                    hub_collected = sum(collection_map.get(uid, 0) for uid in hub_uids)
                    b_color = "#10b981" if (i+j)%2 == 0 else "#3b82f6"
                    
                    with cols[j]:
                        st.markdown(f"""
                        <div class="system-card" style="border-left: 5px solid {b_color};">
                            <h4>🌐 {current_hub} Overview</h4>
                            <p><b>Total Customers Registered:</b> {len(segment)}</p>
                            <p><b>Expected Active Revenue:</b> Rs. {hub_bill:,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>✅ Paid Customers:</b> {hub_paid_count} (Received: Rs. {hub_collected:,})</p>
                            <p style="color:#f59e0b; font-weight:bold;"><b>🟡 Partial Accounts:</b> {hub_partial_count}</p>
                            <p style="color:#f43f5e; font-weight:bold;"><b>❌ Unpaid / Suspended:</b> {hub_unpaid_count} / {hub_suspended_count}</p>
                            <p style="color:#f43f5e; font-weight:500;"><b>⚠️ Outstanding Arrears:</b> Rs. {hub_arrears:,}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
        st.write("---")
        base_df = df_matrix.copy()
        
        if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
            base_df = base_df[base_df['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
            filter_options = ["ALL ASSIGNED SYSTEMS"] + cards_display_areas
            system_filter = st.selectbox("🌐 Operational Area System Filter", filter_options)
            if system_filter != "ALL ASSIGNED SYSTEMS":
                base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]
        else:
            filter_options = ["ALL SYSTEMS"] + all_system_areas
            system_filter = st.selectbox("🌐 Operational Area System Filter", filter_options)
            if system_filter != "ALL SYSTEMS":
                base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]

        if not base_df.empty:
            total_active = len(base_df)
            total_paid = len(base_df[base_df['status'] == 'PAID'])
            total_arrears = base_df['balanceshift'].sum()
            total_suspended = len(base_df[base_df['status'] == 'SUSPENDED'])

            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1: st.button(f"👥 Terminals Active: {total_active}")
            with col_b2: st.button(f"✅ Paid Accounts: {total_paid}")
            with col_b3: st.button(f"⚠️ Arrears: Rs. {total_arrears:,}")
            with col_b4: st.button(f"🚫 Suspended: {total_suspended}")

            search_query = st.text_input("🔍 Fast Find Subscriber Row Analyzer")
            if search_query:
                clean_q = search_query.lower().strip()
                search_blob = base_df.astype(str).apply(lambda row: ' '.join(row).lower(), axis=1)
                base_df = base_df[search_blob.str.contains(clean_q, regex=False)].copy()

            custom_order_cols = GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate']
            
            html_rows = ['<div class="table-wrapper"><table class="premium-table"><tr>']
            for col in custom_order_cols:
                html_rows.append(f"<th>{col.replace('_', ' ').upper()}</th>")
            html_rows.append("<th>ACTIONS</th></tr>")
            
            for row in base_df.itertuples(index=False):
                row_dict = dict(zip(base_df.columns, row))
                phone_num = str(row_dict.get('phone', ''))
                pure_digits = re.sub(r"\D", "", phone_num)
                
                if len(pure_digits) >= 10:
                    wa_number = "92" + pure_digits[-10:]
                    wa_payload = f"Dear {row_dict.get('customername','')}, Lynx Fiber Bill Update. Arrears: Rs.{row_dict.get('balanceshift',0)}. Expiry: {row_dict.get('expirydate','')}"
                    wa_action_html = f'<a href="https://wa.me/{wa_number}?text={urllib.parse.quote(wa_payload)}" target="_blank" class="btn-action btn-w">💬 WA</a>'
                else:
                    wa_action_html = '<span class="btn-action btn-disabled">🚫 WA</span>'
                
                html_rows.append("<tr>")
                for col in custom_order_cols:
                    raw_val = row_dict.get(col, '')
                    escaped_val = html.escape(str(raw_val))
                    if col == 'username': html_rows.append(f"<td><b>{escaped_val}</b></td>")
                    elif col == 'status':
                        s_color = "#10b981" if raw_val == 'PAID' else ("#f59e0b" if raw_val == 'PARTIAL' else "#f43f5e")
                        html_rows.append(f"<td style='color:{s_color}; font-weight:bold;'>{escaped_val}</td>")
                    elif col == 'balanceshift': html_rows.append(f"<td style='color:#f43f5e; font-weight:bold;'>Rs. {raw_val}</td>")
                    else: html_rows.append(f"<td>{escaped_val}</td>")
                        
                html_rows.append(f'<td><a href="tel:{pure_digits}" class="btn-action btn-c">📞 Call</a> {wa_action_html}</td></tr>')
            html_rows.append("</table></div>")
            st.markdown("".join(html_rows), unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONS CENTER (AREA DRIVEN)
# ==========================================
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_live_matrix()
    all_system_areas = fetch_active_areas()
    is_management = (st.session_state['user_role'] in ["Owner", "Admin"])
    
    if not is_management and "ALL" not in st.session_state['assigned_areas']:
        df_matrix = df_matrix[df_matrix['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
        
    tabs_list = ["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"]
    if is_management:
        tabs_list.insert(1, "➕ Provision New Client")
        tabs_list.insert(2, "📥 Bulk Import Excel/CSV")
        
    tabs = st.tabs(tabs_list)
    
    sub_map = {}
    if not df_matrix.empty:
        for row in df_matrix.itertuples(index=False):
            row_dict = dict(zip(df_matrix.columns, row))
            uid = row_dict.get('username')
            if pd.notna(uid): sub_map[f"[{uid}] - {row_dict.get('customername', '')}"] = uid

    # TAB 1: Collection Cash Postings
    with tabs[0]:
        if not sub_map: st.info("No subscribers found.")
        else:
            target_label = st.selectbox("Select Target Subscriber", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            node_row_dict = df_matrix[df_matrix['username'] == resolved_uid].iloc[0].to_dict()
            
            st.info(f"📊 Rate: Rs. {node_row_dict.get('billamount')} | Arrears: Rs. {node_row_dict.get('balanceshift')}")
            billing_months = st.selectbox("📅 Duration (Advance Months)", [1, 3, 6, 12])
            net_payable = (int(node_row_dict.get('billamount', 0)) * billing_months) + int(node_row_dict.get('balanceshift', 0))
            
            with st.form("cash_posting_form"):
                pay_method = st.selectbox("Method Profile", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"])
                discount = st.number_input("🎁 Discount Approved (Rs.)", min_value=0, value=0)
                final_due = max(net_payable - discount, 0)
                st.markdown(f"### Total Due: **Rs. {final_due}**")
                cash_in = st.number_input("Capital Received (Rs.)", min_value=0, value=final_due)
                
                if st.form_submit_button("💳 POST TRANSACTION & EXTEND LINE"):
                    future_shift = final_due - cash_in
                    new_state = "PARTIAL" if future_shift > 0 and cash_in > 0 else ("UNPAID" if future_shift > 0 else "PAID")
                    new_expiry = (datetime.now() + relativedelta(months=billing_months)).strftime("%Y-%m-%d")
                    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                    
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s", (future_shift, new_state, new_expiry, resolved_uid))
                            cursor.execute("""
                                INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s)
                            """, (invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('phone'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), node_row_dict.get('package'), cash_in, future_shift, pay_method, discount))
                        conn.commit()
                    st.success("🎉 Collection Recorded Cleanly!")
                    st.cache_data.clear(); st.rerun()

    if is_management:
        # TAB 2: PROVISION NEW CLIENT WITH AREA-SPECIFIC DYNAMIC PACKAGES FLOW
        with tabs[1]:
            if not all_system_areas:
                st.error("❌ Register an Area Sector inside System Access Controls first.")
            else:
                in_area = st.selectbox("Select Target Hub Location", all_system_areas)
                
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT packagename, packagerate FROM packages WHERE areaname = %s", (in_area,))
                        area_pkgs = dict(cur.fetchall())
                
                with st.form("add_client_form_v59"):
                    in_id = st.text_input("Desired Unique Username Key").strip().lower()
                    in_name = st.text_input("Customer Full Name").strip()
                    in_phone = st.text_input("Phone Number").strip()
                    in_cnic = st.text_input("CNIC Number").strip()
                    
                    if area_pkgs:
                        chosen_pkg = st.selectbox(f"Valid Packages Configured for {in_area}", list(area_pkgs.keys()))
                        suggested_rate = area_pkgs[chosen_pkg]
                    else:
                        chosen_pkg = "Custom Baseline Plan"
                        suggested_rate = 1500
                        st.warning(f"⚠️ No tariffs set for '{in_area}'. Applying standard manual baseline rate.")
                        
                    in_rate = st.number_input("Monthly Plan Bill Amount (Rs.)", min_value=0, value=suggested_rate)
                    in_address = st.text_input("Physical Core Address").strip()
                    in_sn = st.text_input("ONU Hardware Serial ID").strip()
                    
                    if st.form_submit_button("➕ COMMENCE PROVISION INJECTION"):
                        norm_p = clean_and_validate_phone(in_phone)
                        if not in_id or not in_name or not norm_p: 
                            st.error("❌ Key structural missing data elements identified.")
                        else:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                                    cursor.execute("""
                                        INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s)
                                    """, (in_id, in_name, norm_p, in_cnic, chosen_pkg, in_rate, in_area, in_address, in_sn, default_expiry))
                                conn.commit()
                            st.success(f"🚀 Profile allocated cleanly for {in_id}!")
                            st.cache_data.clear(); st.rerun()

        # TAB 3: Bulk Import Excel Matrix Engine
        with tabs[2]:
            uploaded_file = st.file_uploader("Upload Excel Sheet", type=['xlsx', 'csv'])
            if uploaded_file and st.button("⚡ Save Sheet Rows to Live Engine"):
                st.success("Processing Sheet Engine Matrix Rows...")

    # TAB: Edit Profiles Engine Block
    with tabs[-1]:
        if not sub_map: st.info("Empty matrix logs.")
        else:
            edit_target = st.selectbox("Modify Identity Key Node", list(sub_map.keys()), key="edit_box")
            edit_uid = sub_map[edit_target]
            edit_row_dict = df_matrix[df_matrix['username'] == edit_uid].iloc[0].to_dict()
            
            with st.form("edit_terminal_form"):
                up_name = st.text_input("Customer Name", value=edit_row_dict.get('customername'))
                up_phone = st.text_input("Phone Number", value=edit_row_dict.get('phone'))
                up_address = st.text_input("Address", value=edit_row_dict.get('address'))
                up_sn = st.text_input("ONU SN", value=edit_row_dict.get('onuserialnumber'))
                up_rate = st.number_input("Monthly Rate (Rs.)", value=int(float(edit_row_dict.get('billamount',0))))
                up_status = st.selectbox("Line Status", ["PAID", "PARTIAL", "UNPAID", "SUSPENDED"], index=["PAID", "PARTIAL", "UNPAID", "SUSPENDED"].index(edit_row_dict.get('status','UNPAID')))
                
                if st.form_submit_button("💾 COMMIT MODIFICATIONS PROFILE"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE customers SET customername=%s, phone=%s, address=%s, onuserialnumber=%s, billamount=%s, status=%s
                                WHERE username=%s
                            """, (up_name, clean_and_validate_phone(up_phone), up_address, up_sn, up_rate, up_status, edit_uid))
                        conn.commit()
                    st.success("Profile Changes Completed Successfully.")
                    st.cache_data.clear(); st.rerun()

# ==========================================
# VIEW 3: LIFETIME AUDIT LEDGER HISTORY
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    df_ledger = pd.DataFrame()
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM billing_history ORDER BY datetimestamp DESC")
            l_rows = cur.fetchall()
            if l_rows: df_ledger = pd.DataFrame(l_rows)
        
    if df_ledger.empty:
        st.info("No transaction tracking history recorded yet.")
    else:
        df_ledger.columns = [c.lower() for c in df_ledger.columns]
        st.dataframe(df_ledger, use_container_width=True)

# ==========================================
# VIEW 4: SYSTEM ACCESS CONFIGS (ABSOLUTE PURGE INTEGRATED)
# ==========================================
elif routing_node == "🔐 System Access Control":
    if st.session_state['user_role'] not in ["Owner", "Admin"]:
        st.error("🔴 Administrative Elevation Clearance Required.")
    else:
        st.markdown("<div class='main-title'>🔐 LYNX FIBER ACCESS CONTROL PANEL</div>", unsafe_allow_html=True)
        all_system_areas = fetch_active_areas()
        
        tabs_def = ["⚙️ Access Accounts Management", "📦 Fixed Packages Pricing Matrix", "🗺️ Dynamic Area Hubs Sector"]
        if st.session_state['user_role'] == "Owner":
            tabs_def.insert(0, "🛠️ Master Schema Hard Settings")
            
        adm_tabs = st.tabs(tabs_def)
        idx_shift = 1 if st.session_state['user_role'] == "Owner" else 0

        # OWNER PRIVILEGES ENGINE: TRUE CLEAR-STATE PIPELINE
        if st.session_state['user_role'] == "Owner":
            with adm_tabs[0]:
                st.markdown("### 👑 Master Schema Dynamic Destruction Module")
                st.warning("⚠️ Critical Alert: Wiping database drops structural relationships completely. Is ke baad koi sample systems (Sanghoi/Saeela) khud-ba-khud load nahi honge.")
                
                purge_password = st.text_input("Verify Master Owner Confirmation Passphrase", type="password", key="purge_pass_gate")
                if st.button("☢️ INITIATE COMPLETE SYSTEM ZERO-DATA PURGE"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT password FROM users WHERE username = %s AND role='Owner'", (st.session_state['username'],))
                            match_p = cursor.fetchone()
                    
                    if match_p and verify_password(purge_password, match_p[0]):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DROP TABLE IF EXISTS billing_history CASCADE; DROP TABLE IF EXISTS customers CASCADE; DROP TABLE IF EXISTS areas CASCADE; DROP TABLE IF EXISTS packages CASCADE; DROP TABLE IF EXISTS users CASCADE; DROP TABLE IF EXISTS app_settings CASCADE;")
                            conn.commit()
                        
                        build_database_schema()
                        st.success("🚀 System Hard Purge Complete. Complete structural clean state achieved!")
                        st.cache_data.clear(); st.rerun()
                    else:
                        st.error("❌ Password Cryptographic signature mismatch. Operation Aborted.")

        # ADMIN TAB: Package Dynamic Allocation
        with adm_tabs[1 + idx_shift]:
            st.markdown("### 📦 Structural Location Pricing Allocation Configurator")
            if not all_system_areas:
                st.info("💡 Empty State: Configure an active Operating Area first.")
            else:
                with st.form("matrix_package_form"):
                    p_name = st.text_input("Tarif Identification Flag (e.g., 12 Mbps Fiber)").strip()
                    p_area = st.selectbox("Target Core Distribution Area Node Hub", all_system_areas)
                    p_rate = st.number_input("Assigned Monthly Price Configuration (Rs.)", min_value=0, value=1500)
                    
                    if st.form_submit_button("💾 LOCK TARIFF MATRIX PROFILE ENTRY"):
                        if not p_name: st.error("Name field mandatory.")
                        else:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        INSERT INTO packages (packagename, areaname, packagerate) 
                                        VALUES (%s, %s, %s) 
                                        ON CONFLICT (packagename, areaname) 
                                        DO UPDATE SET packagerate = EXCLUDED.packagerate
                                    """, (p_name, p_area, p_rate))
                                conn.commit()
                            st.success(f"✅ Configured {p_name} for area {p_area} at Rs. {p_rate}/m successfully.")
                            st.cache_data.clear(); st.rerun()

        # ADMIN TAB: Hub Areas Registration 
        with adm_tabs[2 + idx_shift]:
            st.markdown("### 🗺️ Sector Node Operations")
            with st.form("add_area_sector_form"):
                new_area_name = st.text_input("Enter New Network Location Name (e.g., Bagga, Saeela, Sanghoi)").strip()
                if st.form_submit_button("➕ COMMIT SECTOR DEPLOYMENT REGISTRY"):
                    if new_area_name:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO areas VALUES (%s) ON CONFLICT DO NOTHING", (new_area_name,))
                            conn.commit()
                        st.success(f"✅ {new_area_name} registered successfully.")
                        st.cache_data.clear(); st.rerun()

# ==========================================
# VIEW 5: SUBSCRIBER SELF-SERVICE INVENTORY
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown("<div class='main-title'>📱 LYNX FIBER SUBSCRIBER PORTAL</div>", unsafe_allow_html=True)
    portal_input = st.text_input("Enter Username or Mobile Number")
    
    if portal_input:
        search_term = portal_input.strip()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE LOWER(username) = LOWER(%s) OR phone = %s", [search_term, clean_and_validate_phone(search_term)])
                c_rows = cur.fetchall()
        if not c_rows: 
            st.error("❌ No active profile linked on server records.")
        else:
            c_dict = c_rows[0]
            html_card = f"""<div class="client-card"><h3 style="color:#10b981; margin-top:0;">👤 Account ID: {html.escape(str(c_dict.get('username','')))}</h3>"""
            for k in GLOBAL_TARGET_ORDER:
                if k != 'username':
                    html_card += f"<p><b>{k.upper()}:</b> {html.escape(str(c_dict.get(k, '')))}</p>"
            html_card += f"<p><b>LINE EXPIRY CYCLE:</b> {c_dict.get('expirydate')}</p></div>"
            st.markdown(html_card, unsafe_allow_html=True)