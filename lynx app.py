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
import os
import logging
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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# RATE LIMITING FOR LOGIN ATTEMPTS
# ==========================================
from collections import defaultdict
from datetime import datetime, timedelta

# Simple in-memory rate limiter (for production, use Redis or database)
login_attempts = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

def is_account_locked(identifier: str) -> bool:
    """Check if account is locked due to too many failed attempts"""
    now = datetime.now()
    attempts = login_attempts[identifier]
    # Remove attempts older than lockout duration
    login_attempts[identifier] = [attempt for attempt in attempts if now - attempt < timedelta(minutes=LOCKOUT_DURATION_MINUTES)]
    
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        return True
    return False

def record_login_attempt(identifier: str, success: bool = False):
    """Record a login attempt"""
    if success:
        # Clear failed attempts on successful login
        login_attempts[identifier].clear()
    else:
        login_attempts[identifier].append(datetime.now())

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
if 'dashboard_status_filter' not in st.session_state:
    st.session_state['dashboard_status_filter'] = "ALL"
if 'app_theme' not in st.session_state:
    st.session_state['app_theme'] = "Dark Nebula (Default)"

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package", "billamount", "area", "address", "onuserialnumber"
]

# ==========================================
# 2. SECURE POOLED DATABASE REGISTRY
# ==========================================
try:
    DB_URL = st.secrets["DB_URL"]
except Exception as exc:
    st.error("🔴 Critical Configuration Error: 'DB_URL' is missing from Streamlit Secrets!")
    st.error("Please create a Streamlit secrets file at .streamlit/secrets.toml with a DB_URL entry.")
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
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def insert_activity_log(tenant_id, username, action_type, description):
    if not tenant_id or not username or not action_type:
        logger.warning(f"Activity log skipped - missing parameters: tenant_id={tenant_id}, username={username}, action_type={action_type}")
        return False

    try:
        log_id = f"LOG-{uuid.uuid4().hex[:10].upper()}"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Only create table if it doesn't exist (check first to avoid redundant operations)
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'activity_logs'
                    )
                """)
                table_exists = cursor.fetchone()[0]
                if not table_exists:
                    cursor.execute("""
                        CREATE TABLE activity_logs (
                            log_id TEXT PRIMARY KEY,
                            tenant_id TEXT NOT NULL,
                            username TEXT NOT NULL,
                            action_type TEXT NOT NULL,
                            description TEXT NOT NULL,
                            timestamp TEXT NOT NULL DEFAULT ''
                        )
                    """)
                    logger.info("Created activity_logs table")
                cursor.execute("""
                    INSERT INTO activity_logs (log_id, tenant_id, username, action_type, description, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (log_id, tenant_id, username, action_type, description, ts))
        logger.info(f"Activity log inserted: {action_type} by {username}")
        return True
    except Exception as exc:
        logger.error(f"Activity log error: {exc}")
        return False


def restore_login_from_query_params():
    try:
        # Use st.query_params instead of deprecated experimental_get_query_params
        query_params = st.query_params
    except AttributeError:
        # Fallback for older Streamlit versions
        if not hasattr(st, "experimental_get_query_params"):
            return False
        try:
            query_params = st.experimental_get_query_params()
        except Exception as e:
            logger.error(f"Error getting query params: {e}")
            return False

    auth_flag = query_params.get("auth", [""])[0] if isinstance(query_params.get("auth"), list) else query_params.get("auth", "")
    tenant = query_params.get("tenant", [""])[0] if isinstance(query_params.get("tenant"), list) else query_params.get("tenant", "")
    user_key = query_params.get("user", [""])[0] if isinstance(query_params.get("user"), list) else query_params.get("user", "")

    if isinstance(tenant, str):
        tenant = tenant.strip().lower()
    if isinstance(user_key, str):
        user_key = user_key.strip().lower()

    if auth_flag != "1" or st.session_state.get("authenticated", False):
        return False

    if not tenant or not user_key:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT role, username, assignedarea FROM users WHERE LOWER(username) = %s AND tenant_id = %s",
                    (user_key, tenant)
                )
                user_match = cursor.fetchone()
                if not user_match:
                    return False

                t_meta = fetch_active_tenant_metadata(tenant)
                _, valid_chk = calculate_license_days(t_meta.get("expiry_date", ""))
                if not t_meta["active"] or not valid_chk:
                    return False

                st.session_state["authenticated"] = True
                st.session_state["user_role"] = user_match[0] if user_match[0] else "Staff"
                st.session_state["username"] = user_match[1] if user_match[1] else user_key
                st.session_state["tenant_id"] = tenant
                raw_areas = user_match[2] if user_match[2] else "ALL"
                if str(user_match[0]).lower() in ["owner", "admin"] or raw_areas == "ALL":
                    st.session_state["assigned_areas"] = ["ALL"]
                else:
                    st.session_state["assigned_areas"] = [a.strip() for a in raw_areas.split(",") if a.strip()]
                st.session_state["current_node"] = "📊 Lynx Dashboard"
                insert_activity_log(tenant, st.session_state["username"], "LOGIN", "System restored from browser refresh via persistent auth parameters.")
                return True

    except Exception as e:
        logger.error(f"Error restoring login from query params: {e}")
        return False

    return False


def parse_wa_template(template_str, data_dict):
    out = template_str
    for key, val in data_dict.items():
        out = out.replace(f"{{{key}}}", str(val))
    return out

def send_tenant_whatsapp(tenant_metadata, phone_number, template_key, context_data):
    if not tenant_metadata.get("wa_enabled"):
        return False
    instance_id = tenant_metadata.get("wa_instance_id")
    api_token = tenant_metadata.get("wa_token")
    if not instance_id or not api_token:
        return False

    templates = DEFAULT_WA_TEMPLATES.copy()
    if tenant_metadata.get("wa_templates"):
        try:
            templates.update(json.loads(tenant_metadata["wa_templates"]))
        except Exception as exc:
            logger.error(f"WA Template Parse Error: {exc}")

    raw_message = templates.get(template_key, DEFAULT_WA_TEMPLATES.get(template_key, ""))
    if not raw_message:
        return False

    context_data.setdefault("helpline", tenant_metadata.get("phone", ""))
    formatted_message = parse_wa_template(raw_message, context_data)

    if not phone_number:
        return False

    clean_phone = str(phone_number).replace("-", "").replace("+", "").strip()
    clean_phone = re.sub(r"\D", "", clean_phone)
    if clean_phone.startswith("0"):
        clean_phone = "92" + clean_phone[1:]
    elif len(clean_phone) == 10 and clean_phone.startswith("3"):
        clean_phone = "92" + clean_phone

    if not clean_phone:
        return False

    url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{api_token}"
    payload = {
        "chatId": f"{clean_phone}@c.us",
        "message": formatted_message
    }
    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
        return response.ok
    except requests.exceptions.RequestException as exc:
        logger.error(f"WA Send Error: {exc}")
        return False
    except Exception as exc:
        logger.error(f"WA Unexpected Error: {exc}")
        return False

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
    except Exception as e:
        logger.error(f"Error converting paid/arrears values: {e}")
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

# ==========================================
# 3. AUTO-REPAIR MULTI-TENANT SCHEMA ENGINE
# ==========================================
def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    support_phone TEXT NOT NULL,
                    owner_username TEXT NOT NULL,
                    license_active BOOLEAN DEFAULT FALSE,
                    registration_date TEXT NOT NULL,
                    license_expiry_date TEXT NOT NULL DEFAULT '',
                    staff_permissions TEXT DEFAULT '',
                    whatsapp_instance_id TEXT DEFAULT '',
                    whatsapp_token TEXT DEFAULT '',
                    whatsapp_enabled BOOLEAN DEFAULT FALSE,
                    whatsapp_templates TEXT DEFAULT ''
                )
            """)
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS areas (
                    areaname TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (areaname, tenant_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    packagename TEXT NOT NULL,
                    areaname TEXT NOT NULL,
                    packagerate INTEGER NOT NULL DEFAULT 0,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (packagename, areaname, tenant_id)
                )
            """)
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
            cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date, license_expiry_date, staff_permissions, whatsapp_templates)
                    VALUES ('lynx', 'Lynx Fiber Pvt Ltd', '03135776263', 'owner', TRUE, %s, '', '', %s)
                """, (datetime.now().strftime("%Y-%m-%d"), json.dumps(DEFAULT_WA_TEMPLATES)))
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner' AND tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                # Use environment variable for default password, or generate a secure random password
                default_owner_pass = os.getenv('DEFAULT_OWNER_PASSWORD', None)
                if not default_owner_pass:
                    # Generate secure random password if not provided
                    import secrets
                    default_owner_pass = secrets.token_urlsafe(16)
                    logger.warning(f"Generated secure default password for owner: {default_owner_pass}. Please change it immediately after first login.")
                cursor.execute("""
                    INSERT INTO users (username, password, role, assignedarea, tenant_id)
                    VALUES ('owner', %s, 'Owner', 'ALL', 'lynx')
                """, (hash_password(default_owner_pass),))

def run_live_migrations():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Remove redundant ALTER statements for activity_logs since columns already exist in CREATE TABLE
                # cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS timestamp TEXT NOT NULL DEFAULT '';")
                # cursor.execute("ALTER TABLE activity_logs ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS staff_permissions TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_instance_id TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_token TEXT DEFAULT '';")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_enabled BOOLEAN DEFAULT FALSE;")
                cursor.execute("ALTER TABLE system_tenants ADD COLUMN IF NOT EXISTS whatsapp_templates TEXT DEFAULT '';")
        logger.info("Database migrations completed successfully")
    except Exception as exc:
        logger.error(f"Migration Error: {exc}")

@st.cache_resource
def initialize_application_database():
    build_database_schema()

initialize_application_database()
run_live_migrations()

# ==========================================
# 4. DATA RETRIEVAL LAYERS
# ==========================================
@st.cache_data(ttl=2)
def fetch_active_tenant_metadata(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT company_name, support_phone, license_active, license_expiry_date, staff_permissions, whatsapp_instance_id, whatsapp_token, whatsapp_enabled, whatsapp_templates FROM system_tenants WHERE tenant_id = %s", (tenant_id,))
                res = cur.fetchone()
                if res:
                    perms = DEFAULT_STAFF_PERMS.copy()
                    if res.get("staff_permissions"):
                        try:
                            perms.update(json.loads(res["staff_permissions"]))
                        except Exception as e:
                            logger.error(f"Error parsing staff permissions: {e}")
                    wa_templates_raw = res.get("whatsapp_templates", "")
                    if not wa_templates_raw or wa_templates_raw.strip() == "":
                        wa_templates_raw = json.dumps(DEFAULT_WA_TEMPLATES)
                    return {
                        "name": res["company_name"],
                        "phone": res["support_phone"],
                        "active": res["license_active"],
                        "expiry_date": res.get("license_expiry_date", ""),
                        "staff_permissions": perms,
                        "wa_instance_id": res.get("whatsapp_instance_id", ""),
                        "wa_token": res.get("whatsapp_token", ""),
                        "wa_enabled": res.get("whatsapp_enabled", False),
                        "wa_templates": wa_templates_raw
                    }
                return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True, "expiry_date": "", "staff_permissions": DEFAULT_STAFF_PERMS, "wa_instance_id": "", "wa_token": "", "wa_enabled": False, "wa_templates": json.dumps(DEFAULT_WA_TEMPLATES)}
    except Exception as e:
        logger.error(f"Error fetching tenant metadata: {e}")
        return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True, "expiry_date": "", "staff_permissions": DEFAULT_STAFF_PERMS, "wa_instance_id": "", "wa_token": "", "wa_enabled": False, "wa_templates": json.dumps(DEFAULT_WA_TEMPLATES)}

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
    except Exception as e:
        logger.error(f"Error calculating license days: {e}")
        return "Invalid Expiry Mapping", False

restore_login_from_query_params()
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
                    df['balanceshift'] = pd.to_numeric(df['balanceshift'], errors='coerce').fillna(0).astype(int)
                    df['billamount'] = pd.to_numeric(df['billamount'], errors='coerce').fillna(0).astype(int)
                    extended_cols = GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER]
                    return df.reindex(columns=extended_cols)
                return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate', 'tenant_id'])
    except Exception as e:
        logger.error(f"Error fetching isolated matrix: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3)
def fetch_isolated_areas(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT areaname FROM areas WHERE tenant_id = %s ORDER BY areaname ASC", (tenant_id,))
                rows = cur.fetchall()
                return [r[0] for r in rows] if rows else []
    except Exception as e:
        logger.error(f"Error fetching isolated areas: {e}")
        return []

@st.cache_data(ttl=3)
def fetch_isolated_packages(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT packagename, areaname, packagerate FROM packages WHERE tenant_id = %s ORDER BY packagename ASC, areaname ASC", (tenant_id,))
                return cur.fetchall()
    except Exception as e:
        logger.error(f"Error fetching isolated packages: {e}")
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
    except Exception as e:
        logger.error(f"Error fetching billing summary: {e}")
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

def validate_phone_number(phone_str: str) -> bool:
    """Validate Pakistani phone number format"""
    if not phone_str:
        return False
    cleaned = clean_and_validate_phone(phone_str)
    # Pakistani mobile numbers: 10-11 digits starting with 0 or 12 digits starting with 92
    if len(cleaned) == 10 and cleaned.startswith("3"):
        return True
    if len(cleaned) == 11 and cleaned.startswith("0"):
        return True
    if len(cleaned) == 12 and cleaned.startswith("92"):
        return True
    return False

def validate_cnic(cnic_str: str) -> bool:
    """Validate Pakistani CNIC format (XXXXX-XXXXXXX-X)"""
    if not cnic_str:
        return True  # CNIC is optional
    cleaned = str(cnic_str).strip()
    # Allow formats: XXXXX-XXXXXXX-X, XXXXX XXXXXXX X, or without dashes
    cnic_pattern = r'^\d{5}[-\s]?\d{7}[-\s]?\d$'
    return bool(re.match(cnic_pattern, cleaned))

def validate_username(username_str: str) -> bool:
    """Validate username format"""
    if not username_str:
        return False
    cleaned = str(username_str).strip().lower()
    # Username should be 3-20 characters, alphanumeric and underscores only
    if len(cleaned) < 3 or len(cleaned) > 20:
        return False
    return bool(re.match(r'^[a-z0-9_]+$', cleaned))

def validate_email(email_str: str) -> bool:
    """Validate email format"""
    if not email_str:
        return True  # Email is optional
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, str(email_str).strip()))

# ==========================================
# 4.5. THEME ENGINE & CSS GENERATOR
# ==========================================
THEMES = {
    "Dark Nebula (Default)": {
        "bg": "#0b0f19", "sidebar_bg": "#111827", "text": "#e5e7eb", "heading": "#10b981", "accent": "#3b82f6", "card_bg": "#1f2937", "table_th": "#1f2937", "table_td": "#111827", "border": "#374151", "input_bg": "#ffffff", "input_text": "#000000", "login_box_border": "#10b981"
    },
    "Light Corporate": {
        "bg": "#f8fafc", "sidebar_bg": "#ffffff", "text": "#1e293b", "heading": "#059669", "accent": "#2563eb", "card_bg": "#ffffff", "table_th": "#e2e8f0", "table_td": "#ffffff", "border": "#cbd5e1", "input_bg": "#f1f5f9", "input_text": "#0f172a", "login_box_border": "#2563eb"
    },
    "Midnight Crimson": {
        "bg": "#11090b", "sidebar_bg": "#1a0e11", "text": "#fda4af", "heading": "#e11d48", "accent": "#be123c", "card_bg": "#281216", "table_th": "#281216", "table_td": "#1a0e11", "border": "#4c1d28", "input_bg": "#fff1f2", "input_text": "#4c0519", "login_box_border": "#e11d48"
    },
    "Ocean Wave": {
        "bg": "#0f172a", "sidebar_bg": "#1e293b", "text": "#e0f2fe", "heading": "#0ea5e9", "accent": "#0284c7", "card_bg": "#0f172a", "table_th": "#1e293b", "table_td": "#0f172a", "border": "#38bdf8", "input_bg": "#f0f9ff", "input_text": "#0c4a6e", "login_box_border": "#0ea5e9"
    }
}

active_theme = THEMES.get(st.session_state['app_theme'], THEMES["Dark Nebula (Default)"])
st.markdown(f"""
<style>
.stApp [data-testid="stHeader"] {{ background: transparent !important; height: 50px !important; }}
.stApp .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }}
.stApp {{ background-color: {active_theme['bg']}; color: {active_theme['text']}; font-family: sans-serif; }}
[data-testid="stSidebar"] {{ background-color: {active_theme['sidebar_bg']}; border-right: 1px solid {active_theme['border']}; }}
div[data-testid="stTextInput"] input, div[data-testid="stNumberInput"] input, div[data-testid="stTextArea"] textarea {{ color: {active_theme['input_text']} !important; background-color: {active_theme['input_bg']} !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid {active_theme['accent']} !important; border-radius: 8px !important; }}
div[data-testid="stNumberInput"] button {{ background-color: {active_theme['input_bg']} !important; color: {active_theme['input_text']} !important; }}
div[data-baseweb="select"] > div {{ background-color: {active_theme['input_bg']} !important; color: {active_theme['input_text']} !important; font-weight: bold !important; font-size: 16px !important; border: 2px solid {active_theme['accent']} !important; border-radius: 8px !important; }}
div[data-baseweb="select"] span, div[data-baseweb="select"] div {{ color: {active_theme['input_text']} !important; }}
ul[role="listbox"] li {{ color: {active_theme['input_text']} !important; background-color: {active_theme['input_bg']} !important; font-weight: 600 !important; }}
label, p, .stMarkdown div {{ color: {active_theme['text']} !important; font-weight: 500; }}
div.stButton > button, div.stFormSubmitButton > button {{ background: linear-gradient(135deg, {active_theme['sidebar_bg']} 0%, {active_theme['bg']} 100%) !important; color: {active_theme['accent']} !important; border: 2px solid {active_theme['accent']} !important; border-radius: 12px !important; padding: 15px !important; font-weight: bold !important; font-size: 15px !important; transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important; width: 100% !important; display: flex !important; align-items: center !important; justify-content: center !important; }}
div.stButton > button:hover, div.stFormSubmitButton > button:hover {{ background: {active_theme['accent']} !important; color: #ffffff !important; border: 2px solid {active_theme['accent']} !important; box-shadow: 0 0 15px {active_theme['accent']}80 !important; }}
.table-wrapper {{ overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; margin-top: 15px; }}
.premium-table {{ width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; background: {active_theme['table_td']}; }}
.premium-table th {{ background: {active_theme['table_th']}; color: {active_theme['heading']}; padding: 14px; text-align: left; font-size: 13px; border-bottom: 2px solid {active_theme['border']}; white-space: nowrap; text-transform: uppercase;}}
.premium-table td {{ padding: 14px; border-bottom: 1px solid {active_theme['border']}; font-size: 13px; color: {active_theme['text']}; white-space: nowrap; }}
.btn-action {{ padding: 6px 12px; border-radius: 6px; font-weight: bold; text-decoration: none; font-size: 12px; display: inline-block; margin-right: 4px; }}
.btn-c {{ background-color: #2563eb; color: white !important; }}
.btn-w {{ background-color: #16a34a; color: white !important; }}
.client-card {{ background: {active_theme['card_bg']}; padding: 20px; border-radius: 12px; border: 1px solid {active_theme['border']}; margin-bottom: 15px; }}
.main-title {{ color: {active_theme['heading']}; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }}
.front-login-box {{ max-width: 450px; margin: 40px auto; background: {active_theme['sidebar_bg']}; padding: 40px; border-radius: 16px; border: 1px solid {active_theme['login_box_border']}; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); }}
.system-card {{ background: {active_theme['card_bg']}; border: 1px solid {active_theme['border']}; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }}
.system-card h4 {{ margin: 0 0 10px 0; color: {active_theme['accent']}; font-size: 16px; font-weight: bold;}}
.saas-footer {{ text-align: center; font-size: 12px; color: {active_theme['text']}; opacity: 0.7; margin-top: 50px; padding: 15px; border-top: 1px solid {active_theme['border']}; }}
.saas-footer b {{ color: {active_theme['accent']}; }}
.live-calc-box {{ background-color: {active_theme['bg']}; border: 2px dashed {active_theme['heading']}; padding: 15px; border-radius: 10px; margin-bottom: 15px; }}
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
            st.markdown(f"<h3 style='text-align:center; color:{active_theme['heading']};'>ERP SYSTEM LOGIN</h3>", unsafe_allow_html=True)
            input_tenant = st.text_input("Tenant Domain ID / Code (e.g., lynx)", key="log_tenant").strip().lower()
            user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
            pass_input = st.text_input("Security Password", type="password", key="front_pass")
            if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
                # Validate inputs
                if not validate_username(input_tenant):
                    st.error("❌ Invalid tenant ID format. Use 3-20 alphanumeric characters.")
                elif not validate_username(user_input):
                    st.error("❌ Invalid username format. Use 3-20 alphanumeric characters.")
                elif len(pass_input) < 6:
                    st.error("❌ Password must be at least 6 characters.")
                elif is_account_locked(f"{input_tenant}:{user_input}"):
                    st.error(f"⚠️ Account locked due to too many failed attempts. Please try again in {LOCKOUT_DURATION_MINUTES} minutes.")
                else:
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT role, username, assignedarea, password FROM users WHERE LOWER(username) = %s AND tenant_id = %s", (user_input, input_tenant))
                            user_match = cursor.fetchone()
                            if user_match and verify_password(pass_input, user_match[3]):
                                record_login_attempt(f"{input_tenant}:{user_input}", success=True)
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
                                    if str(user_match[0]).lower() in ["owner", "admin"] or raw_areas == "ALL":
                                        st.session_state['assigned_areas'] = ["ALL"]
                                    else:
                                        st.session_state['assigned_areas'] = [a.strip() for a in raw_areas.split(",") if a.strip()]
                                    st.session_state['current_node'] = "📊 Lynx Dashboard"
                                    insert_activity_log(input_tenant, st.session_state['username'], "LOGIN", "System initialized successfully via secure portal node.")
                                    # Use st.query_params instead of deprecated experimental_set_query_params
                                    try:
                                        st.query_params['auth'] = '1'
                                        st.query_params['tenant'] = input_tenant
                                        st.query_params['user'] = st.session_state['username']
                                    except AttributeError:
                                        # Fallback for older Streamlit versions
                                        if hasattr(st, 'experimental_set_query_params'):
                                            st.experimental_set_query_params(auth='1', tenant=input_tenant, user=st.session_state['username'])
                                    st.cache_data.clear()
                                    st.rerun()
                            else:
                                record_login_attempt(f"{input_tenant}:{user_input}", success=False)
                                st.error("❌ Invalid Tenant, Username, or Password Variant.")
        with register_tab:
            st.markdown(f"<h3 style='text-align:center; color:{active_theme['accent']};'>SaaS Tenant Onboarding</h3>", unsafe_allow_html=True)
            with st.form("saas_tenant_registration_form"):
                reg_tenant_id = st.text_input("Choose Unique Tenant Code (e.g., falcon, alpha)").strip().lower()
                reg_company_name = st.text_input("ISP Company Full Brand Name").strip()
                reg_support_phone = st.text_input("Official Support Helpline Number").strip()
                reg_owner_user = st.text_input("Create Master Admin Username").strip().lower()
                reg_owner_pass = st.text_input("Create Master Admin Password", type="password")
                if st.form_submit_button("➕ SUBMIT ACTIVATION APP PROPOSAL"):
                    if not reg_tenant_id or not reg_company_name or not reg_owner_user or not reg_owner_pass:
                        st.error("❌ Mandatory registration input fields are empty.")
                    elif not validate_username(reg_tenant_id):
                        st.error("❌ Tenant Code must be 3-20 alphanumeric characters.")
                    elif not validate_username(reg_owner_user):
                        st.error("❌ Username must be 3-20 alphanumeric characters.")
                    elif not validate_phone_number(reg_support_phone):
                        st.error("❌ Invalid Pakistani phone number format.")
                    elif len(reg_owner_pass) < 6:
                        st.error("❌ Password string must consist of at least 6 characters.")
                    else:
                        try:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = %s", (reg_tenant_id,))
                                    if cursor.fetchone()[0] > 0:
                                        st.error("❌ Unique tenant identifier already registered.")
                                    else:
                                        cursor.execute("""
                                            INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date, license_expiry_date, staff_permissions, whatsapp_templates)
                                            VALUES (%s, %s, %s, %s, FALSE, %s, '', '', %s)
                                        """, (reg_tenant_id, reg_company_name, reg_support_phone, reg_owner_user, datetime.now().strftime("%Y-%m-%d"), json.dumps(DEFAULT_WA_TEMPLATES)))
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
        st.markdown(f"<h2 style='color:{active_theme['heading']}; font-weight:900; text-align:center;'>{str(TENANT_COMPANY_NAME).upper()}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-size:11px;'>Instance: <b>{st.session_state.get('tenant_id', 'lynx')}</b></p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-size:12px; color:#f59e0b;'>⏳ Account Life: <br><b>{license_status_text}</b></p>", unsafe_allow_html=True)
        
        if st.button("📊 Lynx Dashboard", use_container_width=True):
            st.session_state['current_node'] = "📊 Lynx Dashboard"
            st.session_state['dashboard_status_filter'] = "ALL"
            st.rerun()
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"
            st.rerun()
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"
            st.rerun()
        if st.button("📘 ISP Guide", use_container_width=True):
            st.session_state['current_node'] = "📘 ISP Guide"
            st.rerun()
            
        if str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"]:
            if st.button("🔐 System Access Control", use_container_width=True):
                st.session_state['current_node'] = "🔐 System Access Control"
                st.rerun()
        st.write("---")
        st.markdown(f"🎨 **Personalize Theme**")
        selected_theme = st.selectbox(
            "Select UI Theme", list(THEMES.keys()), index=list(THEMES.keys()).index(st.session_state['app_theme']), label_visibility="collapsed"
        )
        if selected_theme != st.session_state['app_theme']:
            st.session_state['app_theme'] = selected_theme
            st.rerun()
        st.write("---")
        username_display = str(st.session_state.get('username', 'UNKNOWN')).upper()
        role_display = str(st.session_state.get('user_role', 'STAFF')).upper()
        st.markdown(f"<p style='text-align:center;'>👤 Active: <b>{username_display}</b><br>📍 Role: <b style='color:{active_theme['heading']};'>{role_display}</b></p>", unsafe_allow_html=True)
        if st.button("🔒 Logout System", use_container_width=True):
            insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "LOGOUT", "User terminated application session manually.")
            st.session_state['authenticated'] = False
            # Use st.query_params instead of deprecated experimental_set_query_params
            try:
                st.query_params.clear()
            except AttributeError:
                # Fallback for older Streamlit versions
                if hasattr(st, 'experimental_set_query_params'):
                    st.experimental_set_query_params()
            st.rerun()

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
        
    if not all_system_areas:
        st.info("💡 Database mapping is empty. Configure sectors inside System Access Control.")
    elif df_matrix.empty:
        st.warning("⚠️ Operational Database is empty. No subscribers registered.")
    else:
        collection_map = fetch_isolated_billing_summary(st.session_state['tenant_id'])
        filtered_matrix = df_matrix.copy()
        if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
            filtered_matrix = filtered_matrix[filtered_matrix['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
        total_free_customers = len(filtered_matrix[
            (filtered_matrix['status'] == 'FREE') |
            (filtered_matrix['billamount'] == 0) |
            (filtered_matrix['package'].astype(str).str.contains('free', case=False, na=False))
        ])
        total_free_customers = int(total_free_customers)
        st.markdown("### 🌐 Active System Node Overview")
        st.markdown(f"<p style='font-size:16px; color:{active_theme['heading']}; margin-bottom:0.75rem;'>🆓 Free Subscribers in Overview: <b>{total_free_customers}</b></p>", unsafe_allow_html=True)
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
                    hub_suspended_count = len(segment[segment['status'] == 'SUSPENDED'] )
                    hub_free_count = len(segment[
                        (segment['status'] == 'FREE') |
                        (segment['billamount'] == 0) |
                        (segment['package'].astype(str).str.contains('free', case=False, na=False))
                    ])
                    hub_uids = [str(x).lower().strip() for x in segment['username'].tolist() if x]
                    hub_collected = sum(collection_map.get(uid, 0) for uid in hub_uids)
                    b_color = active_theme['heading'] if (i+j)%2 == 0 else active_theme['accent']
                    with cols[j]:
                        st.markdown(f"""
                        <div class="system-card" style="border-left: 5px solid {b_color};">
                            <h4>🌐 {current_hub} Overview</h4>
                            <p><b>Total Customers:</b> {len(segment)}</p>
                            <p><b>Expected Revenue:</b> Rs. {hub_bill:,}</p>
                            <p style="color:#10b981; font-weight:bold;"><b>✅ Paid Users:</b> {hub_paid_count} (Recv: Rs. {hub_collected:,})</p>
                            <p style="color:#f59e0b; font-weight:bold;"><b>🟡 Partial Accounts:</b> {hub_partial_count}</p>
                            <p style="color:#6366f1; font-weight:bold;"><b>🆓 Free Accounts:</b> {hub_free_count}</p>
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
            total_unpaid = len(base_df[base_df['status'].isin(['UNPAID', 'PARTIAL', 'SUSPENDED'])])
            total_free = len(base_df[(base_df['billamount'] == 0) | (base_df['package'].astype(str).str.contains('free', case=False, na=False))])
            try:
                total_arrears = int(float(str(base_df['balanceshift'].sum())))
            except Exception:
                total_arrears = 0
            st.markdown("### 📊 Interactive Live Filters")
            st.caption("Niche diye gaye buttons par click karke table data ko instant status ke mutabiq filter karein:")
            metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
            with metric_col1:
                if st.button(f"🌐 All Terminals ({total_active})", use_container_width=True):
                    st.session_state['dashboard_status_filter'] = "ALL"
                    st.rerun()
            with metric_col2:
                if st.button(f"✅ Paid Accounts ({total_paid})", use_container_width=True):
                    st.session_state['dashboard_status_filter'] = "PAID"
                    st.rerun()
            with metric_col3:
                if st.button(f"❌ Unpaid / Defaulters ({total_unpaid})", use_container_width=True):
                    st.session_state['dashboard_status_filter'] = "UNPAID_ANY"
                    st.rerun()
            with metric_col4:
                if st.button(f"🆓 Free Accounts ({total_free})", use_container_width=True):
                    st.session_state['dashboard_status_filter'] = "FREE"
                    st.rerun()
            with metric_col5:
                st.metric("Total Arrears Balance", f"Rs. {total_arrears:,}")
            
            search_query = st.text_input("🔍 Fast Find Subscriber Row Analyzer")
            
            active_filter_state = st.session_state['dashboard_status_filter']
            if active_filter_state == "PAID":
                base_df = base_df[base_df['status'] == 'PAID'].copy()
                st.markdown(f"🟢 *Showing Only **PAID** Subscriber List ({len(base_df)} accounts)*")
            elif active_filter_state == "UNPAID_ANY":
                base_df = base_df[base_df['status'].isin(['UNPAID', 'PARTIAL', 'SUSPENDED'])].copy()
                st.markdown(f"🔴 *Showing Only **UNPAID / PARTIAL / SUSPENDED** Defaulter List ({len(base_df)} accounts)*")
            elif active_filter_state == "FREE":
                base_df = base_df[(base_df['billamount'] == 0) | (base_df['package'].astype(str).str.contains('free', case=False, na=False))].copy()
                st.markdown(f"🟣 *Showing Only **FREE** Subscribers ({len(base_df)} accounts)*")
            else:
                st.markdown(f"🔵 *Showing **ALL** Assigned Subscriber Directory*")
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
                    
                c_status = str(row_dict.get('status', '')).upper()
                if c_status == "SUSPENDED":
                    t_key = "expired_warning"
                elif c_status in ["UNPAID", "PARTIAL"]:
                    t_key = "bill_reminder"
                else:
                    t_key = "bill_paid"
                    
                t_dict = DEFAULT_WA_TEMPLATES.copy()
                if tenant_meta.get("wa_templates"):
                    try:
                        t_dict.update(json.loads(tenant_meta["wa_templates"]))
                    except:
                        pass
                ctx = {
                    "name": row_dict.get('customername', ''),
                    "username": row_dict.get('username', ''),
                    "package": row_dict.get('package', ''),
                    "bill": row_dict.get('billamount', 0),
                    "arrears": row_dict.get('balanceshift', 0),
                    "expiry": row_dict.get('expirydate', ''),
                    "helpline": TENANT_SUPPORT_PHONE,
                    "paid": collection_map.get(str(row_dict.get('username','')).lower().strip(), 0)
                }
                parsed_msg = parse_wa_template(t_dict.get(t_key, ""), ctx)
                if len(wa_number) >= 10:
                    wa_label = "💬 Arrears WA" if t_key in ["bill_reminder", "expired_warning"] else "💬 Payment WA"
                    wa_action_html = f'<a href="https://wa.me/{wa_number}?text={urllib.parse.quote(parsed_msg)}" target="_blank" class="btn-action btn-w">{wa_label}</a>'
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

            if active_filter_state == "UNPAID_ANY" and not base_df.empty:
                st.markdown("### 💳 Quick Pay Unpaid Subscriber")
                st.info("Direct settlement is available here. Select a subscriber from the unpaid list below and settle the due amount without going to the Billing tab.")
                unpaid_labels = []
                unpaid_map = {}
                for _, row in base_df.iterrows():
                    uid = str(row.get('username', '')).strip()
                    name = row.get('customername', '')
                    addr = str(row.get('address', '')).strip()
                    display_addr = (addr[:60] + '...') if len(addr) > 60 else addr
                    label = f"[{uid}] {name} — {display_addr} — Rs. {int(float(str(row.get('balanceshift', 0)))):,}"
                    unpaid_labels.append(label)
                    unpaid_map[label] = uid
                selected_unpaid_label = st.selectbox("Choose unpaid subscriber to pay now", unpaid_labels, key="dashboard_unpaid_pay_select")
                if selected_unpaid_label:
                    selected_uid = unpaid_map[selected_unpaid_label]
                    selected_row = base_df[base_df['username'] == selected_uid].iloc[0].to_dict()
                    try:
                        dp_base_bill = int(float(str(selected_row.get('billamount', 0))))
                    except Exception:
                        dp_base_bill = 0
                    try:
                        dp_base_shift = int(float(str(selected_row.get('balanceshift', 0))))
                    except Exception:
                        dp_base_shift = 0
                    st.info(f"📊 Plan Rate: Rs. {dp_base_bill:,} | Current Arrears: Rs. {dp_base_shift:,} | Expiry: {selected_row.get('expirydate', '')}")
                    pay_col1, pay_col2, pay_col3 = st.columns(3)
                    with pay_col1:
                        dp_months = st.selectbox("Advance Months", [1, 3, 6, 12], key="dashboard_unpaid_months")
                    with pay_col2:
                        dp_method = st.selectbox("Payment Method", ["CASH", "EASYPAISA", "JAZZCASH", "BANK_TRANSFER"], key="dashboard_unpaid_method")
                    with pay_col3:
                        dp_discount = st.number_input("Discount (Rs.)", min_value=0, value=0, step=50, key="dashboard_unpaid_discount")

                    dp_package_total_cost = dp_base_bill * dp_months
                    dp_net_payable = dp_package_total_cost + dp_base_shift
                    dp_final_due = max(dp_net_payable - dp_discount, 0)
                    dp_cash_in = st.number_input("Amount Received (Rs.)", min_value=0, max_value=dp_final_due, value=dp_final_due, key="dashboard_unpaid_cash")
                    dp_future_shift = max(0, int(dp_final_due - dp_cash_in))

                    if dp_future_shift <= 0:
                        dp_status = "PAID"
                        dp_color = "#10b981"
                    elif dp_cash_in > 0:
                        dp_status = "PARTIAL"
                        dp_color = "#f59e0b"
                    else:
                        dp_status = "UNPAID"
                        dp_color = "#f43f5e"

                    st.markdown(f"""
                    <div class='live-calc-box'>
                        <p>📦 <b>Package Extension Charges ({dp_months} Month(s)):</b> Rs. {dp_package_total_cost:,}</p>
                        <p>⏮️ <b>Existing Arrears:</b> Rs. {dp_base_shift:,}</p>
                        <p>🎁 <b>Discount:</b> Rs. {dp_discount:,}</p>
                        <h4 style='color:{active_theme['accent']};'><b>Final Due:</b> Rs. {dp_final_due:,}</h4>
                        <hr style='border:1px solid {active_theme['border']};'>
                        <h4>🔮 <b>Updated Status:</b> <span style='color:{dp_color}; font-weight:bold;'>{dp_status}</span></h4>
                        <p>💾 <b>New Arrears Balance:</b> Rs. {dp_future_shift:,}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    if st.button("💳 SETTLE THIS UNPAID ACCOUNT", key=f"dashboard_pay_{selected_uid}", use_container_width=True):
                        today_dt = datetime.now()
                        current_expiry_str = str(selected_row.get('expirydate', '')).strip()
                        try:
                            dp_old_expiry = datetime.strptime(current_expiry_str, "%Y-%m-%d")
                            dp_base_dt = today_dt if dp_old_expiry < today_dt else dp_old_expiry
                        except Exception:
                            dp_base_dt = today_dt
                        dp_new_expiry = (dp_base_dt + relativedelta(months=dp_months)).strftime("%Y-%m-%d")
                        dp_invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s AND tenant_id = %s
                                """, (dp_future_shift, dp_status, dp_new_expiry, selected_uid, st.session_state['tenant_id']))
                                cursor.execute("""
                                    INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven, tenant_id)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s, %s)
                                """, (dp_invoice_uuid, selected_uid, selected_row.get('customername'), selected_row.get('area'), selected_row.get('phone'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), selected_row.get('package'), int(dp_cash_in), dp_future_shift, dp_method, int(dp_discount), st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "BILL_PAYMENT", f"Quick dashboard payment Rs. {dp_cash_in} for user {selected_uid}. Status {dp_status}, Arrears {dp_future_shift}, Expiry {dp_new_expiry}.")
                        st.success(f"✅ Payment recorded for {selected_uid}! Status: {dp_status} | New Expiry: {dp_new_expiry}")
                        wa_context = {
                            "name": selected_row.get('customername', ''), "username": selected_uid, "package": selected_row.get('package', ''), "paid": int(dp_cash_in), "arrears": dp_future_shift, "expiry": dp_new_expiry, "method": dp_method
                        }
                        send_tenant_whatsapp(tenant_meta, selected_row.get('phone'), "bill_paid", wa_context)
                        st.session_state['recent_pdf_bytes'] = generate_receipt_pdf(TENANT_COMPANY_NAME, TENANT_SUPPORT_PHONE, dp_invoice_uuid, selected_uid, selected_row.get('customername'), selected_row.get('area'), selected_row.get('package'), dp_cash_in, dp_future_shift, dp_method)
                        st.session_state['recent_invoice_uuid'] = dp_invoice_uuid
                        st.cache_data.clear()
                        st.rerun()

                    if 'recent_pdf_bytes' in st.session_state:
                        st.download_button("📥 Download Generated PDF Receipt", data=st.session_state['recent_pdf_bytes'], file_name=f"Receipt_{st.session_state.get('recent_invoice_uuid', 'INV')}.pdf", mime="application/pdf", use_container_width=True)

    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONS CENTER (LIVE CALCULATIONS)
# ==========================================
elif routing_node == "📘 ISP Guide":
    st.markdown("<div class='main-title'>📘 ISP GUIDE / آئی ایس پی گائیڈ</div>", unsafe_allow_html=True)
    user_role = str(st.session_state.get('user_role', 'staff')).lower()
    assigned_areas = st.session_state.get('assigned_areas', ['ALL'])

    # Owner / Admin bilingual guide
    if user_role in ["owner", "admin"]:
        st.markdown("<div class='client-card'>", unsafe_allow_html=True)
        st.markdown(
            "<h3>Owner / Admin Full Guide — English</h3>"
            "<p>This section contains the complete system guide for Owner/Admin, including staff management, permissions, and configuration.</p>"
            "<h4>🔑 System Modules</h4>"
            "<ul>"
            "<li><b>ERP Dashboard:</b> Provides summary counts, Active/Paid/Free/Unpaid/Suspended metrics and quick filters.</li>"
            "<li><b>Operational Billing Center:</b> Handles collection, payments, reversals, provisioning, bulk import and terminal edits.</li>"
            "<li><b>Lifetime Ledger History:</b> Full transaction log for tenant auditing and invoice reversal.</li>"
            "<li><b>System Access Control:</b> Owner/Admin-only area for managing areas, packages and staff permissions.</li>"
            "</ul>"
            "<h4>🧠 App Logic Summary</h4>"
            "<p>The app fetches data from the database, applies user permissions and assigned area filters, and then renders dashboard summaries, tables, and actionable operations.</p>"
            "<ol>"
            "<li>After login, the user's role and assigned areas are loaded.</li>"
            "<li>Dashboard shows overview and arrears summaries.</li>"
            "<li>Operational Billing Center enables recording payments, updating arrears and editing customer profiles.</li>"
            "<li>To mark a customer as free, set Monthly Rate to 0 and Status to 'FREE'.</li>"
            "</ol>"
            "<h4>🛠️ Owner/Admin Notes</h4>"
            "<ul>"
            "<li>Owner/Admin can manage staff permissions and tenant-wide settings.</li>"
            "<li>Owner/Admin has full access to view all assigned areas or 'ALL'.</li>"
            "<li>This role is responsible for maintaining billing accuracy and customer statuses.</li>"
            "</ul>"
            "<p>Use Dashboard, Operational Billing Center and Ledger History for full operational control.</p>",
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='client-card'>", unsafe_allow_html=True)
        st.markdown(
            "<h3>Owner / Admin مکمل گائیڈ — اردو</h3>"
            "<p>یہ سیکشن Owner/Admin کے لیے مکمل سسٹم گائیڈ ہے، جس میں اسٹاف مینجمنٹ، پرمیشنز، اور کنفیگریشن شامل ہیں۔</p>"
            "<h4>🔑 سسٹم ماڈیولز</h4>"
            "<ul>"
            "<li><b>ERP Dashboard:</b> خلاصہ، Active/Paid/Free/Unpaid/Suspended میٹرکس اور فوری فلٹرز دکھاتا ہے۔</li>"
            "<li><b>Operational Billing Center:</b> کلیکشن، ادائیگیاں، ریورسل، نئے کنکشن، بلک امپورٹ اور ٹرمینل ایڈیٹ کے لیے ہے۔</li>"
            "<li><b>Lifetime Ledger History:</b> مکمل ٹرانزیکشن لاگ برائے آڈٹ اور انوائس ریورسلز۔</li>"
            "<li><b>System Access Control:</b> Owner/Admin کے لیے مخصوص؛ علاقے، پیکجز اور اسٹاف پرمیشنز یہاں مینج ہوتی ہیں۔</li>"
            "</ul>"
            "<h4>🧠 ایپ لاجک کا خلاصہ</h4>"
            "<p>ایپ پہلے database سے ڈیٹا لیتی ہے، پھر user کی پرمیشنز اور assigned areas کے مطابق فلٹر کرکے dashboard اور actions دکھاتی ہے۔</p>"
            "<ol>"
            "<li>Login کے بعد user کی role اور assigned_areas لوڈ ہوتی ہیں۔</li>"
            "<li>Dashboard میں اوور ویو اور arrears خلاصہ دکھایا جاتا ہے۔</li>"
            "<li>Operational Billing Center میں پیمنٹس ریکارڈ کریں، arrears اپ ڈیٹ کریں اور پروفائل ایڈیٹ کریں۔</li>"
            "<li>کسی صارف کو مفت قرار دینے کے لیے Monthly Rate 0 اور Status 'FREE' کریں۔</li>"
            "</ol>"
            "<h4>🛠️ Owner/Admin کے نوٹس</h4>"
            "<ul>"
            "<li>Owner/Admin اسٹاف پرمیشنز اور ٹیننٹ سیٹنگز مینیج کرسکتا ہے۔</li>"
            "<li>Owner/Admin کو تمام assigned areas یا 'ALL' دیکھنے کی مکمل اجازت ہے۔</li>"
            "<li>یہ رول billing اور customer statuses کی درستگی کا ذمہ دار ہے۔</li>"
            "</ul>"
            "<p>پوری آپریشنل کنٹرول کے لیے Dashboard، Operational Billing Center اور Ledger History استعمال کریں۔</p>",
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Staff bilingual guide
    else:
        st.markdown("<div class='client-card'>", unsafe_allow_html=True)
        st.markdown(
            f"<h3>Staff Guide — English</h3>"
            f"<p>Your role: <b>{html.escape(str(st.session_state.get('user_role', 'Staff')).upper())}</b></p>"
            f"<p>Assigned Areas: <b>{html.escape(', '.join(assigned_areas))}</b></p>"
            "<p>Staff users should focus on these areas:</p>"
            "<ul>"
            "<li>View accounts in your assigned areas via the Dashboard.</li>"
            "<li>Manage customer bills and arrears in the Operational Billing Center.</li>"
            "<li>Send arrears reminder via WhatsApp from the subscriber row actions.</li>"
            "<li>Manage free accounts by setting package or billamount to 0.</li>"
            "</ul>"
            "<p>You cannot edit system settings or staff permissions; those are Owner/Admin responsibilities.</p>"
            "<p>Where to find daily tasks: Dashboard → Operational Billing Center → Ledger History.</p>",
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='client-card'>", unsafe_allow_html=True)
        st.markdown(
            f"<h3>Staff Guide & Limited Access Info — اردو</h3>"
            f"<p>آپ کا رول: <b>{html.escape(str(st.session_state.get('user_role', 'Staff')).upper())}</b></p>"
            f"<p>Assigned Areas: <b>{html.escape(', '.join(assigned_areas))}</b></p>"
            "<p>Staff صارفین کو ذیل کے حصے استعمال کرنے چاہئیں:</p>"
            "<ul>"
            "<li>Dashboard میں اپنے assigned areas کے accounts دیکھیں۔</li>"
            "<li>Operational Billing Center میں کسٹمر بل اور arrears کا انتظام کریں۔</li>"
            "<li>سبسکرائبر رو پر WhatsApp سے arrears reminder بھیجیں۔</li>"
            "<li>Free accounts کو package یا billamount 0 کے ذریعے manage کریں۔</li>"
            "</ul>"
            "<p>System settings یا staff permissions edit کرنے کی اجازت نہیں ہے؛ یہ Owner/Admin کے لیے مخصوص ہے۔</p>"
            "<p>روزمرہ کام کے لیے: Dashboard → Operational Billing Center → Ledger History استعمال کریں۔</p>",
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_management = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    if not is_management and "ALL" not in st.session_state['assigned_areas']:
        df_matrix = df_matrix[df_matrix['area'].str.lower().isin([s.lower() for s in st.session_state['assigned_areas']])]
        
    if is_management:
        tabs = st.tabs(["💳 Capital Collection Hub", "🔄 Status & Reversal Control", "➕ Provision New Client", "📥 Bulk Import Excel/CSV", "🛠️ Edit Terminal Profile", "🗑️ Remove Subscriber"])
        tab_col, tab_status_rev, tab_prov, tab_bulk, tab_edit, tab_del = tabs
    else:
        tabs = st.tabs(["💳 Capital Collection Hub", "🛠️ Edit Terminal Profile"])
        tab_col, tab_edit = tabs
        tab_status_rev = tab_prov = tab_bulk = tab_del = None
        
    sub_map = {}
    if not df_matrix.empty:
        for _, row_series in df_matrix.iterrows():
            row_dict = row_series.to_dict()
            uid = row_dict.get('username')
            if uid:
                name = row_dict.get('customername', '')
                addr = str(row_dict.get('address', '')).strip()
                display_addr = (addr[:60] + '...') if len(addr) > 60 else addr
                sub_map[f"[{uid}] - {name} — {display_addr}"] = uid
                
    with tab_col:
        if not sub_map:
            st.info("No subscribers found.")
        else:
            collection_filter = st.radio(
                "Select Accounts to Manage", 
                ["All Accounts", "Unpaid / Partial / Suspended Only"], 
                horizontal=True,
                key="col_sub_filter"
            )
            available_map = {}
            for label, uid in sub_map.items():
                row_dict = df_matrix[df_matrix['username'] == uid].iloc[0].to_dict()
                status = str(row_dict.get('status', '')).upper()
                if collection_filter == "Unpaid / Partial / Suspended Only":
                    if status in ["UNPAID", "PARTIAL", "SUSPENDED"]:
                        available_map[label] = uid
                else:
                    available_map[label] = uid
            if not available_map:
                st.warning("No unpaid/partial/suspended accounts found in your current scope.")
            else:
                # Allow filtering by username / CNIC / phone before showing the name+address list
                col_filter = st.text_input("Search by username, CNIC or phone (optional)", key="col_select_filter")
                col_filter_clean = col_filter.strip().lower()

                display_map = {}
                for label, uid in available_map.items():
                    row = df_matrix[df_matrix['username'] == uid].iloc[0].to_dict()
                    name = str(row.get('customername', '')).strip()
                    addr = str(row.get('address', '')).strip()

                    # If a filter is provided, match against uid, cnic, phone, name, or address
                    if col_filter_clean:
                        cnic = str(row.get('cnic', '')).strip().lower()
                        phone = str(row.get('phone', '')).strip().lower()
                        if not (
                            col_filter_clean in str(uid).lower()
                            or col_filter_clean in cnic
                            or col_filter_clean in phone
                            or col_filter_clean in name.lower()
                            or col_filter_clean in addr.lower()
                        ):
                            continue

                    display_addr = (addr[:60] + '...') if len(addr) > 60 else addr
                    display_label = f"{name} — {display_addr}" if display_addr else f"{name}"

                    # Disambiguate duplicates by adding area or phone tail (still hide CNIC/username)
                    if display_label in display_map:
                        area = row.get('area', '')
                        disp2 = f"{display_label} — {area}" if area else f"{display_label} — #{uid[-4:]}"
                        if disp2 in display_map:
                            phone_tail = str(row.get('phone', ''))[-4:]
                            phone_tail = phone_tail if phone_tail else uid[-4:]
                            disp2 = f"{disp2} — {phone_tail}"
                        display_label = disp2

                    display_map[display_label] = uid

                if not display_map:
                    st.warning("No matching subscribers for the given filter.")
                else:
                    target_label = st.selectbox("Select Target Subscriber", list(display_map.keys()))
                    resolved_uid = display_map[target_label]
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
                    
                package_total_cost = base_bill * billing_months
                net_payable = package_total_cost + base_shift
                final_due = max(net_payable - discount, 0)
                
                st.markdown("### ⚡ Live Payment Overview Breakdown")
                cash_in = st.number_input("Capital Received From Customer (Rs.)", min_value=0, max_value=final_due, value=final_due)
                future_shift = max(0, int(final_due - cash_in))
                
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
                    <h4 style='color:{active_theme['accent']};'><b>Net Outstanding Due:</b> Rs. {final_due:,}</h4>
                    <hr style='border:1px solid {active_theme['border']};'>
                    <h4>🔮 <b>Auto Post Action State:</b> <span style='color:{status_color}; font-weight:bold;'>{calculated_status}</span></h4>
                    <p>💾 <b>New Balanceshift/Arrears Log:</b> Rs. {future_shift:,}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button("💳 POST TRANSACTION & EXTEND LINE", use_container_width=True):
                    today_dt = datetime.now()
                    current_expiry_str = str(node_row_dict.get('expirydate', '')).strip()
                    try:
                        old_expiry_dt = datetime.strptime(current_expiry_str, "%Y-%m-%d")
                        base_dt = today_dt if old_expiry_dt < today_dt else old_expiry_dt
                    except Exception:
                        base_dt = today_dt
                    new_expiry = (base_dt + relativedelta(months=billing_months)).strftime("%Y-%m-%d")
                    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                    
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s AND tenant_id = %s
                            """, (future_shift, calculated_status, new_expiry, resolved_uid, st.session_state['tenant_id']))
                            cursor.execute("""
                                INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven, tenant_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s, %s)
                            """, (invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('phone'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), node_row_dict.get('package'), int(cash_in), future_shift, pay_method, int(discount), st.session_state['tenant_id']))
                            insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "BILL_PAYMENT", f"Staff posted Rs. {cash_in} for user {resolved_uid}. Status updated to {calculated_status}, Arrears set to Rs. {future_shift}, Expiry to {new_expiry}.")
                            
                    st.success(f"🎉 Collection Recorded Cleanly! System Class Status: {calculated_status} | Extended To: {new_expiry}")
                    wa_context = {
                        "name": node_row_dict.get('customername', ''), "username": resolved_uid, "package": node_row_dict.get('package', ''), "paid": int(cash_in), "arrears": future_shift, "expiry": new_expiry, "method": pay_method
                    }
                    send_tenant_whatsapp(tenant_meta, node_row_dict.get('phone'), "bill_paid", wa_context)
                    st.session_state['recent_pdf_bytes'] = generate_receipt_pdf(TENANT_COMPANY_NAME, TENANT_SUPPORT_PHONE, invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('package'), cash_in, future_shift, pay_method)
                    st.session_state['recent_invoice_uuid'] = invoice_uuid
                    st.cache_data.clear()
                    st.rerun()
                
                if 'recent_pdf_bytes' in st.session_state:
                            st.download_button("📥 Download Generated PDF Receipt", data=st.session_state['recent_pdf_bytes'], file_name=f"Receipt_{st.session_state.get('recent_invoice_uuid', 'INV')}.pdf", mime="application/pdf", use_container_width=True)

    # --- NEW FEATURE: STATUS AND REVERSAL CONTROL TAB ---
    if tab_status_rev:
        with tab_status_rev:
            if not sub_map:
                st.info("No subscribers found.")
            else:
                st.markdown("### 🔄 Status Control & Payment Reversal Engine")
                target_label_sr = st.selectbox("Select Subscriber to Manage", list(sub_map.keys()), key="sb_status_rev")
                resolved_uid_sr = sub_map[target_label_sr]
                node_sr = df_matrix[df_matrix['username'] == resolved_uid_sr].iloc[0].to_dict()
                
                st.write("---")
                st.markdown("#### ⚙️ Line Connection Toggle (Disable / Active)")
                st.write(f"**Current Status:** `{node_sr.get('status')}` | **Phone:** {node_sr.get('phone')} | **Arrears:** Rs. {node_sr.get('balanceshift')}")
                
                col_st1, col_st2 = st.columns(2)
                with col_st1:
                    if st.button("🛑 TEMPORARILY DISABLE LINE", use_container_width=True):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE customers SET status = 'SUSPENDED' WHERE username = %s AND tenant_id = %s", (resolved_uid_sr, st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "DISABLE_LINE", f"Suspended line connection temporary for user {resolved_uid_sr}.")
                        
                        wa_context = {
                            "name": node_sr.get('customername', ''), "username": resolved_uid_sr, "package": node_sr.get('package', ''), "arrears": node_sr.get('balanceshift', 0), "expiry": node_sr.get('expirydate', ''), "helpline": TENANT_SUPPORT_PHONE
                        }
                        send_tenant_whatsapp(tenant_meta, node_sr.get('phone'), "expired_warning", wa_context)
                        st.success(f"✅ Connection for {node_sr.get('customername')} has been DISABLED (Suspended) & Alert sent via WhatsApp!")
                        st.cache_data.clear()
                        st.rerun()
                        
                with col_st2:
                    if st.button("🟢 RE-ACTIVATE LINE / MARK ACTIVE", use_container_width=True):
                        try:
                            current_arrears = int(float(str(node_sr.get('balanceshift', 0))))
                        except:
                            current_arrears = 0
                        new_status = "PAID" if current_arrears <= 0 else "UNPAID"
                        
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE customers SET status = %s WHERE username = %s AND tenant_id = %s", (new_status, resolved_uid_sr, st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "ACTIVATE_LINE", f"Re-activated connection for user {resolved_uid_sr}. Status set to {new_status}.")
                        
                        msg = f"Dear {node_sr.get('customername')}, Aapka connection wapas ACTIVE kar diya gaya hai. Shukriya! Support: {TENANT_SUPPORT_PHONE}"
                        clean_phone = str(node_sr.get('phone', '')).replace("-", "").strip()
                        if clean_phone.startswith("0"): clean_phone = "92" + clean_phone[1:]
                        if tenant_meta.get("wa_enabled") and tenant_meta.get("wa_instance_id") and tenant_meta.get("wa_token"):
                            url = f"https://api.green-api.com/waInstance{tenant_meta['wa_instance_id']}/sendMessage/{tenant_meta['wa_token']}"
                            try: requests.post(url, json={"chatId": f"{clean_phone}@c.us", "message": msg}, headers={'Content-Type': 'application/json'}, timeout=5)
                            except: pass
                            
                        st.success(f"✅ Connection for {node_sr.get('customername')} is now ACTIVE (Status: {new_status})!")
                        st.cache_data.clear()
                        st.rerun()
                        
                st.write("---")
                st.markdown("#### ↩️ Mistaken Payment Reversal (Undo Bill)")
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("""
                            SELECT invoiceid, amountpaid, remainingarrears, discountgiven, currentpackage, datetimestamp, paymentmethod 
                            FROM billing_history WHERE customerid = %s AND tenant_id = %s AND transactiontype = 'BILL_PAYMENT' 
                            ORDER BY datetimestamp DESC LIMIT 1
                        """, (resolved_uid_sr, st.session_state['tenant_id']))
                        last_invoice = cur.fetchone()
                        
                if not last_invoice:
                    st.warning("Is customer ki koi recent payment history nahi mili jise undo kiya ja sake.")
                else:
                    st.info(f"📋 **Last Invoice Registered:** `{last_invoice['invoiceid']}`\n"
                            f"* **Amount Paid:** Rs. {last_invoice['amountpaid']:,} | **Discount Given:** Rs. {last_invoice['discountgiven']:,}\n"
                            f"* **Gateway/Method:** {last_invoice['paymentmethod']} | **Date Timestamp:** {last_invoice['datetimestamp']}")
                            
                    if st.button("🚨 REVERSE & UNDO THIS TRANSACTION", type="primary", use_container_width=True):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    SELECT remainingarrears FROM billing_history WHERE customerid = %s AND tenant_id = %s AND invoiceid != %s 
                                    ORDER BY datetimestamp DESC LIMIT 1
                                """, (resolved_uid_sr, st.session_state['tenant_id'], last_invoice['invoiceid']))
                                prev_invoice_row = cursor.fetchone()
                                
                                try: base_bill = int(float(str(node_sr.get('billamount', 0))))
                                except: base_bill = 1500
                                
                                total_credited = int(last_invoice['amountpaid']) + int(last_invoice['discountgiven'])
                                est_months = max(1, int(round(total_credited / max(1, base_bill))))
                                
                                if prev_invoice_row:
                                    restored_arrears = prev_invoice_row[0]
                                else:
                                    restored_arrears = int(last_invoice['remainingarrears']) - (base_bill * est_months) + total_credited
                                    if restored_arrears < 0: restored_arrears = 0
                                    
                                current_exp_str = str(node_sr.get('expirydate', '')).strip()
                                try:
                                    current_exp_dt = datetime.strptime(current_exp_str, "%Y-%m-%d")
                                    restored_expiry = (current_exp_dt - relativedelta(months=est_months)).strftime("%Y-%m-%d")
                                except:
                                    restored_expiry = (datetime.now()).strftime("%Y-%m-%d")
                                    
                                cursor.execute("""
                                    UPDATE customers SET balanceshift = %s, status = 'UNPAID', expirydate = %s WHERE username = %s AND tenant_id = %s
                                """, (restored_arrears, restored_expiry, resolved_uid_sr, st.session_state['tenant_id']))
                                
                                cursor.execute("DELETE FROM billing_history WHERE invoiceid = %s AND tenant_id = %s", (last_invoice['invoiceid'], st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "REVERSE_PAYMENT", f"Undid invoice {last_invoice['invoiceid']} for user {resolved_uid_sr}. Arrears set back to Rs. {restored_arrears}, Expiry to {restored_expiry}.")
                                
                        st.success(f"🎉 Payment transaction reversed cleanly! Arrears restored back to Rs. {restored_arrears:,} and Expiry rolled back to {restored_expiry}. Now you can add a correct new payment workflow from the first tab.")
                        st.cache_data.clear()
                        st.rerun()

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
                    try: suggested_rate = int(float(str(area_pkgs[chosen_pkg])))
                    except: suggested_rate = 1500
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
                    elif not validate_username(in_id):
                        st.error("❌ Invalid username format. Use 3-20 alphanumeric characters.")
                    elif not validate_phone_number(in_phone):
                        st.error("❌ Invalid Pakistani phone number format.")
                    elif not validate_cnic(in_cnic):
                        st.error("❌ Invalid CNIC format. Use XXXXX-XXXXXXX-X format.")
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
                                    prov_wa_context = {
                                        "name": in_name, "username": in_id, "package": chosen_pkg, "bill": int(in_rate), "expiry": default_expiry
                                    }
                                    send_tenant_whatsapp(tenant_meta, norm_p, "new_connection", prov_wa_context)
                                    st.cache_data.clear()
                                    st.rerun()

    if tab_bulk:
        with tab_bulk:
            st.markdown("#### 📥 Download Sample Template")
            blueprint_df = pd.DataFrame([{
                "username": "ali786", "customername": "Muhammad Ali", "phone": "03001234567", "cnic": "35201-1234567-1", "package": "10 Mbps", "billamount": 1200, "area": "Model Town", "address": "House 45-B, Street 3", "onuserialnumber": "ONU-HW-9988X"
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
                                            if raw_amt.lower() in ['nan', 'none', '']: bill_amt = 1500
                                            else:
                                                try: bill_amt = int(float(raw_amt))
                                                except: bill_amt = 1500
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

    if tab_edit:
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
                    try: current_rate_val = int(float(str(edit_row_dict.get('billamount', 0))))
                    except: current_rate_val = 0
                    try: current_arrears_val = int(float(str(edit_row_dict.get('balanceshift', 0))))
                    except: current_arrears_val = 0
                    up_rate = st.number_input("Monthly Rate (Rs.)", value=current_rate_val, disabled=is_rate_disabled)
                    up_arrears = st.number_input("Outstanding Arrears (Rs.)", min_value=0, value=current_arrears_val, disabled=not is_management)
                    raw_stat = str(edit_row_dict.get('status', 'UNPAID')).upper()
                    safe_stat = raw_stat if raw_stat in ["PAID", "PARTIAL", "UNPAID", "SUSPENDED", "FREE"] else "UNPAID"
                    up_status = st.selectbox("Line Status", ["PAID", "PARTIAL", "UNPAID", "SUSPENDED", "FREE"], index=["PAID", "PARTIAL", "UNPAID", "SUSPENDED", "FREE"].index(safe_stat), disabled=is_status_disabled)
                    st.caption("🆓 To make a subscriber free: set Monthly Rate to 0 and choose status FREE.")
                    # Expiry date field - editable only by Owner/Admin
                    is_expiry_disabled = not is_management
                    existing_expiry = str(edit_row_dict.get('expirydate', '')).strip()
                    if is_expiry_disabled:
                        st.caption(f"🔒 Expiry Date: {existing_expiry} (Only Owner/Admin can change)")
                        up_expiry = existing_expiry
                    else:
                        up_expiry = st.text_input("Expiry Date (YYYY-MM-DD)", value=existing_expiry)
                    if st.form_submit_button("💾 COMMIT MODIFICATIONS"):
                        final_name = edit_row_dict.get('customername') if is_name_disabled else up_name
                        final_phone = edit_row_dict.get('phone') if is_phone_disabled else clean_and_validate_phone(up_phone)
                        final_address = edit_row_dict.get('address') if is_address_disabled else up_address
                        final_sn = edit_row_dict.get('onuserialnumber') if is_onu_disabled else up_sn
                        final_rate = int(current_rate_val) if is_rate_disabled else int(up_rate)
                        final_arrears = current_arrears_val if not is_management else int(up_arrears)
                        final_status = safe_stat if is_status_disabled else up_status
                        final_expiry = existing_expiry if is_expiry_disabled else up_expiry
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE customers SET customername=%s, phone=%s, address=%s, onuserialnumber=%s, billamount=%s, balanceshift=%s, status=%s, expirydate=%s WHERE username=%s AND tenant_id=%s
                                """, (final_name, final_phone, final_address, final_sn, final_rate, final_arrears, final_status, final_expiry, edit_uid, st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "UPDATE_CUSTOMER", f"Modified criteria for customer {edit_uid}. Status set to {final_status}. Expiry set to {final_expiry}.")
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
                        st.success(f"¼ Profiles completely purged.")
                        st.cache_data.clear()
                        st.rerun()

# ==========================================
# VIEW 3: LIFETIME AUDIT LEDGER HISTORY
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
    tab_all, tab_paid = st.tabs(["📜 All Ledger History", "✅ Paid Users (Date Filter)"])
    with tab_all:
        df_ledger = pd.DataFrame()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM billing_history WHERE tenant_id = %s ORDER BY datetimestamp DESC", (st.session_state['tenant_id'],))
                l_rows = cur.fetchall()
                if l_rows: df_ledger = pd.DataFrame(l_rows)
        if df_ledger.empty:
            st.info("No transactional logs found inside your tenant node registry.")
        else:
            df_ledger.columns = [c.lower() for c in df_ledger.columns]
            st.dataframe(df_ledger, use_container_width=True)
    with tab_paid:
        st.markdown("### 📅 Filter Paid Users by Date")
        col_d1, col_d2 = st.columns(2)
        with col_d1: start_date = st.date_input("Start Date", value=datetime.now().date())
        with col_d2: end_date = st.date_input("End Date", value=datetime.now().date())
        if st.button("🔍 Generate Paid Users Report", use_container_width=True):
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    query = """
                        SELECT customerid, customername, area, phone, amountpaid, datetimestamp, paymentmethod FROM billing_history 
                        WHERE tenant_id = %s AND transactiontype = 'BILL_PAYMENT' AND LEFT(datetimestamp, 10) >= %s AND LEFT(datetimestamp, 10) <= %s ORDER BY datetimestamp DESC
                    """
                    cur.execute(query, (st.session_state['tenant_id'], str(start_date), str(end_date)))
                    paid_rows = cur.fetchall()
            if paid_rows:
                df_paid = pd.DataFrame(paid_rows)
                st.success(f"✅ Found {len(df_paid)} paid transactions between {start_date} and {end_date}.")
                st.dataframe(df_paid, use_container_width=True)
                try:
                    total_col = int(float(str(df_paid['amountpaid'].sum())))
                    st.markdown(f"#### 💰 Total Collection Amount: **Rs. {total_col:,}**", unsafe_allow_html=True)
                except Exception: pass
            else:
                st.warning("⚠️ No paid records found in this date range.")

# ==========================================
# VIEW 4: SYSTEM ACCESS CONFIGS
# ==========================================
elif routing_node == "🔐 System Access Control":
    if str(st.session_state.get('user_role', '')).lower() not in ["owner", "admin"]:
        st.error("🔴 Administrative Elevation Clearance Required.")
    else:
        st.markdown("<div class='main-title'>🔐 SYSTEM ACCESS PANEL</div>", unsafe_allow_html=True)
        all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
        is_master_owner = (st.session_state['tenant_id'] == 'lynx' and st.session_state['username'] == 'owner')
        
        adm_tabs = st.tabs([
            "👑 SaaS Whitelabel License Manager" if is_master_owner else "🏢 Branding & WhatsApp Controls",
            "⚙️ Access Accounts Management", "📦 Fixed Packages Pricing Matrix", "🗺️ Dynamic Area Hubs Sector", "🛠️ Core Structural Destruct Engine", "📋 System Activity Logs", "💾 Data Backup Vault"
        ])
        
        if is_master_owner:
            with adm_tabs[0]:
                st.markdown("### 👑 LYNX MASTER CONTROL HUB")
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT * FROM system_tenants ORDER BY registration_date DESC")
                        all_tenants_rows = cur.fetchall()
                if all_tenants_rows: st.dataframe(pd.DataFrame(all_tenants_rows), use_container_width=True)
                tenant_select_list = [t['tenant_id'] for t in all_tenants_rows]
                if tenant_select_list:
                    st.write("---")
                    st.markdown("### 🛠️ EDIT TENANT MASTER CONTROL")
                    chosen_target_tenant = st.selectbox("Select Target Tenant ID to Modify / Control", tenant_select_list)
                    tenant_record = next(item for item in all_tenants_rows if item["tenant_id"] == chosen_target_tenant)
                    with st.form("master_super_control_form"):
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            m_tenant_id = st.text_input("Modify Tenant ID (Unique Code)", value=tenant_record["tenant_id"])
                            m_company_name = st.text_input("ISP Brand/Company Name", value=tenant_record["company_name"])
                            m_support_phone = st.text_input("Mobile / Support Helpline Number", value=tenant_record["support_phone"])
                        with col_m2:
                            m_owner_username = st.text_input("Owner Username Key", value=tenant_record["owner_username"])
                            m_license_toggle = st.checkbox("Grant Premium Software Activation Status", value=tenant_record["license_active"])
                            m_expiry_input = st.text_input("Set License Expiry Date (YYYY-MM-DD) [Blank = Lifetime]", value=tenant_record.get("license_expiry_date", ""))
                        st.markdown("##### 🔑 Security Override")
                        m_new_pass = st.text_input("Force Reset / Change Password (Leave blank to keep current)", type="password")
                        if st.form_submit_button("💾 LOCK MASTER CONFIGURATION & UPDATE ALL SECTOR ROWS"):
                            try:
                                with get_db_connection() as conn:
                                    with conn.cursor() as cursor:
                                        cursor.execute("""
                                            UPDATE system_tenants SET tenant_id = %s, company_name = %s, support_phone = %s, owner_username = %s, license_active = %s, license_expiry_date = %s WHERE tenant_id = %s
                                        """, (m_tenant_id.strip().lower(), m_company_name.strip(), m_support_phone.strip(), m_owner_username.strip().lower(), m_license_toggle, m_expiry_input.strip(), chosen_target_tenant))
                                        cursor.execute("""
                                            UPDATE users SET username = %s, tenant_id = %s WHERE username = %s AND tenant_id = %s
                                        """, (m_owner_username.strip().lower(), m_tenant_id.strip().lower(), tenant_record["owner_username"], chosen_target_tenant))
                                        if m_new_pass.strip():
                                            hashed_f = hash_password(m_new_pass.strip())
                                            cursor.execute("""
                                                UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s
                                            """, (hashed_f, m_owner_username.strip().lower(), m_tenant_id.strip().lower()))
                                        if m_tenant_id.strip().lower() != chosen_target_tenant:
                                            cursor.execute("UPDATE users SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                            cursor.execute("UPDATE customers SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                            cursor.execute("UPDATE areas SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                            cursor.execute("UPDATE packages SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                            cursor.execute("UPDATE billing_history SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                            cursor.execute("UPDATE activity_logs SET tenant_id = %s WHERE tenant_id = %s", (m_tenant_id.strip().lower(), chosen_target_tenant))
                                        insert_activity_log("lynx", "owner", "MASTER_CRITICAL_OVERRIDE", f"Full modification performed on entity: {chosen_target_tenant}")
                                st.success("🎉 Master control update written cleanly across database nodes!")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as err_m: st.error(f"SQL Execution Error: {err_m}")
                    st.write("---")
                    st.markdown("### 👑 Automated WhatsApp Settings for Master (`lynx`) Account")
                    with get_db_connection() as conn:
                        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                            cur.execute("SELECT whatsapp_enabled, whatsapp_instance_id, whatsapp_token, whatsapp_templates FROM system_tenants WHERE tenant_id = 'lynx'")
                            lynx_wa_row = cur.fetchone()
                    master_custom_templates = DEFAULT_WA_TEMPLATES.copy()
                    if lynx_wa_row and lynx_wa_row.get("whatsapp_templates"):
                        try:
                            loaded_m_templates = json.loads(lynx_wa_row["whatsapp_templates"])
                            if isinstance(loaded_m_templates, dict): master_custom_templates.update(loaded_m_templates)
                        except: pass
                    if lynx_wa_row:
                        master_wa_enabled_val = bool(lynx_wa_row.get("whatsapp_enabled", False))
                        master_wa_instance_val = str(lynx_wa_row.get("whatsapp_instance_id", "") or "")
                        master_wa_token_val = str(lynx_wa_row.get("whatsapp_token", "") or "")
                    else:
                        master_wa_enabled_val = False; master_wa_instance_val = ""; master_wa_token_val = ""
                    with st.form("master_lynx_whatsapp_form"):
                        l_wa_enabled = st.checkbox("Enable Automatic WhatsApp Alerts (Master)", value=master_wa_enabled_val)
                        l_wa_instance = st.text_input("Green-API Instance ID (Master)", value=master_wa_instance_val)
                        l_wa_token = st.text_input("Green-API Token (Master)", value=master_wa_token_val, type="password")
                        m_t_new = st.text_area("➕ New Connection Template (Master)", value=master_custom_templates["new_connection"], height=80)
                        m_t_paid = st.text_area("💳 Bill Paid Template (Master)", value=master_custom_templates["bill_paid"], height=80)
                        m_t_remind = st.text_area("⚠️ Bill Reminder Template (Master)", value=master_custom_templates["bill_reminder"], height=80)
                        m_t_exp = st.text_area("⏳ Line Suspended Template (Master)", value=master_custom_templates["expired_warning"], height=80)
                        if st.form_submit_button("💾 SAVE MASTER WHATSAPP CONFIGS"):
                            master_updated_templates = {"new_connection": m_t_new, "bill_paid": m_t_paid, "bill_reminder": m_t_remind, "expired_warning": m_t_exp}
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        UPDATE system_tenants SET whatsapp_enabled=%s, whatsapp_instance_id=%s, whatsapp_token=%s, whatsapp_templates=%s WHERE tenant_id='lynx'
                                    """, (l_wa_enabled, l_wa_instance, l_wa_token, json.dumps(master_updated_templates)))
                            st.success("✅ Lynx owner WhatsApp profile settings updated successfully!")
                            st.cache_data.clear()
                            st.rerun()
        else:
            with adm_tabs[0]:
                st.markdown("### 🏢 ISP Whitelabel Branding & WhatsApp Setup")
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT company_name, support_phone, whatsapp_enabled, whatsapp_instance_id, whatsapp_token, whatsapp_templates FROM system_tenants WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                        meta_row = cur.fetchone()
                current_custom_templates = DEFAULT_WA_TEMPLATES.copy()
                if meta_row and meta_row.get("whatsapp_templates"):
                    try:
                        loaded_templates = json.loads(meta_row["whatsapp_templates"])
                        if isinstance(loaded_templates, dict): current_custom_templates.update(loaded_templates)
                    except: pass
                with st.form("tenant_custom_branding_form"):
                    b_name = st.text_input("Company Brand Name Display", value=meta_row["company_name"] if meta_row else TENANT_COMPANY_NAME)
                    b_phone = st.text_input("Official Helpline Reference Phone", value=meta_row["support_phone"] if meta_row else TENANT_SUPPORT_PHONE)
                    st.write("---")
                    st.markdown("#### 🟢 Automated WhatsApp Settings (Green-API)")
                    wa_enabled = st.checkbox("Enable Automatic WhatsApp Alerts", value=meta_row.get("whatsapp_enabled", False) if meta_row else False)
                    wa_instance = st.text_input("Green-API Instance ID", value=meta_row.get("whatsapp_instance_id", "") if meta_row else "")
                    wa_token = st.text_input("Green-API Token", value=meta_row.get("whatsapp_token", "") if meta_row else "", type="password")
                    st.write("---")
                    st.markdown("#### 💬 Customizable Message Templates Engine")
                    t_new = st.text_area("➕ New Connection / Welcome Message Template", value=current_custom_templates["new_connection"], height=80)
                    t_paid = st.text_area("💳 Bill Paid Receipt Template", value=current_custom_templates["bill_paid"], height=80)
                    t_remind = st.text_area("⚠️ Active Due Bill Reminder Template", value=current_custom_templates["bill_reminder"], height=80)
                    t_exp = st.text_area("⏳ Line Suspended / Expired Warning Template", value=current_custom_templates["expired_warning"], height=80)
                    if st.form_submit_button("💾 SAVE BRANDING & CUSTOM WHATSAPP TEMPLATES"):
                        updated_templates_dict = {"new_connection": t_new, "bill_paid": t_paid, "bill_reminder": t_remind, "expired_warning": t_exp}
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    UPDATE system_tenants SET company_name=%s, support_phone=%s, whatsapp_enabled=%s, whatsapp_instance_id=%s, whatsapp_token=%s, whatsapp_templates=%s WHERE tenant_id=%s
                                """, (b_name, b_phone, wa_enabled, wa_instance, wa_token, json.dumps(updated_templates_dict), st.session_state['tenant_id']))
                                insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "UPDATE_BRANDING", f"Updated branding and WhatsApp custom templates configuration.")
                        st.success("🎉 Branding, Credentials and Message Templates Saved Successfully!")
                        st.cache_data.clear()
                        st.rerun()

        with adm_tabs[1]:
            st.markdown("### ⚙️ Access Accounts Management & Credentials")
            with st.form("owner_self_password_form"):
                current_self_pass = st.text_input("Enter Current Password Verification", type="password")
                new_self_pass = st.text_input("Enter New Secure Password", type="password")
                if st.form_submit_button("🔒 Securely Change My Password"):
                    if len(new_self_pass) < 6: st.error("Password string too short. Minimum 6 characters required.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("SELECT password FROM users WHERE username = %s AND tenant_id = %s", (st.session_state['username'], st.session_state['tenant_id']))
                                current_pwd_row = cursor.fetchone()
                                if current_pwd_row and verify_password(current_self_pass, current_pwd_row[0]):
                                    cursor.execute("UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s", (hash_password(new_self_pass), st.session_state['username'], st.session_state['tenant_id']))
                                    insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "CHANGE_PASSWORD", "System password updated.")
                                    st.success("🎉 Your credentials updated successfully!")
                                else: st.error("❌ Validation failed.")
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
                    updated_perms = {"customername": p_name_chk, "phone": p_phone_chk, "address": p_address_chk, "onuserialnumber": p_onu_chk, "billamount": p_rate_chk, "status": p_status_chk}
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("UPDATE system_tenants SET staff_permissions = %s WHERE tenant_id = %s", (json.dumps(updated_perms), st.session_state['tenant_id']))
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
                    if not new_username or not new_password: st.error("Complete mandatory fields.")
                    else:
                        assigned_areas_str = "ALL" if "ALL" in selected_clearance else ",".join(selected_clearance)
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO users (username, password, role, assignedarea, tenant_id) VALUES (%s, %s, %s, %s, %s)
                                    ON CONFLICT (username, tenant_id) DO UPDATE SET password=EXCLUDED.password, role=EXCLUDED.role, assignedarea=EXCLUDED.assignedarea
                                """, (new_username, hash_password(new_password), new_role, assigned_areas_str, st.session_state['tenant_id']))
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
            if not all_system_areas: st.info("💡 Empty State: Configure an active Operating Area first.")
            else:
                with st.form("matrix_package_form"):
                    p_name = st.text_input("Tarif ID Flag (e.g., 12 Mbps)").strip()
                    p_area = st.selectbox("Target Core Distribution Area Node", all_system_areas)
                    p_rate = st.number_input("Monthly Price Config (Rs.)", min_value=0, value=1500)
                    if st.form_submit_button("💾 LOCK TARIFF MATRIX ENTRY"):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO packages (packagename, areaname, packagerate, tenant_id) VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (packagename, areaname, tenant_id) DO UPDATE SET packagerate = EXCLUDED.packagerate
                                """, (p_name, p_area, int(p_rate), st.session_state['tenant_id']))
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
                                if active_deps > 0: st.error(f"❌ Purge Refused! Active profiles exist.")
                                else:
                                    cursor.execute("""
                                        DELETE FROM packages WHERE LOWER(packagename) = LOWER(%s) AND LOWER(areaname) = LOWER(%s) AND tenant_id = %s
                                    """, (target_del_pkg['packagename'], target_del_pkg['areaname'], st.session_state['tenant_id']))
                                    st.success(f"✅ Package removed successfully!")
                                    st.cache_data.clear()
                                    st.rerun()
                else: st.info("No active packages recorded.")

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
                            if assigned_clients > 0 or linked_packages > 0: st.error(f"❌ Deletion Aborted! Clear dependencies first.")
                            else:
                                cursor.execute("DELETE FROM areas WHERE LOWER(areaname) = LOWER(%s) AND tenant_id = %s", (del_area, st.session_state['tenant_id']))
                                st.success(f"✅ Area wiped cleanly.")
                                st.cache_data.clear()
                                st.rerun()

        with adm_tabs[4]:
            if str(st.session_state.get('user_role', '')).lower() != "owner": st.warning("🔒 Section locked. Only the Organization Owner can wipe datasets.")
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
                            else: st.error("❌ Authentication Refused!")

        with adm_tabs[5]:
            st.markdown("### 📋 System Activity & User Login Logs")
            try:
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        if is_master_owner:
                            cur.execute("SELECT timestamp, tenant_id, username, action_type, description FROM activity_logs ORDER BY timestamp DESC LIMIT 500")
                        else:
                            cur.execute("SELECT timestamp, username, action_type, description FROM activity_logs WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT 300", (st.session_state['tenant_id'],))
                        log_rows = cur.fetchall()
                if log_rows:
                    st.dataframe(pd.DataFrame(log_rows), use_container_width=True)
                else:
                    st.info("Abhi tak koi logs jama nahi huay. Agar activity logs tab missing ho, تو ایڈمن ڈیش بورڈ چیک کریں یا دوبارہ اپلیکیشن رنز کریں۔")
            except Exception as log_err:
                logger.error(f"Logs pull karne mein masla aya: {log_err}")
                st.error(f"Logs pull karne mein masla aya: {log_err}")
                st.info("🔧 اگر یہ ایرر ٹیبل نہ ہونے کی وجہ سے ہو تو، صفحہ دوبارہ لوڈ کریں یا لاگ فنکشن دوبارہ initialize کریں۔")

        with adm_tabs[-1]:
            st.markdown("### 💾 Dynamic Data Backup Vault")
            backup_scope = "Tenant Isolated Backup"
            if is_master_owner: backup_scope = st.radio("Select Backup Scope", ["Current Tenant Only", "Full Server Master Backup"])
            if st.button("⚡ GENERATE SYSTEM BACKUP SNAPSHOT", use_container_width=True):
                with st.spinner("Database snapshot collect kiya ja raha hai..."):
                    try:
                        backup_payload = {}
                        tables = ['system_tenants', 'users', 'customers', 'areas', 'packages', 'billing_history', 'activity_logs']
                        with get_db_connection() as conn:
                            for t_name in tables:
                                # Use parameterized query to prevent SQL injection
                                if backup_scope == "Tenant Isolated Backup" or not is_master_owner:
                                    q = "SELECT * FROM " + t_name + " WHERE tenant_id = %s"
                                    params = [st.session_state['tenant_id']]
                                else:
                                    q = "SELECT * FROM " + t_name
                                    params = []
                                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as b_cur:
                                    b_cur.execute(q, params)
                                    bak_rows = b_cur.fetchall()
                                backup_payload[t_name] = bak_rows if bak_rows else []
                        st.session_state['safe_backup_json'] = json.dumps(backup_payload, default=str, indent=4)
                        insert_activity_log(st.session_state['tenant_id'], st.session_state['username'], "GENERATE_BACKUP", f"Exported state backup.")
                        st.success("✅ Snapshot processed successfully! Niche button se save karein.")
                    except Exception as b_err: st.error(f"Backup Error: {b_err}")
            if 'safe_backup_json' in st.session_state:
                st.download_button(
                    label="📥 DOWNLOAD PREPARED BACKUP FILE (.JSON)", data=st.session_state['safe_backup_json'], file_name=f"Backup_{st.session_state['tenant_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", use_container_width=True
                )

# ==========================================
# VIEW 5: SUBSCRIBER SELF-SERVICE INVENTORY
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown(f"<div class='main-title'>📱 SUBSCRIBER SELF-SERVICE PORTAL</div>", unsafe_allow_html=True)
    col_p1, col_p2 = st.columns(2)
    with col_p1: portal_tenant = st.text_input("Enter ISP Provider Code").strip().lower()
    with col_p2: portal_input = st.text_input("Enter Username / Mobile No.")
    if portal_tenant and portal_input:
        t_meta = fetch_active_tenant_metadata(portal_tenant)
        cleaned_p = clean_and_validate_phone(portal_input)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if cleaned_p: cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND (LOWER(username) = LOWER(%s) OR phone = %s)", [portal_tenant, portal_input.strip(), cleaned_p])
                else: cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND LOWER(username) = LOWER(%s)", [portal_tenant, portal_input.strip()])
                c_rows = cur.fetchall()
        if not c_rows: st.error("❌ No active profile found.")
        else:
            c_dict = c_rows[0]
            try:
                bill_amt_val = int(float(str(c_dict.get('billamount', 0))))
                balance_shift_val = int(float(str(c_dict.get('balanceshift', 0))))
            except Exception: bill_amt_val = 0; balance_shift_val = 0
            st.markdown(f"""
            <div class="client-card" style="border: 2px solid {active_theme['accent']};">
                <h2 style="color:{active_theme['accent']}; text-align:center; font-weight:bold;">📄 DIGITAL BILL & QUOTATION</h2>
                <p style="text-align:center; color:#9ca3af; font-size:13px;">Provider: {html.escape(str(t_meta["name"]))} | Helpline: {html.escape(str(t_meta["phone"]))}</p>
                <hr style="with: 1px solid {active_theme['border']};">
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
