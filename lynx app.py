import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import urllib.parse
import uuid
import html
import re
import io
import os
from datetime import datetime, timedelta
from contextlib import contextmanager

# ReportLab import for PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ==========================================
# 1. PERMANENT SESSION ENGINE (WITH AREA BINDING)
# ==========================================
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'assigned_area' not in st.session_state:
    st.session_state['assigned_area'] = "ALL"
if 'current_node' not in st.session_state:
    st.session_state['current_node'] = "📊 Core Analytics Dashboard"
if 'dashboard_filter' not in st.session_state:
    st.session_state['dashboard_filter'] = "ALL"
if 'portal_mode' not in st.session_state:
    st.session_state['portal_mode'] = False
if 'column_order' not in st.session_state:
    st.session_state['column_order'] = []

# DEFINED TARGET STRUCTURE ORDER AS PER USER REQUIREMENT
GLOBAL_TARGET_ORDER = [
    "username",
    "customername",
    "phone",
    "cnic",
    "package",
    "billamount",
    "area",
    "address",
    "onuserialnumber"
]

# ==========================================
# 2. CORE THEME & PREMIUM MOBILE CSS ENGINE
# ==========================================
st.set_page_config(
    page_title="LYNX Fiber Enterprise ERP v54.1", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .stApp [data-testid="stHeader"] {
        background: transparent !important;
        height: 50px !important;
    }
    .stApp .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 1rem !important;
        max-width: 100% !important;
    }
    .stApp { background-color: #0b0f19; color: #f1f5f9; font-family: sans-serif; }
    [data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
    
    div[data-testid="stTextInput"] input, 
    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextArea"] textarea {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border: 2px solid #3b82f6 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stTextInput"] input[disabled],
    div[data-testid="stNumberInput"] input[disabled] {
        color: #4b5563 !important;
        background-color: #e5e7eb !important;
        border: 2px solid #9ca3af !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #000000 !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border: 2px solid #3b82f6 !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="select"] span, 
    div[data-baseweb="select"] div {
        color: #000000 !important;
    }
    ul[role="listbox"] li {
        color: #000000 !important;
        background-color: #ffffff !important;
        font-weight: 600 !important;
    }
    ul[role="listbox"] li:hover {
        background-color: #3b82f6 !important;
        color: #ffffff !important;
    }
    label, p, .stMarkdown div {
        color: #e5e7eb !important;
        font-weight: 500;
    }
    div.stButton > button, div.stFormSubmitButton > button {
        background: linear-gradient(135deg, #1e293b 0%, #111827 100%) !important;
        color: #3b82f6 !important;
        border: 2px solid #3b82f6 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        font-weight: bold !important;
        font-size: 15px !important;
        transition: all 0.3s ease;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important;
        width: 100% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        background: #3b82f6 !important;
        color: #ffffff !important;
        border: 2px solid #60a5fa !important;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
    }
    [data-testid="stSidebar"] div.stButton > button {
        background: #111827 !important;
        color: #9ca3af !important;
        border: 1px solid #374151 !important;
        border-radius: 8px !important;
        padding: 10px !important;
        text-align: left !important;
        justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] div.stButton > button:hover {
        background: #10b981 !important;
        color: white !important;
        border: 1px solid #10b981 !important;
    }
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
        max-width: 450px; 
        margin: 60px auto; 
        background: #111827; 
        padding: 40px; 
        border-radius: 16px; 
        border: 1px solid #10b981; 
        box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); 
    }
    .nav-header { font-size: 12px; font-weight: bold; color: #6b7280; text-transform: uppercase; margin-bottom: 10px; padding-left: 5px; }
    .system-card {
        background: #1e293b;
        border: 1px solid #475569;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        text-align: center;
    }
    .system-card h4 { margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;}
    .system-card p { margin: 5px 0; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. DIRECT DATABASE ENGINE (SUPABASE POSTGRES)
# ==========================================
try:
    DB_URL = st.secrets["DB_URL"]
except Exception:
    # UPDATED CONFIGURATION WITH YOUR NEW PASSWORD & PROPER CONNECTION POOLING PORT
    encoded_pass = urllib.parse.quote_plus("Sh0yZvfteqsQAqUc")
    DB_URL = f"postgresql://postgres.ehykfrzymkzlxzkhxlww:[YOUR-PASSWORD]@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=10)
        yield conn
    except Exception as e:
        st.error(f"🔴 Critical Database Connection Error: {e}")
        st.stop()
    finally:
        if conn is not None:
            conn.close()

def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS areas (
                    AreaName TEXT PRIMARY KEY
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    username TEXT PRIMARY KEY,
                    customername TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    cnic TEXT DEFAULT '',
                    package TEXT NOT NULL,
                    billamount INTEGER NOT NULL CHECK(billamount >= 0),
                    area TEXT NOT NULL,
                    address TEXT DEFAULT '',
                    onuserialnumber TEXT DEFAULT '',
                    balanceshift INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'UNPAID',
                    expirydate TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    PackageName TEXT PRIMARY KEY,
                    PackageRate INTEGER NOT NULL CHECK(PackageRate >= 0)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    SettingKey TEXT PRIMARY KEY,
                    SettingValue TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    Username TEXT PRIMARY KEY,
                    Password TEXT NOT NULL,
                    Role TEXT NOT NULL CHECK(Role IN ('Admin', 'Staff')),
                    AssignedArea TEXT DEFAULT 'ALL'
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    InvoiceID TEXT PRIMARY KEY,
                    CustomerID TEXT NOT NULL,
                    CustomerName TEXT NOT NULL,
                    Area TEXT NOT NULL,
                    Phone TEXT,
                    DateTimestamp TEXT NOT NULL,
                    CurrentPackage TEXT NOT NULL,
                    AmountPaid INTEGER NOT NULL CHECK(AmountPaid >= 0),
                    RemainingArrears INTEGER NOT NULL CHECK(RemainingArrears >= 0),
                    TransactionType TEXT NOT NULL,
                    PaymentMethod TEXT NOT NULL,
                    DiscountGiven INTEGER DEFAULT 0
                )
            """)
            
            cursor.execute("SELECT COUNT(*) FROM areas")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO areas VALUES ('Sanghoi System')")
                cursor.execute("INSERT INTO areas VALUES ('Saeela System')")
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE Role = 'Admin'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users VALUES ('admin', 'lynxadmin123', 'Admin', 'ALL')")
                cursor.execute("INSERT INTO users VALUES ('staff', 'lynxstaff123', 'Staff', 'Sanghoi System')")
            
            cursor.execute("SELECT COUNT(*) FROM packages")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO packages VALUES ('15 Mbps Fiber', 1500)")
                cursor.execute("INSERT INTO packages VALUES ('25 Mbps Fiber', 2000)")
                cursor.execute("INSERT INTO packages VALUES ('35 Mbps Fiber', 2500)")
                
            cursor.execute("SELECT COUNT(*) FROM customers")
            if cursor.fetchone()[0] == 0:
                default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                dummy_data = [
                    ('ghafoor01', 'Abdul Ghafoor', '03465803040', '37301-1102406-3', '15 Mbps Fiber', 1500, 'Sanghoi System', 'Sanghoi Main Bazar', 'HWTC5B11296B', 0, 'PAID', default_expiry),
                    ('khalid02', 'Abdul Khalid', '03404195974', '37301-5851107-9', '15 Mbps Fiber', 1500, 'Sanghoi System', 'Sanghoi Street 2', 'HWTCB2DA489C', 500, 'PARTIAL', default_expiry),
                    ('majeed03', 'Abdul Majeed', '03359565963', '37301-5718164-9', '15 Mbps Fiber', 1500, 'Sanghoi System', 'Near Grid Station', 'HWTC99AA211A', 1500, 'UNPAID', default_expiry)
                ]
                for row in dummy_data:
                    cursor.execute("""
                        INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING
                    """, row)
        conn.commit()

try:
    build_database_schema()
except Exception as e:
    st.error(f"Schema Builder Failed: {e}")

def get_db_columns():
    return GLOBAL_TARGET_ORDER

def save_column_order(order_list):
    val = ",".join([c.lower() for c in order_list])
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO app_settings (SettingKey, SettingValue) VALUES ('col_order', %s)
                ON CONFLICT (SettingKey) DO UPDATE SET SettingValue = EXCLUDED.SettingValue
            """, (val,))
        conn.commit()

def load_column_order():
    return GLOBAL_TARGET_ORDER

if not st.session_state['column_order']:
    st.session_state['column_order'] = GLOBAL_TARGET_ORDER

def fetch_live_matrix():
    try:
        with get_db_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM customers ORDER BY customername ASC", conn)
        if not df.empty:
            df.columns = [c.lower() for c in df.columns]
            extended_cols = GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER]
            return df.reindex(columns=extended_cols)
        return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate'])
    except Exception:
        return pd.DataFrame()

def fetch_system_packages():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM packages ORDER BY PackageRate ASC", conn)
    if not df.empty:
        df.columns = ['packagename', 'packagerate']
        return dict(zip(df['packagename'], df['packagerate']))
    return {"15 Mbps Fiber": 1500}

def fetch_active_areas():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT AreaName FROM areas ORDER BY AreaName ASC", conn)
    if not df.empty:
        return df.iloc[:, 0].tolist()
    return ["Sanghoi System", "Saeela System"]

def clean_and_validate_phone(phone_str: str) -> str:
    cleaned = re.sub(r"\D", "", str(phone_str))
    if cleaned.startswith("92"):
        cleaned = "0" + cleaned[2:]
    if len(cleaned) == 10 and cleaned.startswith("3"):
        cleaned = "0" + cleaned
    return cleaned

# ==========================================
# 4. ROUTING ENGINE CONFIGURATION & GLOBAL GATEWAY
# ==========================================
col_port1, col_port2 = st.columns([1, 4])

with col_port1:
    if st.button(
        "📱 Client Portal" if not st.session_state['portal_mode'] else "🖥️ ERP Panel",
        use_container_width=True
    ):
        st.session_state['portal_mode'] = not st.session_state['portal_mode']
        st.rerun()

show_client_portal = st.session_state['portal_mode']

if show_client_portal:
    routing_node = "📱 Client Portal"
else:
    if not st.session_state['authenticated']:
        st.markdown("<div class='front-login-box'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:#10b981; font-weight:900; margin-bottom:5px;'>LYNX FIBER NET</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#9ca3af; margin-bottom:30px;'>Enterprise ERP System v54.1 (Cloud Master Mode)</p>", unsafe_allow_html=True)
        
        user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
        pass_input = st.text_input("Security Password", type="password", key="front_pass")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT Role, Username, AssignedArea FROM users WHERE LOWER(Username) = %s AND Password = %s", (user_input, pass_input))
                    user_match = cursor.fetchone()
                
            if user_match:
                st.session_state['authenticated'] = True
                st.session_state['user_role'] = user_match[0]
                st.session_state['username'] = user_match[1]
                st.session_state['assigned_area'] = user_match[2] if user_match[2] else "ALL"
                st.session_state['current_node'] = "📊 Core Analytics Dashboard"
                st.rerun()
            else:
                st.error("❌ Invalid Access Credentials!")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    else:
        routing_node = st.session_state['current_node']

# ==========================================
# 5. NAVIGATION BAR (SIDEBAR)
# ==========================================
if st.session_state['authenticated'] and not st.session_state['portal_mode']:
    with st.sidebar:
        st.markdown(f"<h2 style='color:#10b981; font-weight:900; text-align:center; margin-bottom:20px;'>LYNX FIBER</h2>", unsafe_allow_html=True)
        st.markdown("<div class='nav-header'>System Navigation</div>", unsafe_allow_html=True)
        
        if st.button("📊 Core Analytics Dashboard", use_container_width=True):
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"
            st.rerun()
            
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"
            st.rerun()
            
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"
            st.rerun()
            
        if st.session_state['user_role'] == "Admin":
            if st.button("🔐 System Access Control", use_container_width=True):
                st.session_state['current_node'] = "🔐 System Access Control"
                st.rerun()
            
        st.write("---")
        area_display = "All Systems" if st.session_state['assigned_area'] == "ALL" else st.session_state['assigned_area']
        st.markdown(f"<p style='text-align:center; color:#9ca3af;'>👤 Active: <b>{st.session_state['username'].upper()}</b><br>📍 Area: {area_display}</p>", unsafe_allow_html=True)
        if st.button("🔒 Logout System", use_container_width=True):
            st.session_state['authenticated'] = False
            st.session_state['user_role'] = None
            st.session_state['assigned_area'] = "ALL"
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"
            st.rerun()

# ==========================================
# VIEW 1: CORE ANALYTICS DASHBOARD
# ==========================================
if routing_node == "📊 Core Analytics Dashboard":
    st.markdown("<div class='main-title'>⚡ LYNX FIBER ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_live_matrix()
    all_system_areas = fetch_active_areas()
    
    if df_matrix.empty:
        st.warning("⚠️ Operational Database is currently empty.")
    else:
        with get_db_connection() as conn:
            df_hist_calc = pd.read_sql_query("SELECT CustomerID, AmountPaid, DateTimestamp FROM billing_history", conn)
            if not df_hist_calc.empty:
                df_hist_calc.columns = ["customerid", "amountpaid", "datetimestamp"]
                df_hist_calc['customerid'] = df_hist_calc['customerid'].astype(str).str.lower().str.strip()
                df_hist_calc['datetimestamp'] = pd.to_datetime(df_hist_calc['datetimestamp'], errors='coerce')
                
                current_month_str = datetime.now().strftime("%Y-%m")
                df_hist_calc = df_hist_calc[df_hist_calc['datetimestamp'].dt.strftime("%Y-%m") == current_month_str]
            
        st.markdown("### 🌐 Active System Node Overview")
        for i in range(0, len(all_system_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(all_system_areas):
                    current_hub = all_system_areas[i + j]
                    segment = df_matrix[df_matrix['area'].str.lower() == current_hub.lower()]
                    
                    hub_bill = segment['billamount'].sum()
                    hub_arrears = segment['balanceshift'].sum()
                    
                    hub_paid_count = len(segment[segment['status'] == 'PAID'])
                    hub_partial_count = len(segment[segment['status'] == 'PARTIAL'])
                    hub_unpaid_count = len(segment[segment['status'] == 'UNPAID'])
                    hub_suspended_count = len(segment[segment['status'] == 'SUSPENDED'])
                    
                    hub_uids = [str(x).lower().strip() for x in segment['username'].tolist()]
                    
                    if not df_hist_calc.empty:
                        hub_collected = df_hist_calc[df_hist_calc['customerid'].isin(hub_uids)]['amountpaid'].sum()
                    else:
                        hub_collected = 0
                    
                    b_color = "#10b981" if (i+j)%2 == 0 else "#3b82f6"
                    
                    with cols[j]:
                        st.markdown(f"""
                        <div class="system-card" style="border-left: 5px solid {b_color};">
                            <h4>🌐 {current_hub} Overview</h4>
                            <p><b>Total Customers Registered:</b> {len(segment)}</p>
                            <p><b>Total Expected Revenue:</b> Rs. {hub_bill:,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>✅ Paid Customers:</b> {hub_paid_count} (Received This Month: Rs. {hub_collected:,})</p>
                            <p style="color:#f59e0b; font-weight:bold;"><b>🟡 Partial Accounts:</b> {hub_partial_count}</p>
                            <p style="color:#f43f5e; font-weight:bold;"><b>❌ Unpaid / Suspended:</b> {hub_unpaid_count} / {hub_suspended_count}</p>
                            <p style="color:#f43f5e; font-weight:500;"><b>⚠️ Outstanding Arrears Risk:</b> Rs. {hub_arrears:,}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
        st.write("---")
        
        base_df = df_matrix.copy()
        if st.session_state['assigned_area'] != "ALL":
            base_df = base_df[base_df['area'].str.lower() == st.session_state['assigned_area'].lower()]
            st.info(f"🔒 Secure Mode: Only showing data for **{st.session_state['assigned_area']}**")
        else:
            filter_options = ["ALL SYSTEMS"] + all_system_areas
            system_filter = st.selectbox("🌐 Operational Area System Filter", filter_options)
            if system_filter != "ALL SYSTEMS":
                base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]

        if base_df.empty: 
            st.warning("⚠️ No records found in this system segment.")
        else:
            total_active = len(base_df)
            total_paid = len(base_df[base_df['status'] == 'PAID'])
            total_arrears = base_df['balanceshift'].sum()
            total_suspended = len(base_df[base_df['status'] == 'SUSPENDED'])

            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                if st.button(f"👥 Terminals Active: {total_active}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "ALL"
                    st.rerun()
            with col_b2:
                if st.button(f"✅ Paid Accounts: {total_paid}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "PAID"
                    st.rerun()
            with col_b3:
                if st.button(f"⚠️ Arrears: Rs. {total_arrears:,}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "ARREARS"
                    st.rerun()
            with col_b4:
                if st.button(f"🚫 Suspended: {total_suspended}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "SUSPENDED"
                    st.rerun()

            analysis_df = base_df.copy()
            if st.session_state['dashboard_filter'] == "PAID":
                analysis_df = analysis_df[analysis_df['status'] == 'PAID']
            elif st.session_state['dashboard_filter'] == "ARREARS":
                analysis_df = analysis_df[analysis_df['balanceshift'] > 0]
            elif st.session_state['dashboard_filter'] == "SUSPENDED":
                analysis_df = analysis_df[analysis_df['status'] == 'SUSPENDED']

            search_query = st.text_input("🔍 Fast Find Subscriber (Structured Columns Row Analyzer)")
            if search_query:
                clean_q = search_query.lower().strip()
                search_blob = analysis_df.astype(str).apply(lambda row: ' '.join(row).lower(), axis=1)
                analysis_df = analysis_df[search_blob.str.contains(clean_q, regex=False)].copy()

            custom_order_cols = GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate']
            
            html_grid_code = """<div class="table-wrapper"><table class="premium-table"><tr>"""
            for col in custom_order_cols:
                html_grid_code += f"<th>{col.replace('_', ' ').upper()}</th>"
            html_grid_code += "<th>ACTIONS</th></tr>"
            
            for row in analysis_df.itertuples(index=False):
                row_dict = dict(zip(analysis_df.columns, row))
                
                phone_num = str(row_dict.get('phone', ''))
                pure_digits = re.sub(r"\D", "", phone_num)
                cust_name = row_dict.get('customername', '')
                curr_bal = row_dict.get('balanceshift', 0)
                exp_dt = row_dict.get('expirydate', '')
                
                if len(pure_digits) >= 10:
                    wa_number = "92" + pure_digits[-10:]
                    wa_payload = f"Dear {cust_name}, Lynx Fiber System Update. Outstanding Arrears: Rs.{curr_bal}. Please clear dues before expiry: {exp_dt}."
                    wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(wa_payload)}"
                    wa_action_html = f"""<a href="{wa_url}" target="_blank" class="btn-action btn-w">💬 WA</a>"""
                else:
                    wa_action_html = f"""<span class="btn-action btn-disabled">🚫 WA</span>"""
                
                html_grid_code += "<tr>"
                for col in custom_order_cols:
                    raw_val = row_dict.get(col, '')
                    escaped_val = html.escape(str(raw_val))
                    
                    if col in ['username']:
                        html_grid_code += f"<td><b>{escaped_val}</b></td>"
                    elif col in ['status']:
                        s_color = "#10b981" if raw_val == 'PAID' else ("#f59e0b" if raw_val == 'PARTIAL' else "#f43f5e")
                        html_grid_code += f"<td style='color:{s_color}; font-weight:bold;'>🟢 {escaped_val}</td>"
                    elif col in ['balanceshift']:
                        html_grid_code += f"<td style='color:#f43f5e; font-weight:bold;'>Rs. {escaped_val}</td>"
                    elif col in ['onuserialnumber']:
                        html_grid_code += f"<td style='color:#60a5fa; font-weight:bold;'>{escaped_val}</td>"
                    else:
                        html_grid_code += f"<td>{escaped_val}</td>"
                        
                html_grid_code += f"""<td><a href="tel:{pure_digits}" class="btn-action btn-c">📞 Call</a> {wa_action_html}</td></tr>"""
                
            st.markdown(html_grid_code + "</table></div>", unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONS CENTER
# ==========================================
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_live_matrix()
    pkg_dict = fetch_system_packages()
    all_system_areas = fetch_active_areas()
    is_admin = (st.session_state['user_role'] == "Admin")
    
    if st.session_state['assigned_area'] != "ALL":
        df_matrix = df_matrix[df_matrix['area'].str.lower() == st.session_state['assigned_area'].lower()]
        
    tabs_list = ["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"]
    if is_admin:
        tabs_list.insert(1, "➕ Provision New Client")
        tabs_list.insert(2, "📥 Bulk Import Excel/CSV")
        
    tabs = st.tabs(tabs_list)
    sub_map = {f"[{row.username}] - {row.customername} ({row.phone})" : row.username for row in df_matrix.itertuples(index=False)}
    
    with tabs[0]:
        if not sub_map: 
            st.info("No active subscriber nodes found for your system area.")
        else:
            target_label = st.selectbox("Select Target Subscriber Username", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            node_row = df_matrix[df_matrix['username'] == resolved_uid].iloc[0]
            
            st.info(f"📊 **Monthly Rate:** Rs. {node_row['billamount']} | **Arrears:** Rs. {node_row['balanceshift']}")
            
            billing_months = st.selectbox("📅 Select Billing Duration (Advance Months)", [1, 3, 6, 12])
            calculated_bill = int(node_row['billamount']) * billing_months
            gross_invoice_due = calculated_bill + int(node_row['balanceshift'])
            
            with st.form("cash_posting_form_v50"):
                pay_method = st.selectbox("Payment Method Profile", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"])
                discount_value = st.number_input("🎁 Discount Approved (Rs.)", min_value=0, value=0, disabled=not is_admin)
                
                net_payable_after_discount = max(gross_invoice_due - discount_value, 0)
                st.markdown(f"### 🧾 Net Payable (After Discount): **Rs. {net_payable_after_discount}**")
                
                cash_inflow = st.number_input("Liquid Capital Received (Rs.)", min_value=0, value=net_payable_after_discount)
                
                if st.form_submit_button("💳 POST TRANSACTION & EXTEND LINE", use_container_width=True):
                    future_shift = max(net_payable_after_discount - cash_inflow, 0)
                    
                    if cash_inflow <= 0:
                        new_state = "UNPAID"
                    elif future_shift > 0:
                        new_state = "PARTIAL"
                    else:
                        new_state = "PAID"
                        
                    new_expiry = (datetime.now() + timedelta(days=billing_months * 30)).strftime("%Y-%m-%d")
                    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                    
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(f"UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s", (future_shift, new_state, new_expiry, resolved_uid))
                            
                            cursor.execute("""
                                INSERT INTO billing_history (
                                    InvoiceID, CustomerID, CustomerName, Area, Phone, DateTimestamp, 
                                    CurrentPackage, AmountPaid, RemainingArrears, TransactionType, 
                                    PaymentMethod, DiscountGiven
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                invoice_uuid, 
                                resolved_uid, 
                                node_row['customername'], 
                                node_row['area'],
                                node_row['phone'],
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                                f"{node_row['package']} ({billing_months}M Advance)", 
                                cash_inflow, 
                                future_shift, 
                                "BILL_PAYMENT", 
                                pay_method, 
                                discount_value
                            ))
                    st.success(f"🎉 Transaction Posted Successfully! Status set to {new_state}")
                    st.rerun()

    current_tab_idx = 1
    if is_admin:
        with tabs[current_tab_idx]:
            with st.form("add_client_form_v50", clear_on_submit=True):
                in_id = (st.text_input("Desired Username Key") or "").strip()
                in_name = (st.text_input("Customer Name") or "").strip()
                in_phone = (st.text_input("Phone Number") or "").strip()
                in_cnic = (st.text_input("CNIC Number") or "").strip()
                chosen_pkg = st.selectbox("Select Package Plan Profile", list(pkg_dict.keys()))
                in_rate = st.number_input("Bill Amount Rate (Rs.)", min_value=0, value=pkg_dict[chosen_pkg])
                in_area = st.selectbox("Area Hub Location", all_system_areas)
                in_address = (st.text_input("Address") or "").strip()
                in_sn = (st.text_input("Onu SN (Serial)") or "").strip()
                
                if st.form_submit_button("➕ WRITE PROFILE TO DATABASE", use_container_width=True):
                    norm_p = clean_and_validate_phone(in_phone)
                    if not in_id or not in_name or not norm_p: st.error("❌ Required core fields missing!")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute(f"SELECT COUNT(*) FROM customers WHERE username = %s", (in_id,))
                                if cursor.fetchone()[0] > 0: st.error("❌ Username exists!")
                                else:
                                    default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                                    cursor.execute("""
                                        INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    """, (in_id, in_name, norm_p, in_cnic, chosen_pkg, in_rate, in_area, in_address, in_sn, 0, "UNPAID", default_expiry))
                        st.success("✅ Added Profile Successfully!")
                        st.rerun()
        current_tab_idx += 1

        with tabs[current_tab_idx]:
            st.markdown("### 📥 BULK EXCEL / CSV UPLOADER ENGINE")
            uploaded_file = st.file_uploader("Choose Excel or CSV File", type=['xlsx', 'csv'])
            if uploaded_file is not None:
                try:
                    import_df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
                    st.dataframe(import_df.head(10), use_container_width=True)
                    if st.button("⚡ Save All Sheet Data to Database", use_container_width=True):
                        success_count = 0
                        conflict_count = 0
                        default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                        
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                for index, row in import_df.iterrows():
                                    try:
                                        row_dict = {str(k).lower().strip(): v for k, v in row.to_dict().items()}
                                        
                                        uid = str(row_dict.get('username', '')).strip().lower()
                                        cname = str(row_dict.get('customername', row_dict.get('name', ''))).strip()
                                        cphone = clean_and_validate_phone(str(row_dict.get('phone', '')))
                                        
                                        if not uid or not cname: continue
                                        
                                        try:
                                            b_amt = int(float(row_dict.get('billamount', 1500)))
                                        except:
                                            b_amt = 1500
                                            
                                        cursor.execute("""
                                            INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s)
                                            ON CONFLICT (username) DO NOTHING
                                            RETURNING username
                                        """, (
                                            uid, cname, cphone, 
                                            str(row_dict.get('cnic', '')).strip(),
                                            str(row_dict.get('package', '15 Mbps Fiber')).strip(),
                                            b_amt,
                                            str(row_dict.get('area', 'Main Hub')).strip(),
                                            str(row_dict.get('address', '')).strip(),
                                            str(row_dict.get('onuserialnumber', row_dict.get('onu_sn', ''))).strip(),
                                            default_expiry
                                        ))
                                        
                                        inserted_status = cursor.fetchone()
                                        if inserted_status:
                                            success_count += 1
                                        else:
                                            conflict_count += 1
                                    except Exception:
                                        conflict_count += 1
                                        pass
                        st.success(f"🎉 Processed entries securely. Successfully Saved: {success_count} | Duplicates Skipped: {conflict_count}")
                        st.rerun()
                except Exception as e: st.error(f"❌ Error during file alignment mapping: {e}")
        current_tab_idx += 1

    with tabs[current_tab_idx]:
        st.markdown("### 🛠️ TERMINAL MANIPULATION ENGINE")
        if not sub_map: 
            st.info("No active terminals.")
        else:
            edit_target = st.selectbox("Select Target Username to Modify", list(sub_map.keys()), key="edit_tgt_box")
            edit_uid = sub_map[edit_target]
            edit_row = df_matrix[df_matrix['username'] == edit_uid].iloc[0]
            edit_row_dict = dict(zip(df_matrix.columns, edit_row))
            
            with st.form("edit_terminal_form_v50"):
                up_name = st.text_input("Update Customer Name", value=edit_row_dict.get('customername', ''))
                up_phone = st.text_input("Update Phone Number", value=edit_row_dict.get('phone', ''))
                up_cnic = st.text_input("Update CNIC Number", value=edit_row_dict.get('cnic', ''))
                up_address = st.text_input("Update Address", value=edit_row_dict.get('address', ''))
                up_sn = st.text_input("Update Onu SN", value=edit_row_dict.get('onuserialnumber', ''))
                
                current_area_name = edit_row_dict.get('area', all_system_areas[0] if all_system_areas else '')
                if current_area_name not in all_system_areas: all_system_areas.append(current_area_name)
                up_area = st.selectbox("System Area Hub", all_system_areas, index=all_system_areas.index(current_area_name))
                
                if is_admin:
                    current_pkg_name = edit_row_dict.get('package', '')
                    all_pkgs = list(pkg_dict.keys())
                    if current_pkg_name not in all_pkgs: all_pkgs.append(current_pkg_name)
                    
                    up_pkg = st.selectbox("Override Package Profile", all_pkgs, index=all_pkgs.index(current_pkg_name))
                    up_rate = st.number_input("Monthly Bill Rate (Rs.)", value=int(float(edit_row_dict.get('billamount', 0))))
                else:
                    st.text_input("Package Profile", value=edit_row_dict.get('package', ''), disabled=True)
                    st.number_input("Monthly Bill Rate (Rs.)", value=int(float(edit_row_dict.get('billamount', 0))), disabled=True)
                    up_pkg = edit_row_dict.get('package', '')
                    up_rate = int(float(edit_row_dict.get('billamount', 0)))
                
                up_arrears = st.number_input("Outstanding Balance (Arrears)", value=int(float(edit_row_dict.get('balanceshift', 0))), disabled=not is_admin)
                up_expiry = st.text_input("Expiry Date (YYYY-MM-DD)", value=edit_row_dict.get('expirydate', ''), disabled=not is_admin)
                up_status = st.selectbox("Line Status", ["PAID", "PARTIAL", "UNPAID", "SUSPENDED"], index=["PAID", "PARTIAL", "UNPAID", "SUSPENDED"].index(edit_row_dict.get('status', 'UNPAID')), disabled=not is_admin)
                
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    if st.form_submit_button("💾 SAVE EDITS", use_container_width=True):
                        norm_phone = clean_and_validate_phone(up_phone)
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE customers SET customername=%s, phone=%s, cnic=%s, package=%s, billamount=%s, area=%s, address=%s, onuserialnumber=%s, balanceshift=%s, expirydate=%s, status=%s
                                    WHERE username=%s
                                """, (up_name, norm_phone, up_cnic, up_pkg, up_rate, up_area, up_address, up_sn, up_arrears, up_expiry, up_status, edit_uid))
                        st.success("🎉 Changes Saved Successfully!")
                        st.rerun()
                with col_e2:
                    if st.form_submit_button("🚨 PERMANENTLY WIPE CLIENT", use_container_width=True, disabled=not is_admin):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor: 
                                cursor.execute("DELETE FROM customers WHERE username=%s", (edit_uid,))
                        st.warning("Client Wiped! History data remains safe.")
                        st.rerun()

# ==========================================
# VIEW 3: LIFETIME LEDGER HISTORY (FIXED DELETIONS)
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    
    all_system_areas = fetch_active_areas()
    with get_db_connection() as conn:
        df_ledger = pd.read_sql_query("SELECT * FROM billing_history ORDER BY DateTimestamp DESC", conn)
        
    if df_ledger.empty:
        st.info("No transaction tracking history recorded yet.")
    else:
        df_ledger.columns = [c.lower() for c in df_ledger.columns]
        
        df_ledger['datetime'] = pd.to_datetime(df_ledger['datetimestamp'], errors='coerce')
        df_ledger['Month'] = df_ledger['datetime'].dt.strftime('%Y-%m')
        df_ledger['Year'] = df_ledger['datetime'].dt.strftime('%Y')
        
        if st.session_state['assigned_area'] != "ALL":
            df_ledger = df_ledger[df_ledger['area'].str.lower() == st.session_state['assigned_area'].lower()]
            st.info(f"🔒 Secure Mode: Only showing logs for **{st.session_state['assigned_area']}**")
            sel_area = st.session_state['assigned_area']
        else:
            filter_options = ["ALL AREAS"] + all_system_areas
            sel_area = st.selectbox("🌐 Choose Target Area Filter", filter_options)
            
        filtered_ledger = df_ledger.copy()
        if sel_area != "ALL AREAS" and st.session_state['assigned_area'] == "ALL":
            filtered_ledger = filtered_ledger[filtered_ledger['area'].str.lower() == sel_area.lower()]
            
        st.markdown("### 📊 Enterprise Financial Graphs Overview")
        col_g1, col_g2 = st.columns(2)
        
        clean_graph_ledger = filtered_ledger.dropna(subset=['invoiceid']).drop_duplicates(subset=['invoiceid'])
        
        with col_g1:
            st.markdown("<h4 style='text-align:center; color:#3b82f6;'>📅 Monthly Collection Breakdown</h4>", unsafe_allow_html=True)
            monthly_data = clean_graph_ledger.groupby('Month')['amountpaid'].sum().reset_index()
            if not monthly_data.empty:
                st.bar_chart(data=monthly_data, x='Month', y='amountpaid', color="#3b82f6", use_container_width=True)
            else:
                st.info("No month data available.")
                
        with col_g2:
            st.markdown("<h4 style='text-align:center; color:#10b981;'>🏦 Annually Collection Volume</h4>", unsafe_allow_html=True)
            yearly_data = clean_graph_ledger.groupby('Year')['amountpaid'].sum().reset_index()
            if not yearly_data.empty:
                st.bar_chart(data=yearly_data, x='Year', y='amountpaid', color="#10b981", use_container_width=True)
            else:
                st.info("No annual records parsed.")
                
        st.write("---")
        st.markdown("### 📋 Complete Master Ledger Sheet (Excel Row View)")
        
        excel_sheet_df = filtered_ledger[['invoiceid', 'customerid', 'customername', 'area', 'datetimestamp', 'currentpackage', 'discountgiven', 'amountpaid', 'paymentmethod', 'remainingarrears']]
        excel_sheet_df.columns = ['Invoice ID', 'Username Key', 'Subscriber Name', 'Hub Area', 'Timestamp Log', 'Package Detail', 'Discount (Rs)', 'Amount Received (Rs)', 'Gateway Channel', 'Remaining Arrears Account']
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            excel_sheet_df.to_excel(writer, index=False, sheet_name='Ledger_History')
        buffer.seek(0)
        
        st.download_button(
            label="📥 Export Full Audit Trail to Excel Sheet (.xlsx)",
            data=buffer,
            file_name=f"LYNX_Master_Ledger_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.dataframe(excel_sheet_df, use_container_width=True, hide_index=True)

# ==========================================
# VIEW 4: SYSTEM ACCESS CONTROL (MASTER CONFIG)
# ==========================================
elif routing_node == "🔐 System Access Control":
    if st.session_state['user_role'] != "Admin":
        st.error("🔴 Access Denied!")
    else:
        st.markdown("<div class='main-title'>🔐 LYNX FIBER ACCESS CONTROL PANEL</div>", unsafe_allow_html=True)
        
        all_system_areas = fetch_active_areas()
        adm_tab1, adm_tab2, adm_tab3, adm_tab4, adm_tab5 = st.tabs([
            "🛠️ Master Schema Settings", "⚙️ Access Accounts", "📦 Fixed Packages", "🗺️ Dynamic Area Hubs", "👤 Security Admin"
        ])
        
        with adm_tab1:
            st.markdown("### 👑 Master Database Schema Engineering")
            st.markdown("#### 🚨 Database Structural Purge Engine")
            st.info("Agar aapka schema length aage piche hai, to is button ko dabayein. Purana data backup ho kar new 2026 scheme me safely update ho jayega.")
            
            if st.button("🚨 FORCE CLEAN & PURGE LIVE DATABASE STRUCTURE", use_container_width=True):
                try:
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("DROP TABLE IF EXISTS customers_backup CASCADE")
                            cursor.execute("CREATE TABLE IF NOT EXISTS customers_backup AS SELECT * FROM customers")
                            cursor.execute("DROP TABLE IF EXISTS customers CASCADE")
                            cursor.execute("""
                                CREATE TABLE customers (
                                    username TEXT PRIMARY KEY,
                                    customername TEXT NOT NULL,
                                    phone TEXT UNIQUE NOT NULL,
                                    cnic TEXT DEFAULT '',
                                    package TEXT NOT NULL,
                                    billamount INTEGER NOT NULL DEFAULT 1500,
                                    area TEXT NOT NULL,
                                    address TEXT DEFAULT '',
                                    onuserialnumber TEXT DEFAULT '',
                                    balanceshift INTEGER NOT NULL DEFAULT 0,
                                    status TEXT NOT NULL DEFAULT 'UNPAID',
                                    expirydate TEXT NOT NULL,
                                    installationdate TEXT DEFAULT '',
                                    lastpaymentdate TEXT DEFAULT ''
                                )
                            """)
                            default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                            dummy_data = [
                                ('ghafoor01', 'Abdul Ghafoor', '03465803040', '37301-1102406-3', '15 Mbps Fiber', 1500, 'Sanghoi System', 'Sanghoi Main Bazar', 'HWTC5B11296B', 0, 'PAID', default_expiry, '', '')
                            ]
                            for row in dummy_data:
                                cursor.execute("""
                                    INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate, installationdate, lastpaymentdate)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, row)
                    st.success("🚀 System fully rebuilt successfully! Safe backup snapshot preserved inside 'customers_backup' table.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Sync Failure Engine: {ex}")

            st.write("---")
            st.markdown("#### 🔄 Fixed Columns Layout Rule Mapped across ERP:")
            st.write(" ➡️ ".join([f"`{c.upper()}`" for c in GLOBAL_TARGET_ORDER]))
            st.success("🔒 System Sequence Mismatch Protection is fully locked on target columns hierarchy.")

        with adm_tab2:
            with st.form("new_admin_form"):
                st.markdown("### 🔐 Create New Admin Account")
                new_admin_user = st.text_input("New Admin Username").strip().lower()
                new_admin_pass = st.text_input("New Admin Password", type="password").strip()

                if st.form_submit_button("➕ Create Admin", use_container_width=True):
                    if not new_admin_user or not new_admin_pass: st.error("❌ Entries blank.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                try:
                                    cursor.execute("INSERT INTO users VALUES (%s, %s, 'Admin', 'ALL')", (new_admin_user, new_admin_pass))
                                    st.success(f"✅ New Admin '{new_admin_user}' created successfully!")
                                except psycopg2.IntegrityError: st.error("❌ Username already exists!")

            st.write("---")
            st.markdown("### 👥 Create New Staff Account with Area Lock")
            with st.form("new_staff_form_v50"):
                new_user = st.text_input("New Staff Username").strip().lower()
                new_pass = st.text_input("New Staff Password", type="password").strip()
                new_area_lock = st.selectbox("Assign & Lock System Area", all_system_areas)
                
                if st.form_submit_button("🚀 Add Staff Account & Lock Area", use_container_width=True):
                    if not new_user or not new_pass: st.error("❌ Blank entries not allowed.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                try:
                                    cursor.execute("INSERT INTO users VALUES (%s, %s, 'Staff', %s)", (new_user, new_pass, new_area_lock))
                                    st.success(f"✅ Staff '{new_user}' Created!")
                                except psycopg2.IntegrityError: st.error("❌ Username already exists!")
                                
            st.write("---")
            st.markdown("### 📋 All Registered Accounts")
            with get_db_connection() as conn:
                users_df = pd.read_sql_query("SELECT Username, Password, Role, AssignedArea FROM users", conn)
            st.dataframe(users_df, use_container_width=True, hide_index=True)

        with adm_tab3:
            st.markdown("### ➕ Add or Update Fixed Network Packages")
            with st.form("add_package_form"):
                p_name = st.text_input("Package Profile Name").strip()
                p_rate = st.number_input("Fixed Monthly Rate (Rs.)", min_value=0, value=1500)
                if st.form_submit_button("💾 Save Fixed Package to System", use_container_width=True):
                    if not p_name: st.error("❌ Package name cannot be empty.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO packages VALUES (%s, %s) ON CONFLICT (PackageName) DO UPDATE SET PackageRate = EXCLUDED.PackageRate", (p_name, p_rate))
                        st.success(f"✅ Saved Profile Status")
                        st.rerun()
            
            st.write("---")
            pkg_dict_live = fetch_system_packages()
            pkg_df = pd.DataFrame(list(pkg_dict_live.items()), columns=["Package Name", "Fixed Rate (Rs.)"])
            st.dataframe(pkg_df, use_container_width=True, hide_index=True)

        with adm_tab4:
            st.markdown("### 🗺️ ADD NEW SYSTEM HUB AREA")
            with st.form("dynamic_add_area_form"):
                fresh_area_name = st.text_input("Enter New Area Name").strip()
                if st.form_submit_button("➕ REGISTER NEW AREA NODE", use_container_width=True):
                    if not fresh_area_name: st.error("❌ Area blank!")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                try:
                                    cursor.execute("INSERT INTO areas VALUES (%s)", (fresh_area_name,))
                                    st.success(f"🎉 System Hub Mapped Integrated!")
                                    st.rerun()
                                except psycopg2.IntegrityError: st.error("❌ Exists!")
                                
            st.write("---")
            area_matrix_live = fetch_active_areas()
            st.dataframe(pd.DataFrame(area_matrix_live, columns=["Registered System Area Name"]), use_container_width=True, hide_index=True)

        with adm_tab5:
            st.markdown("### 👤 Update Admin Security Profiling")
            with st.form("admin_profile_form"):
                current_admin_user = st.session_state['username']
                up_admin_user = st.text_input("Change Admin Username", value=current_admin_user).strip().lower()
                up_admin_pass = st.text_input("New Admin Password", type="password").strip()
                
                if st.form_submit_button("🔒 Securely Update Admin Profile", use_container_width=True):
                    if not up_admin_user or not up_admin_pass: st.error("❌ Credentials blank.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DELETE FROM users WHERE Username = %s", (current_admin_user,))
                                cursor.execute("INSERT INTO users VALUES (%s, %s, 'Admin', 'ALL')", (up_admin_user, up_admin_pass))
                        st.success("Updated Successfully!")
                        st.session_state['authenticated'] = False
                        st.rerun()

# ==========================================
# VIEW 5: CLIENT PORTAL (STRICT MATCH ENGINE)
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown("<div class='main-title'>📱 LYNX FIBER SUBSCRIBER PORTAL</div>", unsafe_allow_html=True)
    
    portal_input = st.text_input("Enter Username, Registered Mobile Number, or CNIC")
    
    if portal_input:
        search_term = portal_input.strip()
        clean_phone = clean_and_validate_phone(search_term)
        
        with get_db_connection() as conn:
            query = "SELECT * FROM customers WHERE LOWER(username) = LOWER(%s) OR phone = %s OR cnic = %s"
            client = pd.read_sql_query(query, conn, params=[search_term, clean_phone, search_term])
            
        if client.empty: 
            st.error("❌ No registered record found matching your input. Please check your details.")
        else:
            client.columns = [c.lower() for c in client.columns]
            c_dict = client.iloc[0].to_dict()
            
            uid_val = c_dict.get('username', '')
            cname_val = c_dict.get('customername', '')
            
            html_card = f"""<div class="client-card"><h3 style="color:#10b981; margin-top:0;">👤 Account Username: {html.escape(str(uid_val))}</h3><p><b>Customer Name:</b> {html.escape(str(cname_val))}</p>"""
            
            for k in GLOBAL_TARGET_ORDER:
                if k not in ['username', 'customername']:
                    v = c_dict.get(k, '')
                    html_card += f"<p><b>{k.replace('_',' ').upper()}:</b> {html.escape(str(v))}</p>"
                    
            html_card += "</div>"
            st.markdown(html_card, unsafe_allow_html=True)