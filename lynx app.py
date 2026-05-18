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

# ==========================================
# 2. CORE THEME & PREMIUM MOBILE CSS ENGINE
# ==========================================
st.set_page_config(
    page_title="LYNX Fiber Enterprise ERP v54.0", 
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
    encoded_pass = urllib.parse.quote_plus("cMSUKBCwAy6dyGPr")
    DB_URL = f"postgresql://postgres.ehykfrzymkzlxzkhxlww:{encoded_pass}@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=10)
        yield conn
    except Exception as e:
        st.error(f"🔴 Critical Database Connection Error: {e}")
        st.info("💡 Pro-Tip: Make sure your internet connection is live and your Supabase database is active.")
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
                    customerid TEXT PRIMARY KEY,
                    customername TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    area TEXT NOT NULL,
                    package TEXT NOT NULL,
                    billamount INTEGER NOT NULL CHECK(billamount >= 0),
                    balanceshift INTEGER NOT NULL CHECK(balanceshift >= 0),
                    status TEXT NOT NULL CHECK(status IN ('PAID','PARTIAL','UNPAID','SUSPENDED')),
                    expirydate TEXT NOT NULL,
                    cnic TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    onu_sn TEXT DEFAULT ''
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
            
            # Safe structural verification
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customers' AND column_name='cnic'")
            if not cursor.fetchone(): cursor.execute("ALTER TABLE customers ADD COLUMN cnic TEXT DEFAULT ''")
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customers' AND column_name='address'")
            if not cursor.fetchone(): cursor.execute("ALTER TABLE customers ADD COLUMN address TEXT DEFAULT ''")
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customers' AND column_name='onu_sn'")
            if not cursor.fetchone(): cursor.execute("ALTER TABLE customers ADD COLUMN onu_sn TEXT DEFAULT ''")
                
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
                dummy_data = [
                    ('37301-1102406-3', 'Abdul Ghafoor', '03465803040', 'Sanghoi System', '15 Mbps Fiber', 1500, 0, 'PAID', '2026-06-01', '37301-1102406-3', 'Sanghoi Main Bazar', 'HWTC5B11296B'),
                    ('37301-5851107-9', 'Abdul Khalid', '03404195974', 'Sanghoi System', '15 Mbps Fiber', 1500, 500, 'PARTIAL', '2026-06-01', '37301-5851107-9', 'Sanghoi Street 2', 'HWTCB2DA489C'),
                    ('37301-5718164-9', 'Abdul Majeed', '03359565963', 'Sanghoi System', '15 Mbps Fiber', 1500, 1500, 'UNPAID', '2026-06-01', '37301-5718164-9', 'Near Grid Station', 'HWTC99AA211A'),
                    ('37301-0142613-5', 'Abdul Raheem', '03466104026', 'Saeela System', '15 Mbps Fiber', 1500, 0, 'PAID', '2026-06-01', '37301-0142613-5', 'Saeela Chowk', 'HWTC88BB334C'),
                    ('37301-2238514-0', 'Abdul Razzaq 2', '03216362487', 'Saeela System', '15 Mbps Fiber', 1500, 1500, 'UNPAID', '2026-06-01', '37301-2238514-0', 'Saeela North', 'HWTC77CC445E'),
                ]
                for row in dummy_data:
                    cursor.execute("""
                        INSERT INTO customers (customerid, customername, phone, area, package, billamount, balanceshift, status, expirydate, cnic, address, onu_sn)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (customerid) DO NOTHING
                    """, row)
                
                cursor.execute("""
                    INSERT INTO billing_history (InvoiceID, CustomerID, CustomerName, DateTimestamp, CurrentPackage, AmountPaid, RemainingArrears, TransactionType, PaymentMethod, DiscountGiven)
                    VALUES ('INV-0010A', '37301-1102406-3', 'Abdul Ghafoor', '2026-05-15 10:00:00', '15 Mbps Fiber', 1500, 0, 'BILL_PAYMENT', 'CASH', 0)
                    ON CONFLICT (InvoiceID) DO NOTHING
                """)
        conn.commit()

try:
    build_database_schema()
except Exception as e:
    st.error(f"Initial Schema Builder Failed: {e}")

def get_db_columns():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='customers'")
            cols = [r[0].lower() for r in cursor.fetchall()]
    return cols

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
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT SettingValue FROM app_settings WHERE SettingKey='col_order'")
            res = cursor.fetchone()
    if res and res[0]:
        return [c.lower() for c in res[0].split(",") if c]
    return get_db_columns()

# Initial Order Initialization
if not st.session_state['column_order']:
    st.session_state['column_order'] = load_column_order()

def fetch_live_matrix():
    try:
        current_cols = get_db_columns()
        with get_db_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM customers ORDER BY customername ASC", conn)
        if not df.empty:
            df.columns = [c.lower() for c in df.columns]
            saved_order = load_column_order()
            valid_order = [c for c in saved_order if c in df.columns] + [c for c in df.columns if c not in saved_order]
            return df[valid_order]
        return pd.DataFrame(columns=current_cols)
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
        st.markdown("<p style='text-align:center; color:#9ca3af; margin-bottom:30px;'>Enterprise ERP System v54.0 (Cloud Master Mode)</p>", unsafe_allow_html=True)
        
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
            df_hist_calc = pd.read_sql_query("SELECT customerid, amountpaid FROM billing_history", conn)
            if not df_hist_calc.empty:
                df_hist_calc.columns = ["customerid", "amountpaid"]
            
        st.markdown("### 🌐 Active System Node Overview")
        for i in range(0, len(all_system_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(all_system_areas):
                    current_hub = all_system_areas[i + j]
                    segment = df_matrix[df_matrix['area'] == current_hub]
                    
                    hub_bill = segment['billamount'].sum()
                    hub_arrears = segment['balanceshift'].sum()
                    
                    hub_paid_count = len(segment[segment['status'] == 'PAID'])
                    hub_unpaid_count = len(segment[segment['status'].isin(['UNPAID', 'PARTIAL', 'SUSPENDED'])])
                    
                    hub_uids = segment['customerid'].tolist()
                    hub_collected = df_hist_calc[df_hist_calc['customerid'].isin(hub_uids)]['amountpaid'].sum() if not df_hist_calc.empty else 0
                    
                    b_color = "#10b981" if (i+j)%2 == 0 else "#3b82f6"
                    
                    with cols[j]:
                        st.markdown(f"""
                        <div class="system-card" style="border-left: 5px solid {b_color};">
                            <h4>🌐 {current_hub} Overview</h4>
                            <p><b>Total Customers Registered:</b> {len(segment)}</p>
                            <p><b>Total Expected Revenue:</b> Rs. {hub_bill:,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>✅ Paid Customers:</b> {hub_paid_count} (Received: Rs. {hub_collected:,})</p>
                            <p style="color:#f43f5e; font-weight:bold;"><b>❌ Unpaid/Arrears Customers:</b> {hub_unpaid_count}</p>
                            <p style="color:#f43f5e; font-weight:500;"><b>⚠️ Outstanding Arrears Risk:</b> Rs. {hub_arrears:,}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
        st.write("---")
        
        base_df = df_matrix.copy()
        if st.session_state['assigned_area'] != "ALL":
            base_df = base_df[base_df['area'] == st.session_state['assigned_area']]
            st.info(f"🔒 Secure Mode: Only showing data for **{st.session_state['assigned_area']}**")
        else:
            filter_options = ["ALL SYSTEMS"] + all_system_areas
            system_filter = st.selectbox("🌐 Operational Area System Filter", filter_options)
            if system_filter != "ALL SYSTEMS":
                base_df = base_df[base_df['area'] == system_filter]

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

            search_query = st.text_input("🔍 Fast Find Subscriber (Dynamic Columns Search Enabled)")
            if search_query:
                clean_q = search_query.lower().strip()
                search_blob = analysis_df.astype(str).apply(lambda row: ' '.join(row).lower(), axis=1)
                analysis_df = analysis_df[search_blob.str.contains(clean_q, regex=False)].copy()

            custom_order_cols = load_column_order()
            
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
                    
                    if col in ['customerid', 'username']:
                        html_grid_code += f"<td><b>{escaped_val}</b></td>"
                    elif col in ['status']:
                        s_color = "#10b981" if raw_val == 'PAID' else ("#f59e0b" if raw_val == 'PARTIAL' else "#f43f5e")
                        html_grid_code += f"<td style='color:{s_color}; font-weight:bold;'>🟢 {escaped_val}</td>"
                    elif col in ['balanceshift', 'arrears']:
                        html_grid_code += f"<td style='color:#f43f5e; font-weight:bold;'>Rs. {escaped_val}</td>"
                    elif col in ['onu_sn', 'sn']:
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
        df_matrix = df_matrix[df_matrix['area'] == st.session_state['assigned_area']]
        
    tabs_list = ["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"]
    if is_admin:
        tabs_list.insert(1, "➕ Provision New Client")
        tabs_list.insert(2, "📥 Bulk Import Excel/CSV")
        
    tabs = st.tabs(tabs_list)
    sub_map = {f"[{row.customerid}] - {row.customername} ({row.phone})" : row.customerid for row in df_matrix.itertuples(index=False)}
    
    with tabs[0]:
        if not sub_map: 
            st.info("No active subscriber nodes found for your system area.")
        else:
            target_label = st.selectbox("Select Target Subscriber Username", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            node_row = df_matrix[df_matrix['customerid'] == resolved_uid].iloc[0]
            
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
                    new_state = "UNPAID" if cash_inflow <= 0 else ("PAID" if future_shift == 0 else "PARTIAL")
                    new_expiry = (datetime.now() + timedelta(days=billing_months * 30)).strftime("%Y-%m-%d")
                    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                    
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(f"UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE customerid = %s", (future_shift, new_state, new_expiry, resolved_uid))
                            cursor.execute("""
                                INSERT INTO billing_history (InvoiceID, CustomerID, CustomerName, DateTimestamp, CurrentPackage, AmountPaid, RemainingArrears, TransactionType, PaymentMethod, DiscountGiven)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (invoice_uuid, resolved_uid, node_row['customername'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{node_row['package']} ({billing_months}M Advance)", cash_inflow, future_shift, "BILL_PAYMENT", pay_method, discount_value))
                    st.success(f"🎉 Transaction Posted Successfully!")
                    st.rerun()

    current_tab_idx = 1
    if is_admin:
        with tabs[current_tab_idx]:
            with st.form("add_client_form_v50", clear_on_submit=True):
                in_id = (st.text_input("Desired Username/CustomerID") or "").strip()
                in_name = (st.text_input("Full Owner Name") or "").strip()
                in_phone = (st.text_input("Mobile Contact") or "").strip()
                in_area = st.selectbox("System Area Hub", all_system_areas)
                chosen_pkg = st.selectbox("Select Bandwidth Plan Profile", list(pkg_dict.keys()))
                in_rate = st.number_input("Monthly Rate (Rs.)", min_value=0, value=pkg_dict[chosen_pkg])
                
                dynamic_inputs = {}
                all_current_cols = get_db_columns()
                core_fields = ['customerid', 'customername', 'phone', 'area', 'package', 'billamount', 'balanceshift', 'status', 'expirydate']
                
                for col in all_current_cols:
                    if col not in core_fields:
                        dynamic_inputs[col] = st.text_input(f"Enter {col.upper()} metadata field").strip()
                
                if st.form_submit_button("➕ WRITE PROFILE TO DATABASE", use_container_width=True):
                    norm_p = clean_and_validate_phone(in_phone)
                    if not in_id or not in_name or not norm_p: st.error("❌ Required core fields missing!")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute(f"SELECT COUNT(*) FROM customers WHERE customerid = %s", (in_id,))
                                if cursor.fetchone()[0] > 0: st.error("❌ Username exists!")
                                else:
                                    default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                                    
                                    insert_cols = ['customerid', 'customername', 'phone', 'area', 'package', 'billamount', 'balanceshift', 'status', 'expirydate'] + list(dynamic_inputs.keys())
                                    insert_vals = [in_id, in_name, norm_p, in_area, chosen_pkg, in_rate, 0, "UNPAID", default_expiry] + list(dynamic_inputs.values())
                                    
                                    placeholders = ", ".join(["%s"] * len(insert_vals))
                                    columns_str = ", ".join(insert_cols)
                                    
                                    cursor.execute(f"INSERT INTO customers ({columns_str}) VALUES ({placeholders})", insert_vals)
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
                        default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                        
                        db_cols = get_db_columns()
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                for index, row in import_df.iterrows():
                                    try:
                                        row_dict = {str(k).lower().strip(): v for k, v in row.to_dict().items()}
                                        
                                        cid = str(row_dict.get('customerid', '')).strip()
                                        cname = str(row_dict.get('customername', '')).strip()
                                        cphone = clean_and_validate_phone(str(row_dict.get('phone', '')))
                                        
                                        if not cid or not cname: continue
                                        
                                        col_names = ['customerid', 'customername', 'phone', 'area', 'package', 'billamount', 'balanceshift', 'status', 'expirydate']
                                        
                                        # Safe type casting to avoid DB strict validation failure
                                        try:
                                            b_amt = int(float(row_dict.get('billamount', 1500)))
                                        except:
                                            b_amt = 1500
                                            
                                        val_list = [
                                            cid, cname, cphone, 
                                            str(row_dict.get('area', 'Main Hub')).strip(), 
                                            str(row_dict.get('package', '15 Mbps Fiber')).strip(), 
                                            b_amt, 0, 'UNPAID', default_expiry
                                        ]
                                        
                                        for c in db_cols:
                                            if c not in col_names:
                                                col_names.append(c)
                                                val_list.append(str(row_dict.get(c, '')).strip())
                                                
                                        placeholders = ", ".join(["%s"] * len(val_list))
                                        cols_str = ", ".join(col_names)
                                        
                                        cursor.execute(f"INSERT INTO customers ({cols_str}) VALUES ({placeholders}) ON CONFLICT (customerid) DO NOTHING", val_list)
                                        success_count += 1
                                    except: pass
                        st.success(f"🎉 Processed entries securely into live database rows.")
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
            edit_row = df_matrix[df_matrix['customerid'] == edit_uid].iloc[0]
            edit_row_dict = dict(zip(df_matrix.columns, edit_row))
            
            with st.form("edit_terminal_form_v50"):
                up_name = st.text_input("Update Name", value=edit_row_dict.get('customername', ''))
                up_phone = st.text_input("Update Mobile Contact", value=edit_row_dict.get('phone', ''))
                
                dynamic_updates = {}
                for col in get_db_columns():
                    if col not in ['customerid', 'customername', 'phone', 'area', 'package', 'billamount', 'balanceshift', 'status', 'expirydate']:
                        dynamic_updates[col] = st.text_input(f"Update {col.upper()}", value=str(edit_row_dict.get(col, '')))
                
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
                                update_fields = ["customername=%s", "phone=%s", "area=%s"]
                                params = [up_name, norm_phone, up_area]
                                
                                for col, val in dynamic_updates.items():
                                    update_fields.append(f"{col}=%s")
                                    params.append(val)
                                    
                                if is_admin:
                                    update_fields.extend(["package=%s", "billamount=%s", "balanceshift=%s", "expirydate=%s", "status=%s"])
                                    params.extend([up_pkg, up_rate, up_arrears, up_expiry, up_status])
                                    
                                params.append(edit_uid)
                                sql_query = f"UPDATE customers SET {', '.join(update_fields)} WHERE customerid=%s"
                                cursor.execute(sql_query, params)
                        st.success("🎉 Changes Saved Successfully!")
                        st.rerun()
                with col_e2:
                    if st.form_submit_button("🚨 PERMANENTLY WIPE CLIENT", use_container_width=True, disabled=not is_admin):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor: 
                                cursor.execute("DELETE FROM customers WHERE customerid=%s", (edit_uid,))
                        st.warning("Client Wiped!")
                        st.rerun()

# ==========================================
# VIEW 3: LIFETIME LEDGER HISTORY (WITH CHARTS & SHEETS)
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    
    all_system_areas = fetch_active_areas()
    with get_db_connection() as conn:
        df_history = pd.read_sql_query("SELECT * FROM billing_history ORDER BY DateTimestamp DESC", conn)
        df_customers = pd.read_sql_query("SELECT customerid, area FROM customers", conn)
        
    if df_history.empty:
        st.info("No transaction tracking history recorded yet.")
    else:
        df_history.columns = ["invoiceid", "customerid", "customername", "datetimestamp", "currentpackage", "amountpaid", "remainingarrears", "transactiontype", "paymentmethod", "discountgiven"]
        df_customers.columns = ["customerid", "area"]
            
        df_ledger = pd.merge(df_history, df_customers, on="customerid", how="left")
        df_ledger['area'] = df_ledger['area'].fillna(all_system_areas[0] if all_system_areas else "Sanghoi System")
        
        df_ledger['DateTime'] = pd.to_datetime(df_ledger['datetimestamp'], errors='coerce')
        df_ledger['Month'] = df_ledger['DateTime'].dt.strftime('%Y-%m')
        df_ledger['Year'] = df_ledger['DateTime'].dt.strftime('%Y')
        
        if st.session_state['assigned_area'] != "ALL":
            df_ledger = df_ledger[df_ledger['area'] == st.session_state['assigned_area']]
            st.info(f"🔒 Secure Mode: Only showing logs for **{st.session_state['assigned_area']}**")
            sel_area = st.session_state['assigned_area']
        else:
            filter_options = ["ALL AREAS"] + all_system_areas
            sel_area = st.selectbox("🌐 Choose Target Area Filter", filter_options)
            
        filtered_ledger = df_ledger.copy()
        if sel_area != "ALL AREAS" and st.session_state['assigned_area'] == "ALL":
            filtered_ledger = filtered_ledger[filtered_ledger['area'] == sel_area]
            
        st.markdown("### 📊 Enterprise Financial Graphs Overview")
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("<h4 style='text-align:center; color:#3b82f6;'>📅 Monthly Collection Breakdown</h4>", unsafe_allow_html=True)
            monthly_data = filtered_ledger.groupby('Month')['amountpaid'].sum().reset_index()
            if not monthly_data.empty:
                st.bar_chart(data=monthly_data, x='Month', y='amountpaid', color="#3b82f6", use_container_width=True)
            else:
                st.info("No month data available.")
                
        with col_g2:
            st.markdown("<h4 style='text-align:center; color:#10b981;'>🏦 Annually Collection Volume</h4>", unsafe_allow_html=True)
            yearly_data = filtered_ledger.groupby('Year')['amountpaid'].sum().reset_index()
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
            st.warning("⚠️ Critical Access Node: Adding or dropping live production table schema elements affects active data structures directly.")
            
            col_sc1, col_sc2 = st.columns(2)
            with col_sc1:
                st.markdown("#### ➕ Append New Dynamic Data Column")
                with st.form("add_column_production_form"):
                    new_col_name = st.text_input("New Field Column Name (Use underscores instead of spaces)").strip().lower()
                    if st.form_submit_button("⚡ Inject Live Schema Column", use_container_width=True):
                        if not new_col_name or " " in new_col_name:
                            st.error("❌ Column names must be alpha-numeric and cannot contain empty space breaks!")
                        elif new_col_name in get_db_columns():
                            st.error("❌ Target schema data entry field identifier already exists!")
                        else:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute(f"ALTER TABLE customers ADD COLUMN {new_col_name} TEXT DEFAULT ''")
                            st.success(f"🎉 Dynamic Column Field '{new_col_name}' successfully built into active production tables.")
                            curr_order = load_column_order()
                            if new_col_name not in curr_order:
                                curr_order.append(new_col_name)
                                save_column_order(curr_order)
                            st.rerun()
            with col_sc2:
                st.markdown("#### 🗑️ Drop Dynamic Data Column Field")
                with st.form("drop_column_production_form"):
                    selectable_cols = [c for c in get_db_columns() if c not in ['customerid', 'customername', 'phone', 'area', 'package', 'billamount', 'balanceshift', 'status', 'expirydate']]
                    target_wipe_col = st.selectbox("Select Dynamic Field Target to Drop", selectable_cols if selectable_cols else ["No Dynamic Fields Active"])
                    if st.form_submit_button("🗑️ Wipe Active Column Permanently", use_container_width=True):
                        if target_wipe_col == "No Dynamic Fields Active":
                            st.error("Core engine systemic fields are locked and cannot be removed!")
                        else:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute(f"ALTER TABLE customers DROP COLUMN {target_wipe_col}")
                            st.success(f" Wiped field metadata column array '{target_wipe_col}' from tracking systems.")
                            curr_order = load_column_order()
                            if target_wipe_col in curr_order:
                                curr_order.remove(target_wipe_col)
                                save_column_order(curr_order)
                            st.rerun()
            
            st.write("---")
            st.markdown("#### 🔄 Organize Grid Order (Tarkeeb Tabdil Karein)")
            st.info("Select column array visualization rules for the Core Dashboard Analytics table.")
            
            all_current_columns = get_db_columns()
            saved_col_order = load_column_order()
            
            aligned_order = [c for c in saved_col_order if c in all_current_columns] + [c for c in all_current_columns if c not in saved_col_order]
            
            st.markdown("##### Current Live Hierarchy Order Tracking:")
            st.write(" ➡️ ".join([f"`{c.upper()}`" for c in aligned_order]))
            
            with st.form("column_reorder_form"):
                reordered_list = st.multiselect("Reorder Elements Layout Seq", options=all_current_columns, default=aligned_order)
                
                if st.form_submit_button("💾 Save Global Columns Layout Structure Order", use_container_width=True):
                    if not reordered_list:
                        st.error("❌ Order arrays mapping must contain fields!")
                    else:
                        missing_cols = [c for c in all_current_columns if c not in reordered_list]
                        final_save_list = reordered_list + missing_cols
                        save_column_order(final_save_list)
                        st.session_state['column_order'] = final_save_list
                        st.success("🎉 Display settings configuration framework mapped across cloud tables.")
                        st.rerun()

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
            query = "SELECT * FROM customers WHERE LOWER(customerid) = LOWER(%s) OR phone = %s OR cnic = %s"
            client = pd.read_sql_query(query, conn, params=[search_term, clean_phone, search_term])
            
        if client.empty: 
            st.error("❌ No registered record found matching your input. Please check your details.")
        else:
            client.columns = get_db_columns()
            c_dict = client.iloc[0].to_dict()
            
            cid_val = c_dict.get('customerid', '')
            cname_val = c_dict.get('customername', '')
            
            html_card = f"""<div class="client-card"><h3 style="color:#10b981; margin-top:0;">👤 Account Username: {html.escape(str(cid_val))}</h3><p><b>Full Name:</b> {html.escape(str(cname_val))}</p>"""
            
            for k, v in c_dict.items():
                if k not in ['customerid', 'customername']:
                    html_card += f"<p><b>{k.replace('_',' ').upper()}:</b> {html.escape(str(v))}</p>"
                    
            html_card += "</div>"
            st.markdown(html_card, unsafe_allow_html=True)