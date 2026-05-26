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
import json
from datetime import datetime
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta
import bcrypt

# ========================================== #
# 🛑 SAAS MASTER CONFIGURATION & HIDDEN REGISTRY #
# ========================================== #
DISTRIBUTOR_NAME = "Lynx Fiber Internet"
MASTER_NOTIFY_NUMBERS = ["03215943786", "03118808741"]
GENERIC_TEXT = "Lynx Fiber Internet"

# Default fallback staff editing permissions
DEFAULT_STAFF_PERMS = {
    "customername": True,
    "phone": True,
    "address": True,
    "onuserialnumber": True,
    "billamount": False,
    "status": False
}

# ========================================== #
# 0. CORE PAGE CONFIGURATION (MUST BE FIRST) #
# ========================================== #
st.set_page_config(
    page_title=f"Enterprise ERP Panel — Powered by {DISTRIBUTOR_NAME}", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# ========================================== #
# REPORTLAB ENGINE (INTEGRATED RECEIPT GENERATOR) #
# ========================================== #
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# ========================================== #
# 1. CORE CONFIGURATION & SESSION STATE      #
# ========================================== #
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = ""
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'tenant_id' not in st.session_state:
    st.session_state['tenant_id'] = "lynx"
if 'assigned_areas' not in st.session_state:
    st.session_state['assigned_areas'] = ["ALL"]
if 'current_node' not in st.session_state:
    st.session_state['current_node'] = "📊 Lynx Dashboard"
if 'portal_mode' not in st.session_state:
    st.session_state['portal_mode'] = False

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package", 
    "billamount", "area", "address", "onuserialnumber"
]

# ========================================== #
# 2. SECURE POOLED DATABASE REGISTRY         #
# ========================================== #
if "DB_URL" in st.secrets:
    DB_URL = st.secrets["DB_URL"]
else:
    st.error("🔴 Critical Configuration Error: 'DB_URL' is missing from Streamlit Secrets! Please add it to execute.")
    st.stop()

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
    conn.autocommit = True
    try:
        yield conn
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
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

# Fail-safe Engine Activity Logger Function
def insert_activity_log(tenant_id, username, action_type, description):
    try:
        log_id = f"LOG-{uuid.uuid4().hex[:10].upper()}"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO activity_logs (log_id, tenant_id, username, action_type, description, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (log_id, tenant_id, username, action_type, description, ts))
    except Exception:
        pass  # Fail-safe mechanism to guarantee core operations are never blocked

# Invoice PDF Builder Function with XML Safeguards
def generate_receipt_pdf(company_name, phone_ref, inv_id, c_id, c_name, area, package, paid, arrears, method):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#10b981'), alignment=TA_CENTER, spaceAfter=10)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontSize=10, textColor=colors.gray, alignment=TA_CENTER, spaceAfter=20)
    normal_style = ParagraphStyle('NormStyle', parent=styles['Normal'], fontSize=11, leading=16, textColor=colors.HexColor('#111827'))
    
    def escape_xml(txt):
        return html.escape(str(txt))
        
    try:
        paid_val = int(float(str(paid)))
        arrears_val = int(float(str(arrears)))
    except Exception:
        paid_val = 0
        arrears_val = 0
        
    story = [
        Paragraph(escape_xml(company_name).upper(), title_style),
        Paragraph(f"Official Helpline: {escape_xml(phone_ref)} | Transaction Receipt", sub_style),
        Spacer(1, 10)
    ]
    
    data = [
        [Paragraph(f"<b>Invoice Reference:</b> {escape_xml(inv_id)}", normal_style), Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style)],
        [Paragraph(f"<b>Subscriber Key:</b> {escape_xml(c_id)}", normal_style), Paragraph(f"<b>Customer Name:</b> {escape_xml(c_name)}", normal_style)],
        [Paragraph(f"<b>Network Hub/Area:</b> {escape_xml(area)}", normal_style), Paragraph(f"<b>Subscribed Profile:</b> {escape_xml(package)}", normal_style)],
        [Paragraph(f"<b>Cash Remitted:</b> Rs. {paid_val:,}", normal_style), Paragraph(f"<b>Carried Arrears:</b> Rs. {arrears_val:,}", normal_style)],
        [Paragraph(f"<b>Payment Gateway:</b> {escape_xml(method)}", normal_style), Paragraph(f"<b>Status:</b> SECURED / PROCESSED", normal_style)]
    ]
    
    table = Table(data, colWidths=[260, 260])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ========================================== #
# 3. AUTO-REPAIR MULTI-TENANT SCHEMA ENGINE  #
# ========================================== #
def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # 1. System Tenants
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    support_phone TEXT NOT NULL,
                    owner_username TEXT NOT NULL,
                    license_active BOOLEAN DEFAULT FALSE,
                    registration_date TEXT NOT NULL,
                    license_expiry_date TEXT NOT NULL DEFAULT '',
                    staff_permissions TEXT DEFAULT ''
                )
            """)
            # 2. Users Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    assignedarea TEXT DEFAULT 'ALL',
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            # 3. Customers Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    username TEXT NOT NULL,
                    customername TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    cnic TEXT DEFAULT '',
                    package TEXT NOT NULL,
                    billamount INTEGER NOT NULL DEFAULT 0,
                    area TEXT NOT NULL,
                    address TEXT DEFAULT '',
                    onuserialnumber TEXT DEFAULT '',
                    balanceshift INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'UNPAID',
                    expirydate TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            # 4. Areas Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS areas (
                    areaname TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (areaname, tenant_id)
                )
            """)
            # 5. Packages Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    packagename TEXT NOT NULL,
                    areaname TEXT NOT NULL,
                    packagerate INTEGER NOT NULL DEFAULT 0,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (packagename, areaname, tenant_id)
                )
            """)
            # 6. Billing History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    invoiceid TEXT PRIMARY KEY,
                    customerid TEXT NOT NULL,
                    customername TEXT NOT NULL,
                    area TEXT NOT NULL,
                    phone TEXT,
                    datetimestamp TEXT NOT NULL,
                    currentpackage TEXT NOT NULL,
                    amountpaid INTEGER NOT NULL DEFAULT 0,
                    remainingarrears INTEGER NOT NULL,
                    transactiontype TEXT NOT NULL,
                    paymentmethod TEXT NOT NULL,
                    discountgiven INTEGER DEFAULT 0,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx'
                )
            """)
            # 7. FIXED Activity Logs Table Structure Baseline
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT ''
                )
            """)
            
            # Initial Data Setup
            cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date, license_expiry_date, staff_permissions)
                    VALUES ('lynx', 'Lynx Fiber Pvt Ltd', '03135776263', 'owner', TRUE, %s, '', '')
                """, (datetime.now().strftime("%Y-%m-%d"),))
                
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner' AND tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO users (username, password, role, assignedarea, tenant_id)
                    VALUES ('owner', %s, 'Owner', 'ALL', 'lynx')
                """, (hash_password('lynxowner123'),))

# 🔥 LIVE HOT-MIGRATION ALIGNMENT ENGINE
def run_live_migrations():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS timestamp TEXT NOT NULL DEFAULT '';")
                cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS staff_permissions TEXT DEFAULT '';")
    except Exception:
        pass

@st.cache_resource
def initialize_application_database():
    build_database_schema()

# Execute Orders Sequence
initialize_application_database()
run_live_migrations()

# ========================================== #
# 4. DATA RETRIEVAL LAYERS                   #
# ========================================== #
@st.cache_data(ttl=2)
def fetch_active_tenant_metadata(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT company_name, support_phone, license_active, license_expiry_date, staff_permissions FROM system_tenants WHERE tenant_id = %s", (tenant_id,))
                res = cur.fetchone()
                if res:
                    perms = DEFAULT_STAFF_PERMS.copy()
                    if res.get("staff_permissions"):
                        try:
                            perms.update(json.loads(res["staff_permissions"]))
                        except Exception:
                            pass
                    return {
                        "name": res["company_name"],
                        "phone": res["support_phone"],
                        "active": res["license_active"],
                        "expiry_date": res.get("license_expiry_date", ""),
                        "staff_permissions": perms
                    }
        return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True, "expiry_date": "", "staff_permissions": DEFAULT_STAFF_PERMS}
    except Exception:
        return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True, "expiry_date": "", "staff_permissions": DEFAULT_STAFF_PERMS}

def calculate_license_days(expiry_str):
    if not expiry_str or expiry_str.strip() == "":
        return "Lifetime Plan Active", True
    try:
        expiry_dt = datetime.strptime(expiry_str.strip(), "%Y-%m-%d")
        expiry_end = expiry_dt.replace(hour=23, minute=59, second=59)
        today_dt = datetime.now()
        time_diff = expiry_end - today_dt
        if time_diff.total_seconds() <= 0:
            return "Expired", False
        days = time_diff.days
        if days >= 1:
            return f"{days} Days Remaining", True
        else:
            hours = int(time_diff.total_seconds() // 3600)
            minutes = int((time_diff.total_seconds() % 3600) // 60)
            return f"Last Day! ({hours}h {minutes}m remaining)", True
    except Exception:
        return "Invalid Expiry Mapping", False

tenant_meta = fetch_active_tenant_metadata(st.session_state['tenant_id'])
TENANT_COMPANY_NAME = tenant_meta["name"]
TENANT_SUPPORT_PHONE = tenant_meta["phone"]
STAFF_PERMISSIONS = tenant_meta["staff_permissions"]
license_status_text, is_license_valid = calculate_license_days(tenant_meta.get("expiry_date", ""))

if not tenant_meta["active"] or not is_license_valid:
    st.error(f"⚠️ 🔐 SOFTWARE LICENSE SUSPENDED OR EXPIRED! Status: {license_status_text}. Please contact Lynx Fiber Online to renew your portal instance.")
    st.stop()

@st.cache_data(ttl=3)
def fetch_isolated_matrix(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE tenant_id = %s ORDER BY customername ASC", (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    df = pd.DataFrame(rows)
                    df.columns = [c.lower() for c in df.columns]
                    df['area'] = df['area'].fillna('').astype(str)
                    df['username'] = df['username'].fillna('').astype(str)
                    df['status'] = df['status'].fillna('UNPAID').astype(str)
                    extended_cols = GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER]
                    return df.reindex(columns=extended_cols)
        return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate', 'tenant_id'])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3)
def fetch_isolated_areas(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT areaname FROM areas WHERE tenant_id = %s ORDER BY areaname ASC", (tenant_id,))
                rows = cur.fetchall()
                return [r[0] for r in rows] if rows else []
    except Exception:
        return []

@st.cache_data(ttl=3)
def fetch_isolated_packages(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT packagename, areaname, packagerate FROM packages WHERE tenant_id = %s ORDER BY packagename ASC, areaname ASC", (tenant_id,))
                return cur.fetchall()
    except Exception:
        return []

@st.cache_data(ttl=3)
def fetch_isolated_billing_summary(tenant_id):
    try:
        current_month_str = datetime.now().strftime("%Y-%m")
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT LOWER(TRIM(customerid)) as customerid, amountpaid FROM billing_history WHERE tenant_id = %s AND datetimestamp LIKE %s", (tenant_id, current_month_str + '%'))
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
    if cleaned.startswith("0"):
        return cleaned
    if len(cleaned) == 10 and cleaned.startswith("3"):
        cleaned = "0" + cleaned
    return cleaned

# UI Styles CSS Engine
st.markdown(f"""
<style>
    .stApp [data-testid="stHeader"] {{ background: transparent !important; height: 50px !important; }}
    .stApp .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }}
    .stApp {{ background-color: #0b0f19; color: #f1f5f9; font-family: sans-serif; }}
    [data-testid="stSidebar"] {{ background-color: #111827; border-right: 1px solid #1f2937; }}
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea {{ color: #000000 !important; background-color: #ffffff !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid #3b82f6 !important; border-radius: 8px !important; }}
    div[data-testid="stNumberInput"] button {{ background-color: #e2e8f0 !important; color: #000000 !important; }}
    div[data-baseweb="select"] > div {{ background-color: #ffffff !important; color: #000000 !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid #3b82f6 !important; border-radius: 8px !important; }}
    div[data-baseweb="select"] span, div[data-baseweb="select"] div {{ color: #000000 !important; }}
    ul[role="listbox"] li {{ color: #000000 !important; background-color: #ffffff !important; font-weight: 600 !important; }}
    label, p, .stMarkdown div {{ color: #e5e7eb !important; font-weight: 500; }}
    div.stButton > button, div.stFormSubmitButton > button {{ background: linear-gradient(135deg, #1e293b 0%, #111827 100%) !important; color: #3b82f6 !important; border: 2px solid #3b82f6 !important; border-radius: 12px !important; padding: 15px !important; font-weight: bold !important; font-size: 15px !important; transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important; width: 100% !important; display: flex !important; align-items: center !important; justify-content: center !important; }}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {{ background: #3b82f6 !important; color: #ffffff !important; border: 2px solid #60a5fa !important; box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important; }}
    .table-wrapper {{ overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; margin-top: 15px; }}
    .premium-table {{ width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; background: #111827; }}
    .premium-table th {{ background: #1f2937; color: #10b981; padding: 14px; text-align: left; font-size: 13px; border-bottom: 2px solid #374151; white-space: nowrap; text-transform: uppercase;}}
    .premium-table td {{ padding: 14px; border-bottom: 1px solid #1f2937; font-size: 13px; color: #e5e7eb; white-space: nowrap; }}
    .btn-action {{ padding: 6px 12px; border-radius: 6px; font-weight: bold; text-decoration: none; font-size: 12px; display: inline-block; margin-right: 4px; }}
    .btn-c {{ background-color: #2563eb; color: white !important; }}
    .btn-w {{ background-color: #16a34a; color: white !important; }}
    .client-card {{ background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 15px; }}
    .main-title {{ color: #10b981; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }}
    .front-login-box {{ max-width: 450px; margin: 40px auto; background: #111827; padding: 40px; border-radius: 16px; border: 1px solid #10b981; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); }}
    .system-card {{ background: #1e293b; border: 1px solid #475569; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }}
    .system-card h4 {{ margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;}}
    .saas-footer {{ text-align: center; font-size: 12px; color: #6b7280; margin-top: 50px; padding: 15px; border-top: 1px solid #1f2937; }}
    .saas-footer b {{ color: #3b82f6; }}
    .live-calc-box {{ background-color: #111827; border: 2px dashed #10b981; padding: 15px; border-radius: 10px; margin-bottom: 15px; }}
</style>
""", unsafe_allow_html=True)

# ========================================== #
# 5. PORTAL SECURITY ROUTING ENGINE          #
# ========================================== #
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
        login_tab, register_tab = st.tabs(["🔒 Secure Login Portal", "➕ Register New ISP Application"])
        
        with login_tab:
            st.markdown(f"<h3 style='text-align:center; color:#10b981;'>ERP SYSTEM LOGIN</h3>", unsafe_allow_html=True)
            input_tenant = st.text_input("Tenant Domain ID / Code (e.g., lynx)", key="log_tenant").strip().lower()
            user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
            pass_input = st.text_input("Security Password", type="password", key="front_pass")
            
            if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT role, username, assignedarea, password FROM users WHERE LOWER(username) = %s AND tenant_id = %s", (user_input, input_tenant))
                        user_match = cursor.fetchone()
                        if user_match and verify_password(pass_input, user_match[3]):
                            t_meta = fetch_active_tenant_metadata(input_tenant)
                            _, valid_chk = calculate_license_days(t_meta.get("expiry_date", ""))
                            if not t_meta["active"] or not valid_chk:
                                st.error("⚠️ This system access instance is locked or license has expired.")
                            else:
                                st.session_state['authenticated'] = True
                                st.session_state['user_role'] = user_match[0] if user_match[0] else "Staff"
                                st.session_state['username'] = user_match[1] if user_match[1] else user_input
                                st.session_state['tenant_id'] = input_tenant
                                raw_areas = user_match[2] if user_match[2] else "ALL"
                                if user_match[0] in ["Owner", "Admin"] or raw_areas == "ALL":
                                    st.session_state['assigned_areas'] = ["ALL"]
                                else:
                                    st.session_state['assigned_areas'] = [a.strip() for a in raw_areas.split(",") if a.strip()]
                                st.session_state['current_node'] = "📊 Lynx Dashboard"
                                insert_activity_log(input_tenant, st.session_state['username'], "LOGIN", "System initialized successfully via secure portal node.")
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            st.error("❌ Invalid Tenant, Username, or Password Variant.")
                            
        with register_tab:
            st.markdown("<h3 style='text-align:center; color:#3b82f6;'>SaaS Tenant Onboarding</h3>", unsafe_allow_html=True)
            with st.form("saas_tenant_registration_form"):
                reg_tenant_id = st.text_input("Choose Unique Tenant Code (e.g., falcon, alpha)").strip().lower()
                reg_company_name = st.text_input("ISP Company Full Brand Name").strip()
                reg_support_phone = st.text_input("Official Support Helpline Number").strip()
                reg_owner_user = st.text_input("Create Master Admin Username").strip().lower()
                reg_owner_pass = st.text_input("Create Master Admin Password", type="password")
                
                if st.form_submit_button("➕ SUBMIT ACTIVATION APP PROPOSAL"):
                    if not reg_tenant_id or not reg_company_name or not reg_owner_user or not reg_owner_pass:
                        st.error("❌ Tamam fields fill karna lazmi hain.")
                    elif len(reg_tenant_id) < 3:
                        st.error("❌ Tenant Code kam se kam 3 words ka hona chahiye.")
                    elif len(reg_owner_pass) < 6:
                        st.error("❌ Password kam se kam 6 characters ka hona lazmi hai.")
                    else:
                        try:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = %s", (reg_tenant_id,))
                                    if cursor.fetchone()[0] > 0:
                                        st.error("❌ Unique tenant identifier already registered.")
                                    else:
                                        cursor.execute("""
                                            INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date, license_expiry_date, staff_permissions)
                                            VALUES (%s, %s, %s, %s, FALSE, %s, '', '')
                                        """, (reg_tenant_id, reg_company_name, reg_support_phone, reg_owner_user, datetime.now().strftime("%Y-%m-%d")))
                                        cursor.execute("""
                                            INSERT INTO users (username, password, role, assignedarea, tenant_id)
                                            VALUES (%s, %s, 'Owner', 'ALL', %s)
                                        """, (reg_owner_user, hash_password(reg_owner_pass), reg_tenant_id))
                                        insert_activity_log(reg_tenant_id, reg_owner_user, "REGISTRATION", f"New tenant application generated for {reg_company_name}")
                                        st.success("🎉 Registration Proposal Saved onto Supabase Ledger Engine!")
                                        
                                        alert_payload = f"🔒 LYNX SAAS LICENSE ALERT:\nNew enterprise system activation initiated.\nTenant ID: {reg_tenant_id}\nISP Company: {reg_company_name}"
                                        encoded_msg = urllib.parse.quote(alert_payload)
                                        master_phone = MASTER_NOTIFY_NUMBERS[0]
                                        if master_phone.startswith("0"):
                                            master_phone = master_phone[1:]
                                        st.markdown(f'<a href="https://wa.me/92{master_phone}?text={encoded_msg}" target="_blank" style="background:#10b981; color:white; padding:12px; border-radius:8px; display:block; text-align:center; text-decoration:none; font-weight:bold; margin-bottom:10px;">📲 Dispatch Verification Code</a>', unsafe_allow_html=True)
                        except Exception as ex:
                            st.error(f"Transaction Fault Error: {ex}")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    else:
        routing_node = st.session_state['current_node']

if st.session_state['authenticated'] and not st.session_state['portal_mode']:
    with st.sidebar:
        st.markdown(f"<h2 style='color:#10b981; font-weight:900; text-align:center;'>{str(TENANT_COMPANY_NAME).upper()}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-size:11px;'>Instance: <b>{st.session_state.get('tenant_id', 'lynx')}</b></p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-size:12px; color:#f59e0b;'>⏳ Account Life: <br><b>{license_status_text}</b></p>", unsafe_allow_html=True)
        
        if st.button("📊 Lynx Dashboard", use_container_width=True):
            st.session_state['current_node'] = "📊 Lynx Dashboard"
            st.rerun()
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"
            st.rerun()
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"
            st.rerun()
            
        if str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"]:
            if st.button("🔐 System Access Control", use_container_width=True):
                st.session_state['current_node'] = "🔐 System Access Control"
                st.rerun()
                
        st.write("---")
        username_display = str(st.session_state.get('username', 'UNKNOWN')).upper()
        role_display = str(st.session_state.get('user_role', 'STAFF')).upper()
        st.markdown(f"<p style='text-align:center;'>👤 Active: <b>{username_display}</b><br>📍 Role: <b style='color:#10b981;'>{role_display}</b></p>", unsafe_allow_html=True)
        
        if st.button("🔒 Logout System", use_container_width=True):
            insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "LOGOUT", "User terminated application session manually.")
            st.session_state['authenticated'] = False
            st.rerun()

# ========================================== #
# VIEW 1: LYNX DASHBOARD                     #
# ========================================== #
if routing_node in ["📊 Core Analytics Dashboard", "📊 Lynx Dashboard"]:
    st.markdown(f"<div class='main-title'>⚡ {str(TENANT_COMPANY_NAME).upper()} ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_high_profile = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    cards_display_areas = all_system_areas.copy()
    if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
        cards_display_areas = [a for a in all_system_areas if any(a.lower() == s.lower() for s in st.session_state['assigned_areas'])]
        
    if not all_system_areas:
        st.info("💡 Database mapping is empty. Configure sectors inside System Access Control.")
    elif df_matrix.empty:
        st.warning("⚠️ Operational Database is empty. No subscribers registered.")
    else:
        collection_map = fetch_isolated_billing_summary(st.session_state['tenant_id'])
        st.markdown("### 🌐 Active System Node Overview")
        
        for i in range(0, len(cards_display_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(cards_display_areas):
                    current_hub = cards_display_areas[i + j]
                    segment = df_matrix[df_matrix['area'].str.lower() == current_hub.lower()]
                    active_segment = segment[segment['status'] != 'SUSPENDED']
                    
                    try:
                        hub_bill = int(float(str(active_segment['billamount'].sum())))
                        hub_arrears = int(float(str(segment['balanceshift'].sum())))
                    except Exception:
                        hub_bill = 0
                        hub_arrears = 0
                        
                    hub_paid_count = len(segment[segment['status'] == 'PAID'])
                    hub_partial_count = len(segment[segment['status'] == 'PARTIAL'])
                    hub_unpaid_count = len(segment[segment['status'] == 'UNPAID'])
                    hub_suspended_count = len(segment[segment['status'] == 'SUSPENDED'])
                    
                    hub_uids = [str(x).lower().strip() for x in segment['username'].tolist() if x]
                    hub_collected = sum(collection_map.get(uid, 0) for uid in hub_uids)
                    
                    b_color = "#10b981" if (i+j)%2 == 0 else "#3b82f6"
                    with cols[j]:
                        st.markdown(f"""
                        <div class="system-card" style="border-left: 5px solid {b_color};">
                            <h4>🌐 {current_hub} Overview</h4>
                            <p><b>Total Customers:</b> {len(segment)}</p>
                            <p><b>Expected Revenue:</b> Rs. {hub_bill:,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>✅ Paid Users:</b> {hub_paid_count} (Recv: Rs. {hub_collected:,})</p>
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
        system_filter = st.selectbox("🌐 Area System Filter", filter_options)
        if system_filter != "ALL ASSIGNED SYSTEMS":
            base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]
            
        if not base_df.empty:
            total_active = len(base_df)
            total_paid = len(base_df[base_df['status'] == 'PAID'])
            try:
                total_arrears = int(float(str(base_df['balanceshift'].sum())))
            except Exception:
                total_arrears = 0
            total_suspended = len(base_df[base_df['status'] == 'SUSPENDED'])
            
            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            col_b1.metric("Terminals Active", total_active)
            col_b2.metric("Paid Accounts", total_paid)
            col_b3.metric("Total Arrears", f"Rs. {total_arrears:,}")
            col_b4.metric("Suspended Lines", total_suspended)
            
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
            
            for _, row_series in base_df.iterrows():
                row_dict = row_series.to_dict()
                phone_num = str(row_dict.get('phone', ''))
                pure_digits = re.sub(r"\D", "", phone_num)
                
                if pure_digits.startswith("00"):
                    wa_number = pure_digits[2:]
                elif pure_digits.startswith("0"):
                    wa_number = "92" + pure_digits[1:]
                else:
                    wa_number = pure_digits
                    
                if len(wa_number) >= 10:
                    wa_payload = f"Dear {row_dict.get('customername','')}, {GENERIC_TEXT} Bill Update. Arrears: Rs.{row_dict.get('balanceshift',0)}. Expiry: {row_dict.get('expirydate','')}. Support: {TENANT_SUPPORT_PHONE}"
                    wa_action_html = f'<a href="https://wa.me/{wa_number}?text={urllib.parse.quote(wa_payload)}" target="_blank" class="btn-action btn-w">💬 WA</a>'
                else:
                    wa_action_html = '<span class="btn-action btn-disabled">🚫 WA</span>'
                    
                html_rows.append("<tr>")
                for col in custom_order_cols:
                    raw_val = row_dict.get(col, '')
                    escaped_val = html.escape(str(raw_val))
                    if col == 'username':
                        html_rows.append(f"<td><b>{escaped_val}</b></td>")
                    elif col == 'status':
                        s_color = "#10b981" if raw_val == 'PAID' else ("#f59e0b" if raw_val == 'PARTIAL' else "#f43f5e")
                        html_rows.append(f"<td style='color:{s_color}; font-weight:bold;'>{escaped_val}</td>")
                    elif col == 'balanceshift':
                        html_rows.append(f"<td style='color:#f43f5e; font-weight:bold;'>Rs. {raw_val}</td>")
                    else:
                        html_rows.append(f"<td>{escaped_val}</td>")
                html_rows.append(f'<td><a href="tel:{pure_digits}" class="btn-action btn-c">📞 Call</a> {wa_action_html}</td></tr>')
                
            html_rows.append("</table></div>")
            st.markdown("".join(html_rows), unsafe_allow_html=True)
    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)

# ========================================== #
# VIEW 2: OPERATIONS CENTER (LIVE CALCULATIONS)#
# ========================================== #
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_management = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    if not is_management and "ALL" not in st.session_state['assigned_areas']:
        df_matrix = df_matrix[df_matrix['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
        
    if is_management:
        tabs = st.tabs(["💳 Capital Collection Hub", "➕ Provision New Client", "📥 Bulk Import Excel/CSV", "🛠️ Edit Terminal Profile", "🗑️ Remove Subscriber"])
        tab_col, tab_prov, tab_bulk, tab_edit, tab_del = tabs
    else:
        tabs = st.tabs(["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"])
        tab_col, tab_edit = tabs
        tab_prov = tab_bulk = tab_del = None
    
    sub_map = {}
    if not df_matrix.empty:
        for _, row_series in df_matrix.iterrows():
            row_dict = row_series.to_dict()
            uid = row_dict.get('username')
            if uid:
                sub_map[f"[{uid}] - {row_dict.get('customername', '')}"] = uid
                
    with tab_col:
        if not sub_map:
            st.info("No subscribers found.")
        else:
            target_label = st.selectbox("Select Target Subscriber", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            node_row_dict = df_matrix[df_matrix['username'] == resolved_uid].iloc[0].to_dict()
            
            try:
                base_bill = int(float(str(node_row_dict.get('billamount', 0))))
                base_shift = int(float(str(node_row_dict.get('balanceshift', 0))))
            except Exception:
                base_bill = 0
                base_shift = 0
                
            st.info(f"📊 Plan Rate: Rs. {base_bill:,} | Outstanding Arrears: Rs. {base_shift:,} | Current Expiry: {node_row_dict.get('expirydate')}")
            
            col_op1, col_op2, col_op3 = st.columns(3)
            with col_op1:
                billing_months = st.selectbox("📅 Duration (Advance Months)", [1, 3, 6, 12], key="col_months")
            with col_op2:
                pay_method = st.selectbox("Method Profile", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"])
            with col_op3:
                discount = st.number_input("🎁 Discount Approved (Rs.)", min_value=0, value=0, step=50)
            
            # 🔥 AUTOMATED PERFECT BILLING CALCULATOR ENGINE
            package_total_cost = base_bill * billing_months
            net_payable = package_total_cost + base_shift
            final_due = max(net_payable - discount, 0)
            
            st.markdown("### ⚡ Live Payment Overview Breakdown")
            
            cash_in = st.number_input("Capital Received From Customer (Rs.)", min_value=0, value=final_due)
            
            # Live Status Router Logic
            future_shift = int(final_due - cash_in)
            if future_shift <= 0:
                calculated_status = "PAID"
                status_color = "#10b981"
            elif cash_in > 0:
                calculated_status = "PARTIAL"
                status_color = "#f59e0b"
            else:
                calculated_status = "UNPAID"
                status_color = "#f43f5e"
                
            st.markdown(f"""
            <div class='live-calc-box'>
                <p>📦 <b>Package Extension Charges ({billing_months} Month(s)):</b> Rs. {package_total_cost:,}</p>
                <p>⏮️ <b>Past Arrears Covered:</b> Rs. {base_shift:,}</p>
                <p>🎁 <b>Discount Subtracted:</b> Rs. {discount:,}</p>
                <h4 style='color:#3b82f6;'><b>Net Outstanding Due:</b> Rs. {final_due:,}</h4>
                <hr style='border:1px solid #1f2937;'>
                <h4>🔮 <b>Auto Post Action State:</b> <span style='color:{status_color}; font-weight:bold;'>{calculated_status}</span></h4>
                <p>💾 <b>New Balanceshift/Arrears Log:</b> Rs. {future_shift:,}</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("💳 POST TRANSACTION & EXTEND LINE", use_container_width=True):
                today_dt = datetime.now()
                current_expiry_str = str(node_row_dict.get('expirydate', '')).strip()
                
                # Smart Expiry Calculator: Add to existing expiry if line is active, otherwise start from today
                try:
                    old_expiry_dt = datetime.strptime(current_expiry_str, "%Y-%m-%d")
                    base_dt = today_dt if old_expiry_dt < today_dt else old_expiry_dt
                except Exception:
                    base_dt = today_dt
                    
                new_expiry = (base_dt + relativedelta(months=billing_months)).strftime("%Y-%m-%d")
                invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        # Update customer fields flawlessly based on automatic calculations
                        cursor.execute("""
                            UPDATE customers 
                            SET balanceshift = %s, status = %s, expirydate = %s 
                            WHERE username = %s AND tenant_id = %s
                        """, (future_shift, calculated_status, new_expiry, resolved_uid, st.session_state['tenant_id']))
                        
                        # Post onto transaction history clean ledger logs
                        cursor.execute("""
                            INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven, tenant_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s, %s)
                        """, (invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('phone'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), node_row_dict.get('package'), int(cash_in), future_shift, pay_method, int(discount), st.session_state['tenant_id']))
                
                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "BILL_PAYMENT", f"Staff posted Rs. {cash_in} for user {resolved_uid}. Status updated to {calculated_status}, Arrears set to Rs. {future_shift}, Expiry to {new_expiry}.")
                st.success(f"🎉 Collection Recorded Cleanly! System Class Status: {calculated_status} | Extended To: {new_expiry}")
                
                st.session_state['recent_pdf_bytes'] = generate_receipt_pdf(TENANT_COMPANY_NAME, TENANT_SUPPORT_PHONE, invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('package'), cash_in, future_shift, pay_method)
                st.session_state['recent_invoice_uuid'] = invoice_uuid
                st.cache_data.clear()
                st.rerun()
                
            if 'recent_pdf_bytes' in st.session_state:
                st.download_button("📥 Download Generated PDF Receipt", data=st.session_state['recent_pdf_bytes'], file_name=f"Receipt_{st.session_state.get('recent_invoice_uuid', 'INV')}.pdf", mime="application/pdf", use_container_width=True)
                
    if tab_prov:
        with tab_prov:
            if not all_system_areas:
                st.error("❌ Register an Area Sector inside System Access Controls first.")
            else:
                in_area = st.selectbox("Select Target Hub Location", all_system_areas)
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT packagename, packagerate FROM packages WHERE areaname = %s AND tenant_id = %s", (in_area, st.session_state['tenant_id']))
                        area_pkgs = dict(cur.fetchall())
                        
                in_id = st.text_input("Desired Unique Username Key").strip().lower()
                in_name = st.text_input("Customer Full Name").strip()
                in_phone = st.text_input("Phone Number").strip()
                in_cnic = st.text_input("CNIC Number").strip()
                
                if area_pkgs:
                    chosen_pkg = st.selectbox(f"Valid Packages for {in_area}", list(area_pkgs.keys()))
                    try:
                        suggested_rate = int(float(str(area_pkgs[chosen_pkg])))
                    except Exception:
                        suggested_rate = 1500
                else:
                    chosen_pkg = st.selectbox(f"Valid Packages for {in_area}", ["Standard Manual Baseline"])
                    suggested_rate = 1500
                    
                in_rate = st.number_input("Monthly Plan Bill Amount (Rs.)", min_value=0, value=suggested_rate)
                in_address = st.text_input("Physical Core Address").strip()
                in_sn = st.text_input("ONU Hardware Serial ID").strip()
                
                if st.button("➕ SAVE PROVISION ACCOUNT", use_container_width=True):
                    norm_p = clean_and_validate_phone(in_phone)
                    if not in_id or not in_name or not norm_p:
                        st.error("❌ Structural matching items missing. Customer Name, Username and Phone are required.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("SELECT COUNT(*) FROM customers WHERE username = %s AND tenant_id = %s", (in_id, st.session_state['tenant_id']))
                                if cursor.fetchone()[0] > 0:
                                    st.error("❌ Identity Key / Username duplicate inside logs.")
                                else:
                                    default_expiry = (datetime.now() + relativedelta(months=1)).strftime("%Y-%m-%d")
                                    cursor.execute("""
                                        INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate, tenant_id)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s, %s)
                                    """, (in_id, in_name, norm_p, in_cnic, chosen_pkg, int(in_rate), in_area, in_address, in_sn, default_expiry, st.session_state['tenant_id']))
                                    
                                    insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CREATE_CUSTOMER", f"Allocated new customer terminal profile for {in_id} ({in_name}) inside {in_area}.")
                                    st.success(f"🚀 Profile allocated! Expiry: {default_expiry}.")
                                    st.cache_data.clear()
                                    st.rerun()
                                    
    if tab_bulk:
        with tab_bulk:
            st.markdown("#### 📥 Download Sample Template")
            blueprint_df = pd.DataFrame([{
                "username": "ali786", "customername": "Muhammad Ali", "phone": "03001234567",
                "cnic": "35201-1234567-1", "package": "10 Mbps", "billamount": 1200,
                "area": "Model Town", "address": "House 45-B, Street 3", "onuserialnumber": "ONU-HW-9988X"
            }])
            csv_buffer = io.StringIO()
            blueprint_df.to_csv(csv_buffer, index=False)
            st.download_button(label="📥 DOWNLOAD TEMPLATE FILE", data=csv_buffer.getvalue().encode('utf-8'), file_name="subscriber_template.csv", mime="text/csv", use_container_width=True)
            st.write("---")
            
            uploaded_file = st.file_uploader("Upload Excel/CSV Client Matrix Log", type=['xlsx', 'csv'])
            if uploaded_file:
                try:
                    df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                    if st.button("⚡ Process & Save Uploaded Document"):
                        df_upload.columns = [str(c).lower().replace(" ", "").strip() for c in df_upload.columns]
                        
                        inserted_rows = 0
                        skipped_duplicates = 0
                        failed_rows = 0
                        
                        with st.spinner("Processing Matrix Data..."):
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    for idx, row in df_upload.iterrows():
                                        try:
                                            clean_id = str(row.get('username', '')).strip().lower()
                                            if clean_id == 'nan' or not clean_id: 
                                                failed_rows += 1
                                                continue
                                            
                                            cursor.execute("SELECT COUNT(*) FROM customers WHERE username = %s AND tenant_id = %s", (clean_id, st.session_state['tenant_id']))
                                            if cursor.fetchone()[0] > 0:
                                                skipped_duplicates += 1
                                                continue
                                                
                                            c_name = str(row.get('customername', 'Unknown')).strip()
                                            if c_name.lower() == 'nan': c_name = 'Unknown'
                                            c_phone = clean_and_validate_phone(str(row.get('phone', '')))
                                            c_cnic = str(row.get('cnic', '')).strip()
                                            if c_cnic.lower() == 'nan': c_cnic = ''
                                            c_pkg = str(row.get('package', 'Standard')).strip()
                                            if c_pkg.lower() == 'nan' or not c_pkg: c_pkg = 'Standard'
                                            c_area = str(row.get('area', 'Default')).strip()
                                            if c_area.lower() == 'nan': c_area = 'Default'
                                            c_addr = str(row.get('address', '')).strip()
                                            if c_addr.lower() == 'nan': c_addr = ''
                                            c_onu = str(row.get('onuserialnumber', '')).strip()
                                            if c_onu.lower() == 'nan': c_onu = ''
                                            
                                            raw_amt = str(row.get('billamount', '1500')).strip()
                                            if raw_amt.lower() in ['nan', 'none', '']:
                                                bill_amt = 1500
                                            else:
                                                try:
                                                    bill_amt = int(float(raw_amt))
                                                except:
                                                    bill_amt = 1500
                                                
                                            default_expiry = (datetime.now() + relativedelta(months=1)).strftime("%Y-%m-%d")
                                            
                                            cursor.execute("""
                                                INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate, tenant_id)
                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s, %s)
                                            """, (clean_id, c_name, c_phone, c_cnic, c_pkg, bill_amt, c_area, c_addr, c_onu, default_expiry, st.session_state['tenant_id']))
                                            inserted_rows += 1
                                        except Exception:
                                            failed_rows += 1
                                            
                            insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "BULK_IMPORT", f"Bulk processing - Inserted: {inserted_rows}, Skipped: {skipped_duplicates}, Failures: {failed_rows}")
                            st.success(f"🚀 Matrix Processed Successfully!")
                            st.info(f"📊 Results: {inserted_rows} Added | {skipped_duplicates} Duplicates Skipped | {failed_rows} Blanks Ignored.")
                            st.cache_data.clear()
                except Exception as ex:
                    st.error(f"Critical Upload Error: {ex}")
                    
    with tab_edit:
        if not sub_map:
            st.info("Empty logs.")
        else:
            edit_target = st.selectbox("Modify Identity Key Node", list(sub_map.keys()), key="edit_box")
            edit_uid = sub_map[edit_target]
            edit_row_dict = df_matrix[df_matrix['username'] == edit_uid].iloc[0].to_dict()
            
            with st.form("edit_terminal_form"):
                is_name_disabled = not is_management and not STAFF_PERMISSIONS.get("customername", True)
                is_phone_disabled = not is_management and not STAFF_PERMISSIONS.get("phone", True)
                is_address_disabled = not is_management and not STAFF_PERMISSIONS.get("address", True)
                is_onu_disabled = not is_management and not STAFF_PERMISSIONS.get("onuserialnumber", True)
                is_rate_disabled = not is_management and not STAFF_PERMISSIONS.get("billamount", False)
                is_status_disabled = not is_management and not STAFF_PERMISSIONS.get("status", False)
                
                if not is_management:
                    st.caption("🔒 *Note: Some fields may be locked by the Owner based on your profile permission rules.*")

                up_name = st.text_input("Customer Name", value=edit_row_dict.get('customername'), disabled=is_name_disabled)
                up_phone = st.text_input("Phone Number", value=edit_row_dict.get('phone'), disabled=is_phone_disabled)
                up_address = st.text_input("Address", value=edit_row_dict.get('address'), disabled=is_address_disabled)
                up_sn = st.text_input("ONU SN", value=edit_row_dict.get('onuserialnumber'), disabled=is_onu_disabled)
                
                try:
                    current_rate_val = int(float(str(edit_row_dict.get('billamount', 0))))
                except Exception:
                    current_rate_val = 0
                    
                up_rate = st.number_input("Monthly Rate (Rs.)", value=current_rate_val, disabled=is_rate_disabled)
                
                raw_stat = str(edit_row_dict.get('status', 'UNPAID')).upper()
                safe_stat = raw_stat if raw_stat in ["PAID", "PARTIAL", "UNPAID", "SUSPENDED"] else "UNPAID"
                up_status = st.selectbox("Line Status", ["PAID", "PARTIAL", "UNPAID", "SUSPENDED"], index=["PAID", "PARTIAL", "UNPAID", "SUSPENDED"].index(safe_stat), disabled=is_status_disabled)
                
                if st.form_submit_button("💾 COMMIT MODIFICATIONS"):
                    final_name = edit_row_dict.get('customername') if is_name_disabled else up_name
                    final_phone = edit_row_dict.get('phone') if is_phone_disabled else clean_and_validate_phone(up_phone)
                    final_address = edit_row_dict.get('address') if is_address_disabled else up_address
                    final_sn = edit_row_dict.get('onuserialnumber') if is_onu_disabled else up_sn
                    final_rate = int(current_rate_val) if is_rate_disabled else int(up_rate)
                    final_status = safe_stat if is_status_disabled else up_status

                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE customers SET customername=%s, phone=%s, address=%s, onuserialnumber=%s, billamount=%s, status=%s 
                                WHERE username=%s AND tenant_id=%s
                            """, (final_name, final_phone, final_address, final_sn, final_rate, final_status, edit_uid, st.session_state['tenant_id']))
                            
                    insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "UPDATE_CUSTOMER", f"Modified criteria for customer {edit_uid}. Status set to {final_status}.")
                    st.success("Profile Changes Logged within Tenant context.")
                    st.cache_data.clear()
                    st.rerun()

    if tab_del:
        with tab_del:
            st.markdown("### 🗑️ Permanent Multi-Subscriber Deletion Module")
            if not sub_map:
                st.info("No active terminals to remove.")
            else:
                del_targets = st.multiselect("Select Subscriber Target(s) for Deletion", list(sub_map.keys()), key="del_box")
                if st.button("🗑️ PERMANENTLY REMOVE SELECTED CUSTOMER TERMINALS", type="primary", use_container_width=True):
                    if not del_targets:
                        st.error("❌ Please select at least one subscriber to delete.")
                    else:
                        del_uids = [sub_map[target] for target in del_targets]
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DELETE FROM customers WHERE username = ANY(%s) AND tenant_id = %s", (del_uids, st.session_state['tenant_id']))
                        
                        uids_log_str = ", ".join(del_uids)
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "DELETE_CUSTOMERS", f"Permanently deleted: {uids_log_str}.")
                        st.success(f"✅ Profiles completely purged.")
                        st.cache_data.clear()
                        st.rerun()

# ========================================== #
# VIEW 3: LIFETIME AUDIT LEDGER HISTORY       #
# ========================================== #
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    df_ledger = pd.DataFrame()
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM billing_history WHERE tenant_id = %s ORDER BY datetimestamp DESC", (st.session_state['tenant_id'],))
            l_rows = cur.fetchall()
            if l_rows:
                df_ledger = pd.DataFrame(l_rows)
                
    if df_ledger.empty:
        st.info("No transactional logs found inside your tenant node registry.")
    else:
        df_ledger.columns = [c.lower() for c in df_ledger.columns]
        st.dataframe(df_ledger, use_container_width=True)

# ========================================== #
# VIEW 4: SYSTEM ACCESS CONFIGS              #
# ========================================== #
elif routing_node == "🔐 System Access Control":
    if str(st.session_state.get('user_role', '')).lower() not in ["owner", "admin"]:
        st.error("🔴 Administrative Elevation Clearance Required.")
    else:
        st.markdown("<div class='main-title'>🔐 SYSTEM ACCESS PANEL</div>", unsafe_allow_html=True)
        all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
        
        adm_tabs = st.tabs([
            "👑 SaaS Whitelabel License Manager" if (st.session_state['tenant_id'] == 'lynx' and st.session_state['username'] == 'owner') else "🏢 Branding Metadata Controls",
            "⚙️ Access Accounts Management",
            "📦 Fixed Packages Pricing Matrix",
            "🗺️ Dynamic Area Hubs Sector",
            "🛠️ Core Structural Destruct Engine",
            "📋 System Activity Logs",
            "💾 Data Backup Vault"
        ])
        
        if st.session_state['tenant_id'] == 'lynx' and st.session_state['username'] == 'owner':
            with adm_tabs[0]:
                st.markdown("### 👑 LYNX MASTER CONTROL HUB")
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT * FROM system_tenants ORDER BY registration_date DESC")
                        all_tenants_rows = cur.fetchall()
                        
                if all_tenants_rows:
                    df_tenants_view = pd.DataFrame(all_tenants_rows)
                    st.dataframe(df_tenants_view, use_container_width=True)
                    
                tenant_select_list = [t['tenant_id'] for t in all_tenants_rows if t['tenant_id'] != 'lynx']
                if tenant_select_list:
                    chosen_target_tenant = st.selectbox("Select Target Tenant ID to Modify Access", tenant_select_list)
                    tenant_record = next(item for item in all_tenants_rows if item["tenant_id"] == chosen_target_tenant)
                    current_status = tenant_record["license_active"]
                    current_expiry_val = tenant_record.get("license_expiry_date", "")
                    
                    st.write("---")
                    st.markdown(f"#### ⚙️ Edit Authorization System: `{chosen_target_tenant}`")
                    new_license_toggle = st.checkbox("Grant Premium Software Activation Status", value=current_status)
                    new_expiry_input = st.text_input("Set License Expiry Date (YYYY-MM-DD) [Blank = Lifetime]", value=current_expiry_val)
                    
                    st.markdown("##### 🔑 Master Password Override Tool")
                    new_tenant_pass_force = st.text_input("Force Reset Tenant Admin Password", type="password")
                    
                    if st.button("💾 LOCK CONFIGURATION STATUS KEY"):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE system_tenants SET license_active = %s, license_expiry_date = %s WHERE tenant_id = %s
                                """, (new_license_toggle, new_expiry_input.strip(), chosen_target_tenant))
                                
                                if new_tenant_pass_force.strip():
                                    t_owner = tenant_record["owner_username"]
                                    hashed_f = hash_password(new_tenant_pass_force.strip())
                                    cursor.execute("""
                                        UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s
                                    """, (hashed_f, t_owner, chosen_target_tenant))
                                    st.success(f"🔑 Password updated for owner: `{t_owner}`")
                                    
                        insert_activity_log("lynx", "owner", "MASTER_OVERRIDE", f"Modified tenant `{chosen_target_tenant}`.")
                        st.success("Dynamic access lock state updated.")
                        st.cache_data.clear()
                        st.rerun()
        else:
            with adm_tabs[0]:
                st.markdown("### 🏢 ISP Whitelabel Branding Controls")
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT company_name, support_phone FROM system_tenants WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                        meta_row = cur.fetchone()
                        
                with st.form("tenant_custom_branding_form"):
                    b_name = st.text_input("Company Brand Name Display", value=meta_row["company_name"] if meta_row else TENANT_COMPANY_NAME)
                    b_phone = st.text_input("Official Helpline Reference Phone", value=meta_row["support_phone"] if meta_row else TENANT_SUPPORT_PHONE)
                    if st.form_submit_button("💾 SAVE BRANDING LOGS"):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE system_tenants SET company_name=%s, support_phone=%s WHERE tenant_id=%s", (b_name, b_phone, st.session_state['tenant_id']))
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "UPDATE_BRANDING", f"Name: {b_name}, Hotline: {b_phone}")
                        st.success("Metadata Saved cleanly inside cluster engine.")
                        st.cache_data.clear()
                        st.rerun()
                        
        with adm_tabs[1]:
            st.markdown("### ⚙️ Access Accounts Management & Credentials")
            with st.form("owner_self_password_form"):
                current_self_pass = st.text_input("Enter Current Password Verification", type="password")
                new_self_pass = st.text_input("Enter New Secure Password", type="password")
                if st.form_submit_button("🔒 Securely Change My Password"):
                    if len(new_self_pass) < 6:
                        st.error("Password string too short. Minimum 6 characters required.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("SELECT password FROM users WHERE username = %s AND tenant_id = %s", (st.session_state['username'], st.session_state['tenant_id']))
                                current_pwd_row = cursor.fetchone()
                                if current_pwd_row and verify_password(current_self_pass, current_pwd_row[0]):
                                    cursor.execute("UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s", (hash_password(new_self_pass), st.session_state['username'], st.session_state['tenant_id']))
                                    insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CHANGE_PASSWORD", "System password updated.")
                                    st.success("🎉 Your credentials updated successfully!")
                                else:
                                    st.error("❌ Validation failed.")

            st.write("---")
            st.markdown("#### 🛠️ Configurable Staff Profile Editing Rules")
            with st.form("owner_staff_permissions_form"):
                col_p_a, col_p_b = st.columns(2)
                with col_p_a:
                    p_name_chk = st.checkbox("Allow Editing Customer Name", value=STAFF_PERMISSIONS.get("customername", True))
                    p_phone_chk = st.checkbox("Allow Editing Phone Number", value=STAFF_PERMISSIONS.get("phone", True))
                    p_address_chk = st.checkbox("Allow Editing Physical Address", value=STAFF_PERMISSIONS.get("address", True))
                with col_p_b:
                    p_onu_chk = st.checkbox("Allow Editing ONU Hardware Serial", value=STAFF_PERMISSIONS.get("onuserialnumber", True))
                    p_rate_chk = st.checkbox("Allow Changing Monthly Package Price (Rate)", value=STAFF_PERMISSIONS.get("billamount", False))
                    p_status_chk = st.checkbox("Allow Overriding Status (Paid/Suspended Line)", value=STAFF_PERMISSIONS.get("status", False))
                
                if st.form_submit_button("💾 UPDATE STAFF EDITING PERMISSIONS"):
                    updated_perms = {
                        "customername": p_name_chk,
                        "phone": p_phone_chk,
                        "address": p_address_chk,
                        "onuserialnumber": p_onu_chk,
                        "billamount": p_rate_chk,
                        "status": p_status_chk
                    }
                    perms_json_dump = json.dumps(updated_perms)
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("UPDATE system_tenants SET staff_permissions = %s WHERE tenant_id = %s", (perms_json_dump, st.session_state['tenant_id']))
                    
                    insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "UPDATE_STAFF_RULES", "Owner adjusted staff permissions.")
                    st.success("🎉 Permissions Updated Instantly!")
                    st.cache_data.clear()
                    st.rerun()

            st.write("---")
            st.markdown("#### ➕ Provision Sub-User Entity")
            with st.form("create_subuser_form"):
                new_username = st.text_input("Entity Username ID").strip().lower()
                new_password = st.text_input("Security Access Code / Password", type="password")
                new_role = st.selectbox("System Architecture Role Level", ["Admin", "Staff"])
                selected_clearance = st.multiselect("Allocated Sector Clearance", options=["ALL"] + all_system_areas, default=["ALL"])
                
                if st.form_submit_button("🚀 Create User Profile"):
                    if not new_username or not new_password:
                        st.error("Complete mandatory fields.")
                    else:
                        assigned_areas_str = "ALL" if "ALL" in selected_clearance else ",".join(selected_clearance)
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO users (username, password, role, assignedarea, tenant_id) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (username, tenant_id) DO UPDATE SET password=EXCLUDED.password, role=EXCLUDED.role, assignedarea=EXCLUDED.assignedarea", (new_username, hash_password(new_password), new_role, assigned_areas_str, st.session_state['tenant_id']))
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CREATE_SUB_USER", f"Provisioned sub-user {new_username}")
                        st.success("User configuration posted.")
                        st.cache_data.clear()
                        st.rerun()

            st.write("---")
            st.markdown("#### 👥 Current Staff Directory")
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT username, role, assignedarea FROM users WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                    staff_rows = cur.fetchall()
            
            if staff_rows:
                df_staff = pd.DataFrame(staff_rows)
                df_staff.columns = [c.capitalize() for c in df_staff.columns]
                st.dataframe(df_staff, use_container_width=True)
                deletable_staff = [r['username'] for r in staff_rows if r['username'] != st.session_state['username'] and str(r['role']).lower() != "owner"]
                
                if deletable_staff:
                    st.markdown("##### 🗑️ Terminate Staff Account")
                    del_staff_user = st.selectbox("Select Staff Profile to Disconnect", deletable_staff)
                    if st.button("🗑️ DELETE STAFF PROFILE", type="primary"):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DELETE FROM users WHERE username = %s AND tenant_id = %s", (del_staff_user, st.session_state['tenant_id']))
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "DELETE_SUB_USER", f"Removed staff {del_staff_user}.")
                        st.success(f"✅ Staff connection successfully terminated!")
                        st.rerun()
                        
        with adm_tabs[2]:
            st.markdown("### 📦 Location Pricing Configurator")
            if not all_system_areas:
                st.info("💡 Empty State: Configure an active Operating Area first.")
            else:
                with st.form("matrix_package_form"):
                    p_name = st.text_input("Tarif ID Flag (e.g., 12 Mbps)").strip()
                    p_area = st.selectbox("Target Core Distribution Area Node", all_system_areas)
                    p_rate = st.number_input("Monthly Price Config (Rs.)", min_value=0, value=1500)
                    if st.form_submit_button("💾 LOCK TARIFF MATRIX ENTRY"):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO packages (packagename, areaname, packagerate, tenant_id) VALUES (%s, %s, %s, %s) ON CONFLICT (packagename, areaname, tenant_id) DO UPDATE SET packagerate = EXCLUDED.packagerate", (p_name, p_area, int(p_rate), st.session_state['tenant_id']))
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CREATE_PACKAGE", f"Configured pricing `{p_name}`.")
                        st.success("Configured matrix row entry.")
                        st.cache_data.clear()
                        st.rerun()
            st.write("---")
            st.markdown("#### 🗑️ Remove Package from Matrix")
            all_pkgs_list = fetch_isolated_packages(st.session_state['tenant_id'])
            if all_pkgs_list:
                pkg_options = [f"{pk['packagename']} — Area: {pk['areaname']} (Rs. {pk['packagerate']})" for pk in all_pkgs_list]
                chosen_del_idx = st.selectbox("Select Target Package Profile to Wipe", range(len(pkg_options)), format_func=lambda x: pkg_options[x])
                target_del_pkg = all_pkgs_list[chosen_del_idx]
                
                if st.button("🗑️ PURGE PACKAGE FROM REGISTRY", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                SELECT COUNT(*) FROM customers WHERE LOWER(package) = LOWER(%s) AND LOWER(area) = LOWER(%s) AND tenant_id = %s
                            """, (target_del_pkg['packagename'], target_del_pkg['areaname'], st.session_state['tenant_id']))
                            active_deps = cursor.fetchone()[0]
                            if active_deps > 0:
                                st.error(f"❌ Purge Refused! Active profiles exist.")
                            else:
                                cursor.execute("""
                                    DELETE FROM packages WHERE LOWER(packagename) = LOWER(%s) AND LOWER(areaname) = LOWER(%s) AND tenant_id = %s
                                """, (target_del_pkg['packagename'], target_del_pkg['areaname'], st.session_state['tenant_id']))
                                st.success(f"✅ Package removed successfully!")
                                st.cache_data.clear()
                                st.rerun()
            else:
                st.info("No active packages recorded.")
                
        with adm_tabs[3]:
            st.markdown("### 🗺️ Sector Node Operations")
            with st.form("add_area_sector_form"):
                new_area_name = st.text_input("Enter New Network Location Name").strip()
                if st.form_submit_button("➕ COMMIT SECTOR DEPLOYMENT REGISTRY"):
                    if new_area_name:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO areas VALUES (%s, %s) ON CONFLICT DO NOTHING", (new_area_name, st.session_state['tenant_id']))
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CREATE_AREA", f"Deployed area `{new_area_name}`")
                        st.success("Area logged to network.")
                        st.cache_data.clear()
                        st.rerun()
            st.write("---")
            st.markdown("#### 🗑️ Safe Remove Sector Node")
            if all_system_areas:
                del_area = st.selectbox("Select Target Hub Node to Remove", all_system_areas, key="delete_area_select")
                if st.button("🗑️ PURGE AREA SECTOR FROM REGISTRY", use_container_width=True):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT COUNT(*) FROM customers WHERE LOWER(area) = LOWER(%s) AND tenant_id = %s", (del_area, st.session_state['tenant_id']))
                            assigned_clients = cursor.fetchone()[0]
                            cursor.execute("SELECT COUNT(*) FROM packages WHERE LOWER(areaname) = LOWER(%s) AND tenant_id = %s", (del_area, st.session_state['tenant_id']))
                            linked_packages = cursor.fetchone()[0]
                            
                            if assigned_clients > 0 or linked_packages > 0:
                                st.error(f"❌ Deletion Aborted! Clear dependencies first.")
                            else:
                                cursor.execute("DELETE FROM areas WHERE LOWER(areaname) = LOWER(%s) AND tenant_id = %s", (del_area, st.session_state['tenant_id']))
                                st.success(f"✅ Area wiped cleanly.")
                                st.cache_data.clear()
                                st.rerun()
                                
        with adm_tabs[4]:
            if str(st.session_state.get('user_role', '')).lower() != "owner":
                st.warning("🔒 Section locked. Only the Organization Owner can wipe datasets.")
            else:
                st.markdown("### 🛠️ Tenant Schema Single Destruction Module")
                purge_password = st.text_input("Verify Owner Password Passphrase", type="password", key="purge_pass_gate")
                if st.button("☢️ INITIATE COMPLETE SEGMENT DATA PURGE"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT password FROM users WHERE username = %s AND tenant_id = %s", (st.session_state['username'], st.session_state['tenant_id']))
                            pwd_row = cursor.fetchone()
                            if pwd_row and verify_password(purge_password, pwd_row[0]):
                                cursor.execute("DELETE FROM billing_history WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM customers WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM packages WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM areas WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "DATA_PURGE", "Wiped application instance.")
                                st.success("🚀 Isolated tenant segment data has been cleared cleanly!")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error("❌ Authentication Refused!")
                                
        with adm_tabs[5]:
            st.markdown("### 📋 System Activity & User Login Logs")
            try:
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        if st.session_state['tenant_id'] == 'lynx' and st.session_state['username'] == 'owner':
                            cur.execute("SELECT timestamp, tenant_id, username, action_type, description FROM activity_logs ORDER BY timestamp DESC LIMIT 500")
                        else:
                            cur.execute("SELECT timestamp, username, action_type, description FROM activity_logs WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT 300", (st.session_state['tenant_id'],))
                        log_rows = cur.fetchall()
                        
                if log_rows:
                    df_logs = pd.DataFrame(log_rows)
                    st.dataframe(df_logs, use_container_width=True)
                else:
                    st.info("Abhi tak koi logs jama nahi huay.")
            except Exception as log_err:
                st.error(f"Logs pull karne mein masla aya: {log_err}")
                
        with adm_tabs[-1]:
            st.markdown("### 💾 Dynamic Data Backup Vault")
            is_master_owner = (st.session_state['tenant_id'] == 'lynx' and st.session_state['username'] == 'owner')
            backup_scope = "Tenant Isolated Backup"
            if is_master_owner:
                backup_scope = st.radio("Select Backup Scope", ["Current Tenant Only", "Full Server Master Backup"])
                
            if st.button("⚡ GENERATE SYSTEM BACKUP SNAPSHOT", use_container_width=True):
                with st.spinner("Database snapshot collect kiya ja raha hai..."):
                    try:
                        backup_payload = {}
                        tables = ['system_tenants', 'users', 'customers', 'areas', 'packages', 'billing_history', 'activity_logs']
                        with get_db_connection() as conn:
                            for t_name in tables:
                                q = f"SELECT * FROM {t_name}"
                                params = []
                                if backup_scope == "Tenant Isolated Backup" or not is_master_owner:
                                    q += " WHERE tenant_id = %s"
                                    params.append(st.session_state['tenant_id'])
                                df_bak = pd.read_sql_query(q, conn, params=params)
                                backup_payload[t_name] = df_bak.to_dict(orient='records')
                                
                        st.session_state['safe_backup_json'] = json.dumps(backup_payload, default=str, indent=4)
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "GENERATE_BACKUP", f"Exported state backup.")
                        st.success("✅ Snapshot processed successfully! Niche button se save karein.")
                    except Exception as b_err:
                        st.error(f"Backup Error: {b_err}")
                        
            if 'safe_backup_json' in st.session_state:
                st.download_button(
                    label="📥 DOWNLOAD PREPARED BACKUP FILE (.JSON)",
                    data=st.session_state['safe_backup_json'],
                    file_name=f"Backup_{st.session_state['tenant_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )

# ========================================== #
# VIEW 5: SUBSCRIBER SELF-SERVICE INVENTORY  #
# ========================================== #
elif routing_node == "📱 Client Portal":
    st.markdown(f"<div class='main-title'>📱 SUBSCRIBER SELF-SERVICE PORTAL</div>", unsafe_allow_html=True)
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        portal_tenant = st.text_input("Enter ISP Provider Code").strip().lower()
    with col_p2:
        portal_input = st.text_input("Enter Username / Mobile No.")
        
    if portal_tenant and portal_input:
        t_meta = fetch_active_tenant_metadata(portal_tenant)
        cleaned_p = clean_and_validate_phone(portal_input)
        
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if cleaned_p:
                    cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND (LOWER(username) = LOWER(%s) OR phone = %s)", [portal_tenant, portal_input.strip(), cleaned_p])
                else:
                    cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND LOWER(username) = LOWER(%s)", [portal_tenant, portal_input.strip()])
                c_rows = cur.fetchall()
                
        if not c_rows:
            st.error("❌ No active profile found.")
        else:
            c_dict = c_rows[0]
            try:
                bill_amt_val = int(float(str(c_dict.get('billamount', 0))))
                balance_shift_val = int(float(str(c_dict.get('balanceshift', 0))))
            except Exception:
                bill_amt_val = 0
                balance_shift_val = 0
                
            st.markdown(f"""
            <div class="client-card" style="border: 2px solid #3b82f6;">
                <h2 style="color:#3b82f6; text-align:center; font-weight:bold;">📄 DIGITAL BILL & QUOTATION</h2>
                <p style="text-align:center; color:#9ca3af; font-size:13px;">Provider: {html.escape(str(t_meta["name"]))} | Helpline: {html.escape(str(t_meta["phone"]))}</p>
                <hr style="border: 1px solid #374151;">
                <h3 style="color:#10b981; margin-top:15px;">👤 Account ID: {html.escape(str(c_dict.get('username','')))}</h3>
                <p><b>CUSTOMER NAME:</b> {html.escape(str(c_dict.get('customername','')))}</p>
                <p><b>CONNECTED AREA:</b> {html.escape(str(c_dict.get('area','')))}</p>
                <p><b>ACTIVE PLAN:</b> {html.escape(str(c_dict.get('package','')))}</p>
                <p><b>MONTHLY CHARGES:</b> Rs. {bill_amt_val:,}</p>
                <p style="color:#f43f5e; font-weight:bold;"><b>OUTSTANDING ARREARS:</b> Rs. {balance_shift_val:,}</p>
                <p style="color:#10b981; font-weight:bold;"><b>LINE EXPIRY DATE:</b> {html.escape(str(c_dict.get('expirydate','')))}</p>
            </div>
            """, unsafe_allow_html=True)
    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)