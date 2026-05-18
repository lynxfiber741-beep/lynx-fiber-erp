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
from dateutil.relativedelta import relativedelta
import bcrypt

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

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package", "billamount", "area", "address", "onuserialnumber"
]

# ==========================================
# 2. CORE THEME & PREMIUM MOBILE CSS ENGINE
# ==========================================
st.set_page_config(
    page_title="LYNX Fiber Enterprise ERP v54.3",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.stApp [data-testid="stHeader"] { background: transparent !important; height: 50px !important; }
.stApp .block-container { padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }
.stApp { background-color: #0b0f19; color: #f1f5f9; font-family: sans-serif; }
[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea { color: #000000 !important; background-color: #ffffff !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid #3b82f6 !important; border-radius: 8px !important; }
div[data-testid="stTextInput"] input[disabled], div[data-testid="stNumberInput"] input[disabled] { color: #4b5563 !important; background-color: #e5e7eb !important; border: 2px solid #9ca3af !important; }
div[data-baseweb="select"] > div { background-color: #ffffff !important; color: #000000 !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid #3b82f6 !important; border-radius: 8px !important; }
div[data-baseweb="select"] span, div[data-baseweb="select"] div { color: #000000 !important; }
ul[role="listbox"] li { color: #000000 !important; background-color: #ffffff !important; font-weight: 600 !important; }
ul[role="listbox"] li:hover { background-color: #3b82f6 !important; color: #ffffff !important; }
label, p, .stMarkdown div { color: #e5e7eb !important; font-weight: 500; }
div.stButton > button, div.stFormSubmitButton > button { background: linear-gradient(135deg, #1e293b 0%, #111827 100%) !important; color: #3b82f6 !important; border: 2px solid #3b82f6 !important; border-radius: 12px !important; padding: 15px !important; font-weight: bold !important; font-size: 15px !important; transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important; width: 100% !important; display: flex !important; align-items: center !important; justify-content: center !important; }
div.stButton > button:hover, div.stFormSubmitButton > button:hover { background: #3b82f6 !important; color: #ffffff !important; border: 2px solid #60a5fa !important; box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important; }
[data-testid="stSidebar"] div.stButton > button { background: #111827 !important; color: #9ca3af !important; border: 1px solid #374151 !important; border-radius: 8px !important; padding: 10px !important; text-align: left !important; justify-content: flex-start !important; }
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
.front-login-box { max-width: 450px; margin: 60px auto; background: #111827; padding: 40px; border-radius: 16px; border: 1px solid #10b981; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); }
.nav-header { font-size: 12px; font-weight: bold; color: #6b7280; text-transform: uppercase; margin-bottom: 10px; padding-left: 5px; }
.system-card { background: #1e293b; border: 1px solid #475569; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }
.system-card h4 { margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;}
.system-card p { margin: 5px 0; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. DIRECT DATABASE ENGINE (UPDATED CREDENTIALS)
# ==========================================
try:
    DB_URL = st.secrets["DB_URL"]
except Exception:
    encoded_pass = urllib.parse.quote_plus("cMSUKBCwAy6dyGPr")
    DB_URL = f"postgresql://postgres.ehykfrzymkzlxzkhxlww:{encoded_pass}@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=10)
        conn.autocommit = False
        yield conn
    except Exception as e:
        if conn is not None:
            conn.rollback()
        st.error(f"🔴 Critical Database Connection Error: {e}")
        st.stop()
    finally:
        if conn is not None:
            conn.close()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS areas (areaname TEXT PRIMARY KEY)")
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
            cursor.execute("CREATE TABLE IF NOT EXISTS packages (packagename TEXT PRIMARY KEY, packagerate INTEGER NOT NULL CHECK(packagerate >= 0))")
            cursor.execute("CREATE TABLE IF NOT EXISTS app_settings (settingkey TEXT PRIMARY KEY, settingvalue TEXT NOT NULL)")
            cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('Admin', 'Staff')), assignedarea TEXT DEFAULT 'ALL')")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    invoiceid TEXT PRIMARY KEY,
                    customerid TEXT NOT NULL,
                    customername TEXT NOT NULL,
                    area TEXT NOT NULL,
                    phone TEXT,
                    datetimestamp TEXT NOT NULL,
                    currentpackage TEXT NOT NULL,
                    amountpaid INTEGER NOT NULL CHECK(amountpaid >= 0),
                    remainingarrears INTEGER NOT NULL,
                    transactiontype TEXT NOT NULL,
                    paymentmethod TEXT NOT NULL,
                    discountgiven INTEGER DEFAULT 0
                )
            """)
            cursor.execute("SELECT COUNT(*) FROM areas")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO areas VALUES ('Sanghoi System'), ('Saeela System')")
            
            cursor.execute("SELECT username, password FROM users")
            existing_users = cursor.fetchall()
            if not existing_users:
                cursor.execute("INSERT INTO users VALUES ('admin', %s, 'Admin', 'ALL')", (hash_password('lynxadmin123'),))
                cursor.execute("INSERT INTO users VALUES ('staff', %s, 'Staff', 'Sanghoi System')", (hash_password('lynxstaff123'),))
            else:
                for uname, pwd in existing_users:
                    if not (pwd.startswith('$2b$') or pwd.startswith('$2a$')):
                        cursor.execute("UPDATE users SET password = %s WHERE username = %s", (hash_password(pwd), uname))
            
            cursor.execute("SELECT COUNT(*) FROM packages")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO packages VALUES ('15 Mbps Fiber', 1500), ('25 Mbps Fiber', 2000), ('35 Mbps Fiber', 2500)")
            conn.commit()

try:
    build_database_schema()
except Exception as e:
    st.error(f"Schema Builder Failed: {e}")

# High efficiency caching strategy
@st.cache_data(ttl=60)
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

@st.cache_data(ttl=60)
def fetch_system_packages():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT packagename, packagerate FROM packages ORDER BY packagerate ASC")
                rows = cur.fetchall()
                return dict(rows) if rows else {"15 Mbps Fiber": 1500}
    except Exception:
        return {"15 Mbps Fiber": 1500}

@st.cache_data(ttl=60)
def fetch_active_areas():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT areaname FROM areas ORDER BY areaname ASC")
                rows = cur.fetchall()
                return [r[0] for r in rows] if rows else ["Sanghoi System", "Saeela System"]
    except Exception:
        return ["Sanghoi System", "Saeela System"]

@st.cache_data(ttl=60)
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
    if not phone_str or str(phone_str).lower() == 'nan':
        return ""
    cleaned = str(phone_str).strip()
    if cleaned.endswith('.0'):
        cleaned = cleaned[:-2]
    cleaned = re.sub(r"\D", "", cleaned)
    if cleaned.startswith("92"):
        cleaned = "0" + cleaned[2:]
    if len(cleaned) == 10 and cleaned.startswith("3"):
        cleaned = "0" + cleaned
    return cleaned

# ==========================================
# 4. ROUTING ENGINE CONFIGURATION & GATEWAY
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
        st.markdown("<p style='text-align:center; color:#9ca3af; margin-bottom:30px;'>Enterprise ERP System v54.3 (Cloud Master Mode)</p>", unsafe_allow_html=True)
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
                        st.session_state['assigned_area'] = user_match[2] if user_match[2] else "ALL"
                        st.session_state['current_node'] = "📊 Core Analytics Dashboard"
                        st.cache_data.clear()
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
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"; st.rerun()
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"; st.rerun()
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"; st.rerun()
        if st.session_state['user_role'] == "Admin" and st.button("🔐 System Access Control", use_container_width=True):
            st.session_state['current_node'] = "🔐 System Access Control"; st.rerun()
        
        st.write("---")
        area_display = "All Systems" if st.session_state['assigned_area'] == "ALL" else st.session_state['assigned_area']
        st.markdown(f"<p style='text-align:center; color:#9ca3af;'>👤 Active: <b>{st.session_state['username'].upper()}</b><br>📍 Area: {area_display}</p>", unsafe_allow_html=True)
        if st.button("🔒 Logout System", use_container_width=True):
            st.session_state['authenticated'] = False; st.session_state['user_role'] = None; st.session_state['assigned_area'] = "ALL"
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"; st.rerun()

# ==========================================
# VIEW 1: CORE ANALYTICS DASHBOARD
# ==========================================
if routing_node == "📊 Core Analytics Dashboard":
    st.markdown("<div class='main-title'>⚡ LYNX FIBER ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    df_matrix = fetch_live_matrix()
    all_system_areas = fetch_active_areas()
    
    if df_matrix.empty:
        st.warning("⚠️ Operational Database is currently empty. Please go to Operations Center to load fresh clients.")
    else:
        collection_map = fetch_current_month_billing_summary()
        st.markdown("### 🌐 Active System Node Overview")
        for i in range(0, len(all_system_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(all_system_areas):
                    current_hub = all_system_areas[i + j]
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
                    st.session_state['dashboard_filter'] = "ALL"; st.rerun()
            with col_b2:
                if st.button(f"✅ Paid Accounts: {total_paid}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "PAID"; st.rerun()
            with col_b3:
                if st.button(f"⚠️ Arrears: Rs. {total_arrears:,}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "ARREARS"; st.rerun()
            with col_b4:
                if st.button(f"🚫 Suspended: {total_suspended}", use_container_width=True):
                    st.session_state['dashboard_filter'] = "SUSPENDED"; st.rerun()
            
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
            html_rows = []
            html_rows.append('<div class="table-wrapper"><table class="premium-table"><tr>')
            for col in custom_order_cols:
                html_rows.append(f"<th>{col.replace('_', ' ').upper()}</th>")
            html_rows.append("<th>ACTIONS</th></tr>")
            
            for row in analysis_df.itertuples(index=False):
                row_dict = dict(zip(analysis_df.columns, row))
                phone_num = str(row_dict.get('phone', ''))
                pure_digits = re.sub(r"\D", "", phone_num)
                cust_name = row_dict.get('customername', '')
                curr_bal = row_dict.get('balanceshift', 0)
                exp_dt = row_dict.get('expirydate', '')
                
                if len(pure_digits) >= 10:
                    wa_number = "92" + pure_digits[-10:]
                    wa_payload = f"Dear {cust_name}, Lynx Fiber System Update. Balance Summary: Rs.{curr_bal}. Expiry Date: {exp_dt}."
                    wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(wa_payload)}"
                    wa_action_html = f'<a href="{wa_url}" target="_blank" class="btn-action btn-w">💬 WA</a>'
                else:
                    wa_action_html = '<span class="btn-action btn-disabled">🚫 WA</span>'
                    
                html_rows.append("<tr>")
                for col in custom_order_cols:
                    raw_val = row_dict.get(col, '')
                    escaped_val = html.escape(str(raw_val))
                    if col == 'username':
                        html_rows.append(f"<td><b>{escaped_val}</b></td>")
                    elif col == 'status':
                        s_color = "#10b981" if raw_val == 'PAID' else ("#f59e0b" if raw_val == 'PARTIAL' else ("#6b7280" if raw_val == 'SUSPENDED' else "#f43f5e"))
                        icon = {"PAID": "🟢", "PARTIAL": "🟡", "UNPAID": "🔴", "SUSPENDED": "⚫"}.get(raw_val, "⚪")
                        html_rows.append(f"<td style='color:{s_color}; font-weight:bold;'>{icon} {escaped_val}</td>")
                    elif col == 'balanceshift':
                        try:
                            val_int = int(float(raw_val))
                        except:
                            val_int = 0
                        if val_int < 0:
                            html_rows.append(f"<td style='color:#10b981; font-weight:bold;'>CR Rs. {abs(val_int)}</td>")
                        else:
                            html_rows.append(f"<td style='color:#f43f5e; font-weight:bold;'>Rs. {val_int}</td>")
                    elif col == 'onuserialnumber':
                        html_rows.append(f"<td style='color:#60a5fa; font-weight:bold;'>{escaped_val}</td>")
                    else:
                        html_rows.append(f"<td>{escaped_val}</td>")
                html_rows.append(f'<td><a href="tel:{pure_digits}" class="btn-action btn-c">📞 Call</a> {wa_action_html}</td></tr>')
            html_rows.append("</table></div>")
            st.markdown("".join(html_rows), unsafe_allow_html=True)

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
        
    tabs_list = ["💳 Capital Collection Hub"]
    if is_admin:
        tabs_list.append("➕ Provision New Client")
        tabs_list.append("📥 Bulk Import Excel/CSV")
    tabs_list.append("🛠️ Edit Terminal Profile")
    
    tabs = st.tabs(tabs_list)
    
    sub_map = {}
    if not df_matrix.empty:
        for row in df_matrix.itertuples(index=False):
            row_dict = dict(zip(df_matrix.columns, row))
            uid = row_dict.get('username')
            if pd.notna(uid) and str(uid).strip() != "" and str(uid).lower() != "nan":
                sub_map[f"[{uid}] - {row_dict.get('customername', '')} ({row_dict.get('phone', '')})"] = uid
                
    with tabs[0]:
        if not sub_map:
            st.info("No active subscriber nodes found for your system area.")
        else:
            target_label = st.selectbox("Select Target Subscriber Username", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            matched_rows = df_matrix[df_matrix['username'] == resolved_uid]
            
            if matched_rows.empty:
                st.error(f"❌ Username '{resolved_uid}' matrix data was not found.")
            else:
                node_row_dict = matched_rows.iloc[0].to_dict()
                try:
                    curr_bill_amt = int(float(node_row_dict.get('billamount', 0)))
                    curr_bal_shift = int(float(node_row_dict.get('balanceshift', 0)))
                except:
                    curr_bill_amt = 0; curr_bal_shift = 0
                st.info(f"📊 **Monthly Rate:** Rs. {curr_bill_amt} | **Arrears Balance:** Rs. {curr_bal_shift}")
                
                billing_months = st.selectbox("📅 Select Billing Duration (Advance Months)", [1, 3, 6, 12])
                calculated_bill = curr_bill_amt * billing_months
                gross_invoice_due = calculated_bill + curr_bal_shift
                
                with st.form("cash_posting_form_v50"):
                    pay_method = st.selectbox("Payment Method Profile", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"])
                    discount_value = st.number_input("🎁 Discount Approved (Rs.)", min_value=0, value=0, disabled=not is_admin)
                    net_payable_after_discount = max(gross_invoice_due - discount_value, 0)
                    st.markdown(f"### 🧾 Net Payable (After Discount): **Rs. {net_payable_after_discount}**")
                    cash_inflow = st.number_input("Liquid Capital Received (Rs.)", min_value=0, value=net_payable_after_discount)
                    
                    if st.form_submit_button("💳 POST TRANSACTION & EXTEND LINE", use_container_width=True):
                        future_shift = net_payable_after_discount - cash_inflow
                        new_state = "PARTIAL" if future_shift > 0 and cash_inflow > 0 else ("UNPAID" if future_shift > 0 else "PAID")
                        try:
                            current_expiry = datetime.strptime(str(node_row_dict.get('expirydate')), "%Y-%m-%d")
                            base_date = datetime.now() if current_expiry < datetime.now() else current_expiry
                        except:
                            base_date = datetime.now()
                        new_expiry = (base_date + relativedelta(months=billing_months)).strftime("%Y-%m-%d")
                        invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                        
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s", (future_shift, new_state, new_expiry, resolved_uid))
                                cursor.execute("""
                                    INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s)
                                """, (invoice_uuid, resolved_uid.strip().lower(), node_row_dict.get('customername', ''), node_row_dict.get('area', ''), node_row_dict.get('phone', ''), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{node_row_dict.get('package', '')} ({billing_months}M Advance)", cash_inflow, future_shift, pay_method, discount_value))
                            conn.commit()
                        st.success(f"🎉 Transaction Posted!")
                        st.cache_data.clear()
                        st.rerun()
                        
    current_tab_idx = 1
    if is_admin:
        with tabs[current_tab_idx]:
            with st.form("add_client_form_v50", clear_on_submit=True):
                in_id = (st.text_input("Desired Username Key") or "").strip().lower()
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
                    if not in_id or not in_name or not norm_p:
                        st.error("❌ Required core fields missing!")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("SELECT COUNT(*) FROM customers WHERE username = %s", (in_id,))
                                if cursor.fetchone()[0] > 0:
                                    st.error("❌ Username exists!")
                                else:
                                    default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                                    try:
                                        cursor.execute("""
                                            INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s)
                                        """, (in_id, in_name, norm_p, in_cnic, chosen_pkg, in_rate, in_area, in_address, in_sn, default_expiry))
                                        conn.commit()
                                        st.success("✅ Added Profile Successfully!")
                                        st.cache_data.clear(); st.rerun()
                                    except psycopg2.IntegrityError:
                                        st.error("❌ Phone Number already allocated!")
        current_tab_idx += 1
        with tabs[current_tab_idx]:
            st.markdown("### 📥 BULK EXCEL / CSV UPLOADER ENGINE")
            uploaded_file = st.file_uploader("Choose Excel or CSV File", type=['xlsx', 'csv'], key="bulk_file_uploader_master")
            if uploaded_file is not None:
                try:
                    import_df = pd.read_excel(uploaded_file, dtype=str) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file, dtype=str)
                    import_df.columns = [str(c).strip() for c in import_df.columns]
                    total_rows_found = len(import_df)
                    raw_columns_mapped = {str(original_col).strip().lower().replace(" ", "").replace("_", "").replace("-", ""): original_col for original_col in import_df.columns}
                    st.dataframe(import_df.head(5), use_container_width=True)
                    
                    if st.button(f"⚡ Save All {total_rows_found} Sheet Records to Live Database", use_container_width=True):
                        success_count, update_count, skip_count = 0, 0, 0
                        error_logs = []
                        default_expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                        default_pkg = list(pkg_dict.keys())[0] if pkg_dict else "15 Mbps Fiber"
                        default_area = all_system_areas[0] if all_system_areas else "Sanghoi System"
                        
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                for index, row in import_df.iterrows():
                                    savepoint_id = f"row_{index}"
                                    cursor.execute(f"SAVEPOINT {savepoint_id}")
                                    try:
                                        r_dict = row.to_dict()
                                        def get_excel_val(possible_keys, default_str=""):
                                            for pk in possible_keys:
                                                if pk in raw_columns_mapped:
                                                    val = str(r_dict.get(raw_columns_mapped[pk], '')).strip()
                                                    if val.lower() != 'nan' and val != '':
                                                        if val.endswith('.0'):
                                                            val = val[:-2]
                                                        return val
                                            return default_str
                                        
                                        uid = get_excel_val(['username', 'userid', 'user', 'id', 'customerid']).lower().strip()
                                        cname = get_excel_val(['customername', 'name', 'clientname', 'subscribername']).strip()
                                        raw_phone = get_excel_val(['phone', 'phonenumber', 'mobile', 'mobilecode', 'contact'])
                                        
                                        if not uid or not cname:
                                            skip_count += 1; cursor.execute(f"RELEASE SAVEPOINT {savepoint_id}"); continue
                                        cphone = clean_and_validate_phone(raw_phone)
                                        if not cphone:
                                            skip_count += 1; error_logs.append(f"Row {index+2} (User: {uid}): Phone empty."); cursor.execute(f"RELEASE SAVEPOINT {savepoint_id}"); continue
                                            
                                        raw_rate = get_excel_val(['billamount', 'rate', 'bill', 'amount', 'charges'])
                                        clean_rate = re.sub(r"[^\d]", "", raw_rate)
                                        try:
                                            b_amt = int(clean_rate) if clean_rate else int(pkg_dict.get(default_pkg, 1500))
                                        except:
                                            b_amt = int(pkg_dict.get(default_pkg, 1500))
                                            
                                        cursor.execute("""
                                            INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s)
                                            ON CONFLICT (username) DO UPDATE SET customername = EXCLUDED.customername, phone = EXCLUDED.phone, cnic = EXCLUDED.cnic, package = EXCLUDED.package, billamount = EXCLUDED.billamount, area = EXCLUDED.area, address = EXCLUDED.address, onuserialnumber = EXCLUDED.onuserialnumber
                                            RETURNING (xmax = 0);
                                        """, (uid, cname, cphone, get_excel_val(['cnic', 'cnicnumber', 'nic']), get_excel_val(['package', 'plan', 'internetplan'], default_pkg), b_amt, get_excel_val(['area', 'system', 'zone', 'location'], default_area), get_excel_val(['address', 'locationaddress', 'house']), get_excel_val(['onuserialnumber', 'onusn', 'serial', 'sn', 'onuserial']), default_expiry))
                                        if cursor.fetchone()[0]:
                                            success_count += 1
                                        else:
                                            update_count += 1
                                        cursor.execute(f"RELEASE SAVEPOINT {savepoint_id}")
                                    except Exception as ex:
                                        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_id}"); skip_count += 1
                            conn.commit()
                        st.success("🎉 **Excel file data kamyabi se upload aur live database mein safe ho chuka hai!**")
                        st.cache_data.clear(); st.stop()
                except Exception as e:
                    st.error(f"❌ Mapping Error: {e}")
        current_tab_idx += 1
        
    with tabs[current_tab_idx]:
        if not sub_map:
            st.info("No active terminals.")
        else:
            edit_target = st.selectbox("Select Target Username to Modify", list(sub_map.keys()), key="edit_tgt_box")
            edit_matched = df_matrix[df_matrix['username'] == sub_map[edit_target]]
            if not edit_matched.empty:
                edit_row_dict = edit_matched.iloc[0].to_dict()
                with st.form("edit_terminal_form_v50"):
                    up_name = st.text_input("Update Customer Name", value=edit_row_dict.get('customername', ''))
                    up_phone = st.text_input("Update Phone Number", value=edit_row_dict.get('phone', ''))
                    up_cnic = st.text_input("Update CNIC Number", value=edit_row_dict.get('cnic', ''))
                    up_address = st.text_input("Update Address", value=edit_row_dict.get('address', ''))
                    up_sn = st.text_input("Update Onu SN", value=edit_row_dict.get('onuserialnumber', ''))
                    up_area = st.selectbox("System Area Hub", all_system_areas, index=all_system_areas.index(edit_row_dict.get('area')) if edit_row_dict.get('area') in all_system_areas else 0)
                    
                    try:
                        parsed_bill_amt = int(float(edit_row_dict.get('billamount', 0)))
                        parsed_bal_shift = int(float(edit_row_dict.get('balanceshift', 0)))
                    except:
                        parsed_bill_amt = 0; parsed_bal_shift = 0
                        
                    if is_admin:
                        all_pkgs = list(pkg_dict.keys())
                        up_pkg = st.selectbox("Override Package Profile", all_pkgs, index=all_pkgs.index(edit_row_dict.get('package')) if edit_row_dict.get('package') in all_pkgs else 0)
                        up_rate = st.number_input("Monthly Bill Rate (Rs.)", value=parsed_bill_amt)
                    else:
                        st.text_input("Package Profile", value=edit_row_dict.get('package', ''), disabled=True)
                        up_pkg = edit_row_dict.get('package', ''); up_rate = parsed_bill_amt
                        
                    up_arrears = st.number_input("Outstanding Balance (Arrears)", value=parsed_bal_shift, disabled=not is_admin)
                    up_expiry = st.text_input("Expiry Date (YYYY-MM-DD)", value=edit_row_dict.get('expirydate', ''), disabled=not is_admin)
                    up_status = st.selectbox("Line Status", ["PAID", "PARTIAL", "UNPAID", "SUSPENDED"], index=["PAID", "PARTIAL", "UNPAID", "SUSPENDED"].index(edit_row_dict.get('status', 'UNPAID')), disabled=not is_admin)
                    
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        if st.form_submit_button("💾 SAVE EDITS", use_container_width=True):
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        UPDATE customers SET customername=%s, phone=%s, cnic=%s, package=%s, billamount=%s, area=%s, address=%s, onuserialnumber=%s, balanceshift=%s, expirydate=%s, status=%s WHERE username=%s
                                    """, (up_name, clean_and_validate_phone(up_phone), up_cnic, up_pkg, up_rate, up_area, up_address, up_sn, up_arrears, up_expiry, up_status, edit_row_dict['username']))
                                conn.commit()
                            st.success("🎉 Changes Saved!")
                            st.cache_data.clear(); st.rerun()
                    with col_e2:
                        if st.form_submit_button("🚨 PERMANENTLY WIPE CLIENT", use_container_width=True, disabled=not is_admin):
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("DELETE FROM customers WHERE username=%s", (edit_row_dict['username'],))
                                conn.commit()
                            st.cache_data.clear(); st.rerun()

# ==========================================
# VIEW 3: LIFETIME LEDGER HISTORY
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    all_system_areas = fetch_active_areas()
    df_ledger = pd.DataFrame()
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM billing_history ORDER BY datetimestamp DESC")
            l_rows = cur.fetchall()
            if l_rows:
                df_ledger = pd.DataFrame(l_rows)
                
    if df_ledger.empty:
        st.info("No transaction tracking history recorded yet.")
    else:
        df_ledger.columns = [c.lower() for c in df_ledger.columns]
        df_ledger['datetime'] = pd.to_datetime(df_ledger['datetimestamp'].astype(str), errors='coerce')
        df_ledger['Month'] = df_ledger['datetime'].dt.strftime('%Y-%m')
        df_ledger['Year'] = df_ledger['datetime'].dt.strftime('%Y')
        
        if st.session_state['assigned_area'] != "ALL":
            df_ledger = df_ledger[df_ledger['area'].str.lower() == st.session_state['assigned_area'].lower()]
            sel_area = st.session_state['assigned_area']
        else:
            sel_area = st.selectbox("🌐 Choose Target Area Filter", ["ALL AREAS"] + all_system_areas)
            
        filtered_ledger = df_ledger.copy()
        if sel_area != "ALL AREAS" and st.session_state['assigned_area'] == "ALL":
            filtered_ledger = filtered_ledger[filtered_ledger['area'].str.lower() == sel_area.lower()]
            
        st.markdown("### 📊 Enterprise Financial Graphs Overview")
        col_g1, col_g2 = st.columns(2)
        clean_graph_ledger = filtered_ledger.dropna(subset=['invoiceid']).drop_duplicates(subset=['invoiceid']).copy()
        
        if not clean_graph_ledger.empty:
            clean_graph_ledger['amountpaid'] = pd.to_numeric(clean_graph_ledger['amountpaid'], errors='coerce').fillna(0)
            with col_g1:
                st.markdown("<h4 style='text-align:center; color:#3b82f6;'>📅 Monthly Collection</h4>", unsafe_allow_html=True)
                st.bar_chart(data=clean_graph_ledger.groupby('Month')['amountpaid'].sum().reset_index(), x='Month', y='amountpaid', color="#3b82f6", use_container_width=True)
            with col_g2:
                st.markdown("<h4 style='text-align:center; color:#10b981;'>🏦 Annually Volume</h4>", unsafe_allow_html=True)
                st.bar_chart(data=clean_graph_ledger.groupby('Year')['amountpaid'].sum().reset_index(), x='Year', y='amountpaid', color="#10b981", use_container_width=True)
                
        st.write("---")
        required_cols = ['invoiceid', 'customerid', 'customername', 'area', 'datetimestamp', 'currentpackage', 'discountgiven', 'amountpaid', 'paymentmethod', 'remainingarrears']
        available_cols = [col for col in required_cols if col in filtered_ledger.columns]
        excel_sheet_df = filtered_ledger[available_cols].copy()
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            excel_sheet_df.to_excel(writer, index=False, sheet_name='Ledger_History')
        buffer.seek(0)
        
        st.download_button(label="📥 Export Full Audit Trail to Excel Sheet (.xlsx)", data=buffer, file_name=f"LYNX_Master_Ledger.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
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
        adm_tab1, adm_tab2, adm_tab3, adm_tab4, adm_tab5 = st.tabs(["🛠️ Master Schema Settings", "⚙️ Access Accounts", "📦 Fixed Packages", "🗺️ Dynamic Area Hubs", "👤 Security Admin"])
        
        with adm_tab1:
            st.markdown("### 👑 Master Database Schema Engineering")
            if 'purge_requested' not in st.session_state:
                st.session_state['purge_requested'] = False
            if not st.session_state['purge_requested']:
                if st.button("🚨 FORCE CLEAN & PURGE LIVE DATABASE STRUCTURE", use_container_width=True):
                    st.session_state['purge_requested'] = True; st.rerun()
            else:
                purge_password = st.text_input("سیکیورٹی پاسورڈ درج کریں (Security Password)", type="password")
                col_purge1, col_purge2 = st.columns(2)
                with col_purge1:
                    if st.button("✅ پاسورڈ کی تصدیق کریں اور ڈیٹا اڑائیں", use_container_width=True) and purge_password == "lynx@secure786":
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DROP TABLE IF EXISTS billing_history CASCADE; DROP TABLE IF EXISTS customers CASCADE;")
                        build_database_schema()
                        st.success("🚀 System success fully reset ho chuka hai!")
                        st.session_state['purge_requested'] = False
                        st.cache_data.clear(); st.rerun()
                with col_purge2:
                    if st.button("❌ کینسل کریں (Cancel)", use_container_width=True):
                        st.session_state['purge_requested'] = False; st.rerun()
                        
        with adm_tab2:
            with st.form("new_admin_form"):
                new_admin_user = st.text_input("New Admin Username").strip().lower()
                new_admin_pass = st.text_input("New Admin Password", type="password").strip()
                if st.form_submit_button("➕ Create Admin", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            try:
                                cursor.execute("INSERT INTO users VALUES (%s, %s, 'Admin', 'ALL')", (new_admin_user, hash_password(new_admin_pass)))
                                conn.commit()
                                st.success("Created!")
                            except:
                                st.error("Exists!")
                                
            with st.form("new_staff_form_v50"):
                new_user = st.text_input("New Staff Username").strip().lower()
                new_pass = st.text_input("New Staff Password", type="password").strip()
                new_area_lock = st.selectbox("Assign & Lock System Area", all_system_areas)
                if st.form_submit_button("🚀 Add Staff Account & Lock Area", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            try:
                                cursor.execute("INSERT INTO users VALUES (%s, %s, 'Staff', %s)", (new_user, hash_password(new_pass), new_area_lock))
                                conn.commit()
                                st.success("Created!")
                            except:
                                st.error("Exists!")
                                
        with adm_tab3:
            with st.form("add_package_form"):
                p_name = st.text_input("Package Profile Name").strip()
                p_rate = st.number_input("Fixed Monthly Rate (Rs.)", min_value=0, value=1500)
                if st.form_submit_button("💾 Save Fixed Package to System", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("INSERT INTO packages VALUES (%s, %s) ON CONFLICT (packagename) DO UPDATE SET packagerate = EXCLUDED.packagerate", (p_name, p_rate))
                            conn.commit()
                    st.cache_data.clear(); st.rerun()
                    
        with adm_tab4:
            with st.form("dynamic_add_area_form"):
                fresh_area_name = st.text_input("Enter New Area Name").strip()
                if st.form_submit_button("➕ REGISTER NEW AREA NODE", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            try:
                                cursor.execute("INSERT INTO areas VALUES (%s)", (fresh_area_name,))
                                conn.commit()
                            except:
                                pass
                    st.cache_data.clear(); st.rerun()
                    
        with adm_tab5:
            with st.form("admin_profile_form"):
                up_admin_user = st.text_input("Change Admin Username", value=st.session_state['username']).strip().lower()
                up_admin_pass = st.text_input("New Admin Password", type="password").strip()
                if st.form_submit_button("🔒 Securely Update Admin Profile", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("DELETE FROM users WHERE username = %s", (st.session_state['username'],))
                            cursor.execute("INSERT INTO users VALUES (%s, %s, 'Admin', 'ALL')", (up_admin_user, hash_password(up_admin_pass)))
                            conn.commit()
                    st.session_state['authenticated'] = False; st.rerun()

# ==========================================
# VIEW 5: CLIENT PORTAL
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown("<div class='main-title'>📱 LYNX FIBER SUBSCRIBER PORTAL</div>", unsafe_allow_html=True)
    portal_input = st.text_input("Enter Username, Registered Mobile Number, or CNIC")
    if portal_input:
        search_term = portal_input.strip()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE LOWER(username) = LOWER(%s) OR phone = %s OR cnic = %s", [search_term, clean_and_validate_phone(search_term), search_term])
                c_rows = cur.fetchall()
                if not c_rows:
                    st.error("❌ No registered record found.")
                else:
                    c_dict = c_rows[0]
                    html_card = f"""<div class="client-card"><h3 style="color:#10b981; margin-top:0;">👤 Account Username: {html.escape(str(c_dict.get('username','')))}</h3>"""
                    for k in GLOBAL_TARGET_ORDER:
                        if k != 'username':
                            html_card += f"<p><b>{k.upper()}:</b> {html.escape(str(c_dict.get(k, '')))}</p>"
                    st.markdown(html_card + "</div>", unsafe_allow_html=True)