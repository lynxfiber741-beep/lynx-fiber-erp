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
import json
import requests
from datetime import datetime
from contextlib import contextmanager
from dateutil.relativedelta import relativedelta
import bcrypt

# ==========================================
# 🛑 SAAS MASTER CONFIGURATION & HIDDEN REGISTRY
# ==========================================
DISTRIBUTOR_NAME = "Lynx Fiber Internet"
MASTER_NOTIFY_NUMBERS = ["03215943786", "03118808741"]
GENERIC_TEXT = "Lynx Fiber Internet"

DEFAULT_STAFF_PERMS = {
    "customername": True,
    "phone": True,
    "address": True,
    "onuserialnumber": True,
    "billamount": False,
    "status": False
}

DEFAULT_WA_TEMPLATES = {
    "new_connection": "Dear {name}, Welcome to our network! Your new internet profile '{package}' has been successfully activated. Monthly Rate: Rs. {bill}, Expiry Date: {expiry}. Support: {helpline}",
    "bill_paid": "Dear {name},\nThank you for your payment of Rs. {paid} via {method}.\nYour internet package has been renewed.\nNew Expiry Date: {expiry}\nRemaining Arrears: Rs. {arrears}",
    "bill_reminder": "Dear {name}, your {package} internet bill is due. Arrears: Rs. {arrears}. Expiry Date: {expiry}. Please pay promptly to avoid disconnection. Support: {helpline}",
    "expired_warning": "Dear {name}, your internet access has been suspended due to non-payment of Rs. {arrears}. Please clear dues to restore connection immediately. Support: {helpline}"
}

# ==========================================
# 0. CORE PAGE CONFIGURATION (MUST BE FIRST)
# ==========================================
st.set_page_config(
    page_title=f"Enterprise ERP Panel — Powered by {DISTRIBUTOR_NAME}",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# REPORTLAB ENGINE (INTEGRATED RECEIPT GENERATOR)
# ==========================================
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# ==========================================
# 1. CORE CONFIGURATION & SESSION STATE
# ==========================================
if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
if 'user_role' not in st.session_state: st.session_state['user_role'] = ""
if 'username' not in st.session_state: st.session_state['username'] = ""
if 'tenant_id' not in st.session_state: st.session_state['tenant_id'] = "lynx"
if 'assigned_areas' not in st.session_state: st.session_state['assigned_areas'] = ["ALL"]
if 'current_node' not in st.session_state: st.session_state['current_node'] = "📊 Lynx Dashboard"
if 'portal_mode' not in st.session_state: st.session_state['portal_mode'] = False
if 'dashboard_status_filter' not in st.session_state: st.session_state['dashboard_status_filter'] = "ALL"
if 'app_theme' not in st.session_state: st.session_state['app_theme'] = "Dark Nebula (Default)"

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package", "billamount", "area", "address", "onuserialnumber"
]

# ==========================================
# 2. SECURE POOLED DATABASE REGISTRY
# ==========================================
if "DB_URL" in st.secrets:
    DB_URL = st.secrets["DB_URL"]
else:
    st.error("🔴 Critical Configuration Error: 'DB_URL' is missing from Streamlit Secrets!")
    st.stop()

@st.cache_resource
def init_connection_pool():
    try:
        return SimpleConnectionPool(1, 20, dsn=DB_URL)
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
        try: conn.rollback()
        except Exception: pass
        raise e
    finally:
        master_pool.putconn(conn)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try: return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception: return False

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
        pass

def parse_wa_template(template_str, data_dict):
    out = template_str
    for key, val in data_dict.items():
        out = out.replace(f"{{{key}}}", str(val))
    return out

def send_tenant_whatsapp(tenant_metadata, phone_number, template_key, context_data):
    if not tenant_metadata.get("wa_enabled"): return False
    instance_id = tenant_metadata.get("wa_instance_id")
    api_token = tenant_metadata.get("wa_token")
    if not instance_id or not api_token: return False
    
    templates = DEFAULT_WA_TEMPLATES.copy()
    if tenant_metadata.get("wa_templates"):
        try: templates.update(json.loads(tenant_metadata["wa_templates"]))
        except Exception: pass
        
    raw_message = templates.get(template_key, DEFAULT_WA_TEMPLATES.get(template_key, ""))
    if not raw_message: return False
    
    context_data.setdefault("helpline", tenant_metadata.get("phone", ""))
    formatted_message = parse_wa_template(raw_message, context_data)
    
    clean_phone = phone_number.replace("-", "").strip()
    if clean_phone.startswith("0"):
        clean_phone = "92" + clean_phone[1:]
        
    url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{api_token}"
    payload = { "chatId": f"{clean_phone}@c.us", "message": formatted_message }
    try:
        requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
        return True
    except Exception:
        return False

def generate_receipt_pdf(company_name, phone_ref, inv_id, c_id, c_name, area, package, paid, arrears, method):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#10b981'), alignment=TA_CENTER, spaceAfter=10)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontSize=10, textColor=colors.gray, alignment=TA_CENTER, spaceAfter=20)
    normal_style = ParagraphStyle('NormStyle', parent=styles['Normal'], fontSize=11, leading=16, textColor=colors.HexColor('#111827'))
    
    def escape_xml(txt): return html.escape(str(txt))
    try:
        paid_val = int(float(str(paid)))
        arrears_val = int(float(str(arrears)))
    except Exception:
        paid_val = 0; arrears_val = 0
        
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

# ==========================================
# 3. AUTO-REPAIR MULTI-TENANT SCHEMA ENGINE
# ==========================================
def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_tenants (
                    tenant_id TEXT PRIMARY KEY, company_name TEXT NOT NULL, support_phone TEXT NOT NULL, owner_username TEXT NOT NULL,
                    license_active BOOLEAN DEFAULT FALSE, registration_date TEXT NOT NULL, license_expiry_date TEXT NOT NULL DEFAULT '',
                    staff_permissions TEXT DEFAULT '', whatsapp_instance_id TEXT DEFAULT '', whatsapp_token TEXT DEFAULT '',
                    whatsapp_enabled BOOLEAN DEFAULT FALSE, whatsapp_templates TEXT DEFAULT ''
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL, assignedarea TEXT DEFAULT 'ALL', tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    username TEXT NOT NULL, customername TEXT NOT NULL, phone TEXT NOT NULL, cnic TEXT DEFAULT '', package TEXT NOT NULL,
                    billamount INTEGER NOT NULL DEFAULT 0, area TEXT NOT NULL, address TEXT DEFAULT '', onuserialnumber TEXT DEFAULT '',
                    balanceshift INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'UNPAID', expirydate TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            cursor.execute("CREATE TABLE IF NOT EXISTS areas ( areaname TEXT NOT NULL, tenant_id TEXT NOT NULL DEFAULT 'lynx', PRIMARY KEY (areaname, tenant_id) )")
            cursor.execute("CREATE TABLE IF NOT EXISTS packages ( packagename TEXT NOT NULL, areaname TEXT NOT NULL, packagerate INTEGER NOT NULL DEFAULT 0, tenant_id TEXT NOT NULL DEFAULT 'lynx', PRIMARY KEY (packagename, areaname, tenant_id) )")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    invoiceid TEXT PRIMARY KEY, customerid TEXT NOT NULL, customername TEXT NOT NULL, area TEXT NOT NULL, phone TEXT,
                    datetimestamp TEXT NOT NULL, currentpackage TEXT NOT NULL, amountpaid INTEGER NOT NULL DEFAULT 0, remainingarrears INTEGER NOT NULL,
                    transactiontype TEXT NOT NULL, paymentmethod TEXT NOT NULL, discountgiven INTEGER DEFAULT 0, tenant_id TEXT NOT NULL DEFAULT 'lynx'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, username TEXT NOT NULL, action_type TEXT NOT NULL, description TEXT NOT NULL, timestamp TEXT NOT NULL DEFAULT ''
                )
            """)
            cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date, whatsapp_templates)
                    VALUES ('lynx', 'Lynx Fiber Pvt Ltd', '03135776263', 'owner', TRUE, %s, %s)
                """, (datetime.now().strftime("%Y-%m-%d"), json.dumps(DEFAULT_WA_TEMPLATES)))
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner' AND tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users (username, password, role, assignedarea, tenant_id) VALUES ('owner', %s, 'Owner', 'ALL', 'lynx')", (hash_password('lynxowner123'),))

def run_live_migrations():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS timestamp TEXT NOT NULL DEFAULT '';")
                cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS staff_permissions TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_instance_id TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_token TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_enabled BOOLEAN DEFAULT FALSE;")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_templates TEXT DEFAULT '';")
    except Exception: pass

@st.cache_resource
def initialize_application_database():
    build_database_schema()

initialize_application_database()
run_live_migrations()

# ==========================================
# 4. DATA RETRIEVAL LAYERS
# ==========================================
@st.cache_data(ttl=1)
def fetch_active_tenant_metadata(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT company_name, support_phone, license_active, license_expiry_date, staff_permissions, whatsapp_instance_id, whatsapp_token, whatsapp_enabled, whatsapp_templates FROM system_tenants WHERE tenant_id = %s", (tenant_id,))
                res = cur.fetchone()
                if res:
                    perms = DEFAULT_STAFF_PERMS.copy()
                    if res.get("staff_permissions"):
                        try: perms.update(json.loads(res["staff_permissions"]))
                        except Exception: pass
                    wa_templates_raw = res.get("whatsapp_templates", "")
                    if not wa_templates_raw or wa_templates_raw.strip() == "":
                        wa_templates_raw = json.dumps(DEFAULT_WA_TEMPLATES)
                    return {
                        "name": res["company_name"], "phone": res["support_phone"], "active": res["license_active"], "expiry_date": res.get("license_expiry_date", ""),
                        "staff_permissions": perms, "wa_instance_id": res.get("whatsapp_instance_id", ""), "wa_token": res.get("whatsapp_token", ""),
                        "wa_enabled": res.get("whatsapp_enabled", False), "wa_templates": wa_templates_raw
                    }
    except Exception: pass
    return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True, "expiry_date": "", "staff_permissions": DEFAULT_STAFF_PERMS, "wa_instance_id": "", "wa_token": "", "wa_enabled": False, "wa_templates": json.dumps(DEFAULT_WA_TEMPLATES)}

def calculate_license_days(expiry_str):
    if not expiry_str or expiry_str.strip() == "": return "Lifetime Plan Active", True
    try:
        expiry_dt = datetime.strptime(expiry_str.strip(), "%Y-%m-%d")
        time_diff = expiry_dt.replace(hour=23, minute=59, second=59) - datetime.now()
        if time_diff.total_seconds() <= 0: return "Expired", False
        return f"{time_diff.days} Days Remaining" if time_diff.days >= 1 else "Last Day Active", True
    except Exception: return "Invalid Mapping", False

tenant_meta = fetch_active_tenant_metadata(st.session_state['tenant_id'])
TENANT_COMPANY_NAME = tenant_meta["name"]
TENANT_SUPPORT_PHONE = tenant_meta["phone"]
STAFF_PERMISSIONS = tenant_meta["staff_permissions"]
license_status_text, is_license_valid = calculate_license_days(tenant_meta.get("expiry_date", ""))

if not tenant_meta["active"] or not is_license_valid:
    st.error(f"⚠️ 🔐 SOFTWARE LICENSE SUSPENDED OR EXPIRED! Status: {license_status_text}.")
    st.stop()

@st.cache_data(ttl=1)
def fetch_isolated_matrix(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE tenant_id = %s ORDER BY customername ASC", (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    df = pd.DataFrame(rows)
                    df.columns = [c.lower() for c in df.columns]
                    df['balanceshift'] = pd.to_numeric(df['balanceshift'], errors='coerce').fillna(0).astype(int)
                    df['billamount'] = pd.to_numeric(df['billamount'], errors='coerce').fillna(0).astype(int)
                    return df.reindex(columns=GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER])
    except Exception: pass
    return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate', 'tenant_id'])

@st.cache_data(ttl=2)
def fetch_isolated_areas(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT areaname FROM areas WHERE tenant_id = %s ORDER BY areaname ASC", (tenant_id,))
                return [r[0] for r in cur.fetchall()]
    except Exception: return []

@st.cache_data(ttl=2)
def fetch_isolated_packages(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT packagename, areaname, packagerate FROM packages WHERE tenant_id = %s ORDER BY packagename ASC", (tenant_id,))
                return cur.fetchall()
    except Exception: return []

@st.cache_data(ttl=1)
def fetch_isolated_billing_summary(tenant_id):
    try:
        current_month_str = datetime.now().strftime("%Y-%m")
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT LOWER(TRIM(customerid)) as customerid, amountpaid FROM billing_history WHERE tenant_id = %s AND datetimestamp LIKE %s", (tenant_id, current_month_str + '%'))
                rows = cur.fetchall()
                if rows: return pd.DataFrame(rows).groupby('customerid')['amountpaid'].sum().to_dict()
    except Exception: pass
    return {}

def clean_and_validate_phone(phone_str: str) -> str:
    if not phone_str or str(phone_str).lower() == 'nan': return ""
    cleaned = re.sub(r"\D", "", str(phone_str).strip().split('.')[0])
    if cleaned.startswith("0"): return cleaned
    if len(cleaned) == 10 and cleaned.startswith("3"): return "0" + cleaned
    return cleaned

# ==========================================
# 4.5. THEME ENGINE & CSS GENERATOR
# ==========================================
THEMES = {
    "Dark Nebula (Default)": {"bg": "#0b0f19", "sidebar_bg": "#111827", "text": "#e5e7eb", "heading": "#10b981", "accent": "#3b82f6", "card_bg": "#1f2937", "table_th": "#1f2937", "table_td": "#111827", "border": "#374151", "input_bg": "#ffffff", "input_text": "#000000", "login_box_border": "#10b981"},
    "Light Corporate": {"bg": "#f8fafc", "sidebar_bg": "#ffffff", "text": "#1e293b", "heading": "#059669", "accent": "#2563eb", "card_bg": "#ffffff", "table_th": "#e2e8f0", "table_td": "#ffffff", "border": "#cbd5e1", "input_bg": "#f1f5f9", "input_text": "#0f172a", "login_box_border": "#2563eb"}
}
active_theme = THEMES.get(st.session_state['app_theme'], THEMES["Dark Nebula (Default)"])

st.markdown(f"""
<style>
    .stApp {{ background-color: {active_theme['bg']}; color: {active_theme['text']}; font-family: sans-serif; }}
    [data-testid="stSidebar"] {{ background-color: {active_theme['sidebar_bg']}; border-right: 1px solid {active_theme['border']}; }}
    div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea {{ color: {active_theme['input_text']} !important; background-color: {active_theme['input_bg']} !important; font-weight: bold !important; border: 2px solid {active_theme['accent']} !important; border-radius: 8px !important; }}
    .main-title {{ color: {active_theme['heading']}; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }}
    .system-card {{ background: {active_theme['card_bg']}; border: 1px solid {active_theme['border']}; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }}
    .system-card h4 {{ margin: 0 0 10px 0; color: {active_theme['accent']}; }}
    .live-calc-box {{ background-color: {active_theme['bg']}; border: 2px dashed {active_theme['heading']}; padding: 15px; border-radius: 10px; margin-bottom: 15px; }}
    .inline-user-row {{ background-color: {active_theme['card_bg']}; padding: 12px; border-radius: 8px; border: 1px solid {active_theme['border']}; margin-bottom: 8px; }}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 5. PORTAL SECURITY ROUTING ENGINE
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
        login_tab, register_tab = st.tabs(["🔒 Secure Login Portal", "➕ Register New ISP Application"])
        with login_tab:
            input_tenant = st.text_input("Tenant Domain ID", key="log_tenant").strip().lower()
            user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
            pass_input = st.text_input("Security Password", type="password", key="front_pass")
            if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
                with get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT role, username, assignedarea, password FROM users WHERE LOWER(username) = %s AND tenant_id = %s", (user_input, input_tenant))
                        user_match = cursor.fetchone()
                        if user_match and verify_password(pass_input, user_match[3]):
                            st.session_state['authenticated'] = True
                            st.session_state['user_role'] = user_match[0]
                            st.session_state['username'] = user_match[1]
                            st.session_state['tenant_id'] = input_tenant
                            st.session_state['assigned_areas'] = ["ALL"] if user_match[2] == "ALL" else [a.strip() for a in user_match[2].split(",") if a.strip()]
                            st.session_state['current_node'] = "📊 Lynx Dashboard"
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("❌ Invalid Credentials.")
        st.stop()
    else:
        routing_node = st.session_state['current_node']
        with st.sidebar:
            st.markdown(f"## {str(TENANT_COMPANY_NAME).upper()}")
            if st.button("📊 Lynx Dashboard", use_container_width=True): st.session_state['current_node'] = "📊 Lynx Dashboard"; st.rerun()
            if st.button("👥 Operational Billing Center", use_container_width=True): st.session_state['current_node'] = "👥 Operational Billing Center"; st.rerun()
            if st.button("📜 Lifetime Ledger History", use_container_width=True): st.session_state['current_node'] = "📜 Lifetime Ledger History"; st.rerun()
            if str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"]:
                if st.button("🔐 System Access Control", use_container_width=True): st.session_state['current_node'] = "🔐 System Access Control"; st.rerun()
            if st.button("🔒 Logout System", use_container_width=True):
                st.session_state['authenticated'] = False
                st.rerun()

# ==========================================
# HELPER ACTIONS FOR INLINE PROCESSING
# ==========================================
def process_inline_payment(uid, row_data, months, gateway, disc, cash_received, tenant_meta_ctx):
    base_bill = int(row_data['billamount'])
    base_shift = int(row_data['balanceshift'])
    total_cost = base_bill * months
    net_payable = max((total_cost + base_shift) - disc, 0)
    future_shift = int(net_payable - cash_received)
    calculated_status = "PAID" if future_shift <= 0 else ("PARTIAL" if cash_received > 0 else "UNPAID")
    
    old_expiry_str = str(row_data.get('expirydate', '')).strip()
    try: old_expiry_dt = datetime.strptime(old_expiry_str, "%Y-%m-%d")
    except Exception: old_expiry_dt = datetime.now()
    base_dt = datetime.now() if old_expiry_dt < datetime.now() else old_expiry_dt
    new_expiry = (base_dt + relativedelta(months=months)).strftime("%Y-%m-%d")
    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
    
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s AND tenant_id = %s", (future_shift, calculated_status, new_expiry, uid, st.session_state['tenant_id']))
            cursor.execute("""
                INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s, %s)
            """, (invoice_uuid, uid, row_data['customername'], row_data['area'], row_data['phone'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), row_data['package'], int(cash_received), future_shift, gateway, int(disc), st.session_state['tenant_id']))
    
    wa_context = {"name": row_data['customername'], "username": uid, "package": row_data['package'], "paid": int(cash_received), "arrears": future_shift, "expiry": new_expiry, "method": gateway}
    send_tenant_whatsapp(tenant_meta_ctx, row_data['phone'], "bill_paid", wa_context)
    return invoice_uuid, future_shift, new_expiry, cash_received, gateway

def process_inline_reversal(uid, row_data):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT invoiceid, amountpaid, remainingarrears, discountgiven, currentpackage FROM billing_history WHERE customerid = %s AND tenant_id = %s AND transactiontype = 'BILL_PAYMENT' ORDER BY datetimestamp DESC LIMIT 1", (uid, st.session_state['tenant_id']))
            last_invoice = cur.fetchone()
            if not last_invoice:
                return False, "Is customer ki koi payment history nahi mili."
            
            cur.execute("SELECT remainingarrears FROM billing_history WHERE customerid = %s AND tenant_id = %s AND invoiceid != %s ORDER BY datetimestamp DESC LIMIT 1", (uid, st.session_state['tenant_id'], last_invoice['invoiceid']))
            prev_row = cur.fetchone()
            
            base_bill = int(row_data['billamount']) if int(row_data['billamount']) > 0 else 1500
            total_credited = int(last_invoice['amountpaid']) + int(last_invoice['discountgiven'])
            est_months = max(1, int(round(total_credited / base_bill)))
            
            restored_arrears = prev_row['remainingarrears'] if prev_row else max(int(last_invoice['remainingarrears']) - (base_bill * est_months) + total_credited, 0)
            
            try:
                curr_exp_dt = datetime.strptime(str(row_data['expirydate']).strip(), "%Y-%m-%d")
                restored_expiry = (curr_exp_dt - relativedelta(months=est_months)).strftime("%Y-%m-%d")
            except Exception: restored_expiry = datetime.now().strftime("%Y-%m-%d")
            
            cur.execute("UPDATE customers SET balanceshift = %s, status = 'UNPAID', expirydate = %s WHERE username = %s AND tenant_id = %s", (restored_arrears, restored_expiry, uid, st.session_state['tenant_id']))
            cur.execute("DELETE FROM billing_history WHERE invoiceid = %s AND tenant_id = %s", (last_invoice['invoiceid'], st.session_state['tenant_id']))
            return True, f"Invoice {last_invoice['invoiceid']} reversed! Arrears: Rs. {restored_arrears}, Expiry Rolled Back to {restored_expiry}."

# ==========================================
# VIEW 1: LYNX DASHBOARD
# ==========================================
if routing_node in ["📊 Core Analytics Dashboard", "📊 Lynx Dashboard"]:
    st.markdown(f"<div class='main-title'>⚡ {str(TENANT_COMPANY_NAME).upper()} ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_high_profile = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    cards_display_areas = all_system_areas.copy()
    if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
        cards_display_areas = [a for a in all_system_areas if any(a.lower() == s.lower() for s in st.session_state['assigned_areas'])]
        
    if not all_system_areas: st.info("💡 Database sectors list configuration empty.")
    elif df_matrix.empty: st.warning("⚠️ Operational Database is empty.")
    else:
        collection_map = fetch_isolated_billing_summary(st.session_state['tenant_id'])
        
        # Grid Metric Summary
        st.markdown("### 🌐 System Node Overview")
        for i in range(0, len(cards_display_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(cards_display_areas):
                    current_hub = cards_display_areas[i + j]
                    segment = df_matrix[df_matrix['area'].str.lower() == current_hub.lower()]
                    active_seg = segment[segment['status'] != 'SUSPENDED']
                    
                    hub_bill = int(active_seg['billamount'].sum())
                    hub_arrears = int(segment['balanceshift'].sum())
                    hub_uids = [str(x).lower().strip() for x in segment['username'].tolist() if x]
                    hub_collected = sum(collection_map.get(uid, 0) for uid in hub_uids)
                    
                    with cols[j]:
                        st.markdown(f"""
                            <div class="system-card" style="border-left: 5px solid {active_theme['heading']};">
                                <h4>🌐 {current_hub} Node Summary</h4>
                                <p>Total Subs: <b>{len(segment)}</b> | Revenue Target: <b>Rs. {hub_bill:,}</b></p>
                                <p style="color:#10b981;">Collection Collected: <b>Rs. {hub_collected:,}</b></p>
                                <p style="color:#f43f5e;">Outstanding Arrears Logged: <b>Rs. {hub_arrears:,}</b></p>
                            </div>
                        """, unsafe_allow_html=True)
                        
        st.write("---")
        base_df = df_matrix.copy()
        if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
            base_df = base_df[base_df['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
            
        system_filter = st.selectbox("🌐 Location Segment Filter", ["ALL ASSIGNED SYSTEMS"] + cards_display_areas)
        if system_filter != "ALL ASSIGNED SYSTEMS":
            base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]
            
        total_active = len(base_df)
        total_paid = len(base_df[base_df['status'] == 'PAID'])
        total_unpaid = len(base_df[base_df['status'].isin(['UNPAID', 'PARTIAL', 'SUSPENDED'])])
        total_arrears = int(base_df['balanceshift'].sum())
        
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        with metric_col1:
            if st.button(f"🌐 All Directories ({total_active})", use_container_width=True): st.session_state['dashboard_status_filter'] = "ALL"; st.rerun()
        with metric_col2:
            if st.button(f"✅ Paid Users ({total_paid})", use_container_width=True): st.session_state['dashboard_status_filter'] = "PAID"; st.rerun()
        with metric_col3:
            if st.button(f"❌ Defaulter / Unpaid ({total_unpaid})", use_container_width=True): st.session_state['dashboard_status_filter'] = "UNPAID_ANY"; st.rerun()
        with metric_col4:
            st.metric("Total Outstanding Arrears", f"Rs. {total_arrears:,}")
            
        active_filter_state = st.session_state['dashboard_status_filter']
        if active_filter_state == "PAID": base_df = base_df[base_df['status'] == 'PAID'].copy()
        elif active_filter_state == "UNPAID_ANY": base_df = base_df[base_df['status'].isin(['UNPAID', 'PARTIAL', 'SUSPENDED'])].copy()
        
        search_query = st.text_input("🔍 Fast Find Row Analyzer (Username, Name, Phone)")
        if search_query:
            clean_q = search_query.lower().strip()
            base_df = base_df[base_df.astype(str).apply(lambda row: ' '.join(row).lower(), axis=1).str.contains(clean_q, regex=False)].copy()
            
        # NATIVE STREAMLIT INTERACTIVE USER ROW RENDERING ENGINE
        st.markdown("### 📋 Customer Profile Terminals")
        if base_df.empty:
            st.info("Is segment filter matrix mein koi user record maujood nahi hai.")
        else:
            for idx, row in base_df.iterrows():
                uid_key = row['username']
                c_status = str(row['status']).upper()
                s_color = "#10b981" if c_status == 'PAID' else ("#f59e0b" if c_status == 'PARTIAL' else "#f43f5e")
                
                # HTML presentation template for header meta
                st.markdown(f"""
                <div class="inline-user-row">
                    <span style="font-size:16px;">👤 <b>{row['customername']}</b> (<code style="color:#3b82f6;">{uid_key}</code>)</span> | 
                    Hub: <b>{row['area']}</b> | Plan: <b>{row['package']}</b> | Monthly Rate: <b>Rs. {row['billamount']:,}</b> | 
                    Arrears: <span style="color:#f43f5e; font-weight:bold;">Rs. {row['balanceshift']:,}</span> | 
                    Status: <span style="color:{s_color}; font-weight:bold;">{c_status}</span> | Expiry: <b>{row['expirydate']}</b>
                </div>
                """, unsafe_allow_html=True)
                
                # Row Action Buttons layout
                btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns([1, 1, 1.5, 1.5, 3])
                with btn_col1:
                    pure_p = re.sub(r"\D", "", str(row['phone']))
                    st.markdown(f'<a href="tel:{pure_p}" style="text-decoration:none;"><button style="width:100%; border-radius:6px; background-color:#2563eb; color:white; border:none; padding:4px;">📞 Call</button></a>', unsafe_allow_html=True)
                with btn_col2:
                    wa_dig = pure_p[1:] if pure_p.startswith("0") else pure_p
                    st.markdown(f'<a href="https://wa.me/92{wa_dig}" target="_blank" style="text-decoration:none;"><button style="width:100%; border-radius:6px; background-color:#16a34a; color:white; border:none; padding:4px;">💬 WA</button></a>', unsafe_allow_html=True)
                    
                with btn_col3:
                    # Direct payment control trigger inside Dashboard row loop
                    pay_click = st.button("💳 Direct Pay", key=f"pay_inline_{uid_key}", use_container_width=True)
                with btn_col4:
                    # Direct payment rollback control trigger inside Dashboard row loop
                    undo_click = st.button("🔄 Undo Last", key=f"undo_inline_{uid_key}", use_container_width=True)
                    
                # Action Block Toggles
                if pay_click:
                    st.session_state[f"active_pay_block_{uid_key}"] = not st.session_state.get(f"active_pay_block_{uid_key}", False)
                    st.session_state[f"active_undo_block_{uid_key}"] = False
                if undo_click:
                    st.session_state[f"active_undo_block_{uid_key}"] = not st.session_state.get(f"active_undo_block_{uid_key}", False)
                    st.session_state[f"active_pay_block_{uid_key}"] = False
                    
                # Conditional Inline Payment Expandable Container
                if st.session_state.get(f"active_pay_block_{uid_key}", False):
                    with st.container():
                        st.markdown(f"<div style='background-color:{active_theme['table_th']}; padding:15px; border-radius:8px; border:1px dashed {active_theme['accent']}; margin-bottom:10px;'>", unsafe_allow_html=True)
                        st.subheader(f"⚡ Fast Billing Payment Desk: {row['customername']}")
                        
                        iop1, iop2, iop3 = st.columns(3)
                        with iop1: imonths = st.selectbox("Duration Months", [1,3,6,12], key=f"in_m_{uid_key}")
                        with iop2: igateway = st.selectbox("Gateway", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"], key=f"in_g_{uid_key}")
                        with iop3: idisc = st.number_input("Discount Approved (Rs.)", min_value=0, step=50, key=f"in_d_{uid_key}")
                        
                        net_due = max(((int(row['billamount']) * imonths) + int(row['balanceshift'])) - idisc, 0)
                        icash = st.number_input("Cash Received From Subscriber", min_value=0, value=int(net_due), key=f"in_c_{uid_key}")
                        
                        if st.button("Confirm & Post Cash Remittance", key=f"in_sub_{uid_key}", type="primary"):
                            inv_uuid, f_shift, f_exp, f_paid, f_meth = process_inline_payment(uid_key, row, imonths, igateway, idisc, icash, tenant_meta)
                            st.success(f"🎉 Bill Collection successful! Status saved. Extended to: {f_exp}")
                            insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "BILL_PAYMENT", f"Inline fast panel posted Rs. {f_paid} via {f_meth} for customer {uid_key}")
                            st.session_state[f"pdf_bytes_{uid_key}"] = generate_receipt_pdf(TENANT_COMPANY_NAME, TENANT_SUPPORT_PHONE, inv_uuid, uid_key, row['customername'], row['area'], row['package'], f_paid, f_shift, f_meth)
                            st.cache_data.clear()
                            st.rerun()
                            
                        if f"pdf_bytes_{uid_key}" in st.session_state:
                            st.download_button("📥 Download PDF Digital Receipt", data=st.session_state[f"pdf_bytes_{uid_key}"], file_name=f"Receipt_{uid_key}.pdf", mime="application/pdf")
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                # Conditional Inline Payment Reversal/Undo Container
                if st.session_state.get(f"active_undo_block_{uid_key}", False):
                    with st.container():
                        st.markdown(f"<div style='background-color:{active_theme['table_th']}; padding:15px; border-radius:8px; border:1px dashed #f43f5e; margin-bottom:10px;'>", unsafe_allow_html=True)
                        st.markdown(f"⚠️ **Kya aap waqai user `{uid_key}` ki aakhri billing transaction ko reverse / delete karna chahte hain?**")
                        st.caption("Yeh action billing history se entry ura dega aur purana balance wapas account mein shift kar dega.")
                        if st.button("🚨 Haan, Mistaken Entry Undo Karein", key=f"in_rev_btn_{uid_key}", use_container_width=True):
                            success_v, msg_v = process_inline_reversal(uid_key, row)
                            if success_v:
                                st.success(msg_v)
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "REVERSE_PAYMENT", f"Inline fast dashboard configuration reversed last invoice context for subscriber: {uid_key}")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(msg_v)
                        st.markdown("</div>", unsafe_allow_html=True)
                st.write("---")
    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONS CENTER
# ==========================================
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_management = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    if not is_management and "ALL" not in st.session_state['assigned_areas']:
        df_matrix = df_matrix[df_matrix['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
        
    tabs = st.tabs(["💳 Capital Collection Hub", "🔄 Provision New Client", "📥 Bulk Import Excel/CSV", "🛠️ Edit Terminal Profile"]) if is_management else st.tabs(["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"])
    tab_col = tabs[0]
    
    sub_map = {f"[{r['username']}] - {r['customername']}": r['username'] for _, r in df_matrix.iterrows() if r['username']} if not df_matrix.empty else {}
    
    with tab_col:
        if not sub_map: st.info("No subscribers registered.")
        else:
            target_label = st.selectbox("Select Target Subscriber Profile", list(sub_map.keys()))
            resolved_uid = sub_map[target_label]
            node_row_dict = df_matrix[df_matrix['username'] == resolved_uid].iloc[0].to_dict()
            
            st.info(f"📊 Rate: Rs. {node_row_dict['billamount']:,} | Arrears: Rs. {node_row_dict['balanceshift']:,} | Expiry: {node_row_dict['expirydate']}")
            col_op1, col_op2, col_op3 = st.columns(3)
            with col_op1: billing_months = st.selectbox("Duration (Advance Months)", [1, 3, 6, 12])
            with col_op2: pay_method = st.selectbox("Method Profile Gateway", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"])
            with col_op3: discount = st.number_input("Discount Approved (Rs.)", min_value=0, value=0, step=50)
            
            final_due = max(((int(node_row_dict['billamount']) * billing_months) + int(node_row_dict['balanceshift'])) - discount, 0)
            cash_in = st.number_input("Capital Received (Rs.)", min_value=0, value=final_due)
            future_shift = int(final_due - cash_in)
            
            if st.button("💳 POST TRANSACTION & EXTEND LINE", use_container_width=True):
                inv_uuid, f_s, f_e, f_p, f_m = process_inline_payment(resolved_uid, node_row_dict, billing_months, pay_method, discount, cash_in, tenant_meta)
                st.success(f"Collection Recorded cleanly! Extended To: {f_e}")
                st.session_state['recent_pdf_bytes'] = generate_receipt_pdf(TENANT_COMPANY_NAME, TENANT_SUPPORT_PHONE, inv_uuid, resolved_uid, node_row_dict['customername'], node_row_dict['area'], node_row_dict['package'], f_p, f_s, f_m)
                st.session_state['recent_invoice_uuid'] = inv_uuid
                st.cache_data.clear()
                st.rerun()
                
            if 'recent_pdf_bytes' in st.session_state:
                st.download_button("📥 Download Generated PDF Receipt", data=st.session_state['recent_pdf_bytes'], file_name=f"Receipt_{st.session_state.get('recent_invoice_uuid')}.pdf", mime="application/pdf", use_container_width=True)

    if is_management:
        tab_prov, tab_bulk, tab_edit = tabs[1], tabs[2], tabs[3]
        with tab_prov:
            if not all_system_areas: st.error("Register an Area Node sector first.")
            else:
                in_area = st.selectbox("Select Target Hub Location", all_system_areas)
                in_id = st.text_input("Desired Unique Username Key").strip().lower()
                in_name = st.text_input("Customer Full Name").strip()
                in_phone = st.text_input("Phone Number Reference").strip()
                in_pkg = st.text_input("Subscribed Package Standard").strip()
                in_rate = st.number_input("Monthly Rate Price Config", min_value=0, value=1500)
                
                if st.button("➕ SAVE PROVISION ACCOUNT", use_container_width=True):
                    norm_p = clean_and_validate_phone(in_phone)
                    if not in_id or not in_name or not norm_p: st.error("Mandatory structural input metrics missing.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                default_expiry = (datetime.now() + relativedelta(months=1)).strftime("%Y-%m-%d")
                                cursor.execute("""
                                    INSERT INTO customers (username, customername, phone, package, billamount, area, status, expirydate, tenant_id)
                                    VALUES (%s, %s, %s, %s, %s, %s, 'UNPAID', %s, %s)
                                """, (in_id, in_name, norm_p, in_pkg, int(in_rate), in_area, default_expiry, st.session_state['tenant_id']))
                        st.success("New subscriber line allocated cleanly.")
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# VIEW 3: LIFETIME AUDIT LEDGER HISTORY
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT invoiceid, customerid, customername, area, amountpaid, remainingarrears, datetimestamp, paymentmethod FROM billing_history WHERE tenant_id = %s ORDER BY datetimestamp DESC", (st.session_state['tenant_id'],))
            l_rows = cur.fetchall()
            if l_rows: st.dataframe(pd.DataFrame(l_rows), use_container_width=True)
            else: st.info("No logs captured inside ledger engine.")

# ==========================================
# VIEW 4: SYSTEM ACCESS CONFIGS
# ==========================================
elif routing_node == "🔐 System Access Control":
    if str(st.session_state.get('user_role', '')).lower() not in ["owner", "admin"]:
        st.error("Administrative elevation authorization clearance required.")
    else:
        st.markdown("<div class='main-title'>🔐 SYSTEM ACCESS PANEL</div>", unsafe_allow_html=True)
        all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
        
        adm_tabs = st.tabs(["🏢 Branding & Controls", "⚙️ Access Credentials Manager", "🗺️ Dynamic Area Nodes"])
        
        with adm_tabs[0]:
            with st.form("tenant_custom_branding_form"):
                b_name = st.text_input("Brand Company Name Display", value=TENANT_COMPANY_NAME)
                b_phone = st.text_input("Helpline Telephone Number", value=TENANT_SUPPORT_PHONE)
                wa_enabled = st.checkbox("Enable Green-API Auto Alert Dispatches", value=tenant_meta.get("wa_enabled", False))
                wa_instance = st.text_input("Green-API Instance Unique ID", value=tenant_meta.get("wa_instance_id", ""))
                wa_token = st.text_input("Green-API Token Key String", value=tenant_meta.get("wa_token", ""), type="password")
                
                if st.form_submit_button("💾 UPDATE BRANDING ARCHITECTURE"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE system_tenants SET company_name=%s, support_phone=%s, whatsapp_enabled=%s, whatsapp_instance_id=%s, whatsapp_token=%s WHERE tenant_id=%s
                            """, (b_name, b_phone, wa_enabled, wa_instance, wa_token, st.session_state['tenant_id']))
                    st.success("Tenant branding metrics written onto schema.")
                    st.cache_data.clear()
                    st.rerun()
                    
        with adm_tabs[2]:
            st.markdown("### 🗺️ Sector Node Operations")
            with st.form("add_area_sector_form"):
                new_area_name = st.text_input("Enter New Network Location Name").strip()
                if st.form_submit_button("➕ COMMIT SECTOR DEPLOYMENT REGISTRY"):
                    if new_area_name:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO areas VALUES (%s, %s) ON CONFLICT DO NOTHING", (new_area_name, st.session_state['tenant_id']))
                        st.success("Area logged to network mapping registry.")
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# VIEW 5: SUBSCRIBER SELF-SERVICE INVENTORY
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown("<div class='main-title'>📱 SUBSCRIBER SELF-SERVICE PORTAL</div>", unsafe_allow_html=True)
    portal_tenant = st.text_input("Enter ISP Provider Code").strip().lower()
    portal_input = st.text_input("Enter Username / Registered Mobile No.")
    
    if portal_tenant and portal_input:
        t_meta = fetch_active_tenant_metadata(portal_tenant)
        cleaned_p = clean_and_validate_phone(portal_input)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND (LOWER(username) = LOWER(%s) OR phone = %s)", [portal_tenant, portal_input.strip(), cleaned_p])
                c_rows = cur.fetchall()
                if c_rows:
                    c_dict = c_rows[0]
                    st.markdown(f"""
                        <div class="client-card" style="border: 2px solid {active_theme['accent']}; padding:20px; background-color:#1e2937; border-radius:12px;">
                            <h3 style="color:#10b981;">👤 ID: {c_dict['username']}</h3>
                            <p><b>Subscriber Name:</b> {c_dict['customername']}</p>
                            <p><b>Active Profile Profile:</b> {c_dict['package']}</p>
                            <p><b>Monthly Base Charges:</b> Rs. {int(c_dict['billamount']):,}</p>
                            <p style="color:#f43f5e; font-weight:bold;"><b>Outstanding Arrears Balance:</b> Rs. {int(c_dict['balanceshift']):,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>Line Expiry Date:</b> {c_dict['expirydate']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("❌ Profile identity matrix mapping not matched.")