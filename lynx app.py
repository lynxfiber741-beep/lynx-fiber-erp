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
# 🛑 SAAS MASTER CONFIGURATION & HIDDEN REGISTRY
# ==========================================
DISTRIBUTOR_NAME = "Lynx Fiber Internet"

# 🤫 HIDDEN SUPER-ADMIN REGISTRY
MASTER_NOTIFY_NUMBERS = ["03215943786", "03118808741"]

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
    st.session_state['tenant_id'] = "lynx"  # Default master tenant
if 'assigned_areas' not in st.session_state:
    st.session_state['assigned_areas'] = ["ALL"]  
if 'current_node' not in st.session_state:
    st.session_state['current_node'] = "📊 Core Analytics Dashboard"
if 'portal_mode' not in st.session_state:
    st.session_state['portal_mode'] = False

GLOBAL_TARGET_ORDER = [
    "username", "customername", "phone", "cnic", "package",
    "billamount", "area", "address", "onuserialnumber"
]

# ==========================================
# 2. SECURE POOLED DATABASE REGISTRY
# ==========================================
try:
    DB_URL = st.secrets["DB_URL"]
except Exception:
    DB_URL = "postgresql://postgres.snbmurjcggthdvxyxyrd:DlLaglY98SkOzDq2@aws-1-ap-southeast-1.pooler.southeast-1.pooler.southeast-1.pooler.southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"

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

# ==========================================
# 🛑 AUTO-REPAIR MULTI-TENANT SCHEMA ENGINE
# ==========================================
def build_database_schema():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Create Tenants Master Control Table safely
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_tenants (
                    tenant_id TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    support_phone TEXT NOT NULL,
                    owner_username TEXT NOT NULL,
                    license_active BOOLEAN DEFAULT FALSE,
                    registration_date TEXT NOT NULL
                )
            """)
            
            # 2. Check and Alter 'users' table column safe patch
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='users' AND column_name='tenant_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'lynx'")
                try:
                    cursor.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_pkey")
                except Exception:
                    pass
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT NOT NULL, 
                    password TEXT NOT NULL, 
                    role TEXT NOT NULL CHECK(role IN ('Owner', 'Admin', 'Staff')), 
                    assignedarea TEXT DEFAULT 'ALL',
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            
            # 3. Patching 'customers' table structures safely
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='tenant_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN tenant_id TEXT DEFAULT 'lynx'")
                try:
                    cursor.execute("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_pkey")
                except Exception:
                    pass
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    username TEXT NOT NULL, customername TEXT NOT NULL, phone TEXT NOT NULL,
                    cnic TEXT DEFAULT '', package TEXT NOT NULL, billamount INTEGER NOT NULL CHECK(billamount >= 0),
                    area TEXT NOT NULL, address TEXT DEFAULT '', onuserialnumber TEXT DEFAULT '',
                    balanceshift INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'UNPAID', expirydate TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (username, tenant_id)
                )
            """)
            
            # 4. Patching 'areas' table structures safely
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='areas' AND column_name='tenant_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE areas ADD COLUMN tenant_id TEXT DEFAULT 'lynx'")
                try:
                    cursor.execute("ALTER TABLE areas DROP CONSTRAINT IF EXISTS areas_pkey")
                except Exception:
                    pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS areas (
                    areaname TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (areaname, tenant_id)
                )
            """)
            
            # 5. Patching 'packages' table structures safely
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='packages' AND column_name='tenant_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE packages ADD COLUMN tenant_id TEXT DEFAULT 'lynx'")
                try:
                    cursor.execute("ALTER TABLE packages DROP CONSTRAINT IF EXISTS packages_pkey")
                except Exception:
                    pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    packagename TEXT NOT NULL, areaname TEXT NOT NULL, packagerate INTEGER NOT NULL CHECK(packagerate >= 0),
                    tenant_id TEXT NOT NULL DEFAULT 'lynx',
                    PRIMARY KEY (packagename, areaname, tenant_id)
                )
            """)
            
            # 6. Patching 'billing_history' table structures safely
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='billing_history' AND column_name='tenant_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE billing_history ADD COLUMN tenant_id TEXT DEFAULT 'lynx'")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS billing_history (
                    invoiceid TEXT PRIMARY KEY, customerid TEXT NOT NULL, customername TEXT NOT NULL, area TEXT NOT NULL,
                    phone TEXT, datetimestamp TEXT NOT NULL, currentpackage TEXT NOT NULL, amountpaid INTEGER NOT NULL CHECK(amountpaid >= 0),
                    remainingarrears INTEGER NOT NULL, transactiontype TEXT NOT NULL, paymentmethod TEXT NOT NULL, discountgiven INTEGER DEFAULT 0,
                    tenant_id TEXT NOT NULL DEFAULT 'lynx'
                )
            """)
            
            # Seed Default Core Control Entities
            cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO system_tenants VALUES ('lynx', 'Lynx Fiber Pvt Ltd', '03135776263', 'owner', TRUE, %s)
                """, (datetime.now().strftime("%Y-%m-%d"),))
                
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner' AND tenant_id = 'lynx'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users VALUES ('owner', %s, 'Owner', 'ALL', 'lynx')", (hash_password('lynxowner123'),))
                
        conn.commit()

# Run the database setup
build_database_schema()

# ==========================================
# 3. HIGH PERFORMANCE RETRIEVALS & TENANT ISOLATION FETCH
# ==========================================
@st.cache_data(ttl=2)
def fetch_active_tenant_metadata(tenant_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT company_name, support_phone, license_active FROM system_tenants WHERE tenant_id = %s", (tenant_id,))
                res = cur.fetchone()
        if res:
            return {
                "name": res["company_name"],
                "phone": res["support_phone"],
                "active": res["license_active"]
            }
    except Exception:
        pass
    return {"name": "Lynx Fiber Pvt Ltd", "phone": "03135776263", "active": True}

# Load Metadata context dynamically based on session
tenant_meta = fetch_active_tenant_metadata(st.session_state['tenant_id'])
TENANT_COMPANY_NAME = tenant_meta["name"]
TENANT_SUPPORT_PHONE = tenant_meta["phone"]

# Check License Lock Layer
if not tenant_meta["active"]:
    st.error(f"⚠️ 🔐 SOFTWARE LICENSE SUSPENDED! Please contact the master administrator to renew your system access ledger. Provider: {DISTRIBUTOR_NAME}")
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
    if not phone_str or str(phone_str).lower() == 'nan': return ""
    cleaned = str(phone_str).strip()
    if cleaned.endswith('.0'): cleaned = cleaned[:-2]
    cleaned = re.sub(r"\D", "", cleaned)
    if cleaned.startswith("92"): cleaned = "0" + cleaned[2:]
    if len(cleaned) == 10 and cleaned.startswith("3"): cleaned = "0" + cleaned
    return cleaned

# Page Configuration Setup
st.set_page_config(
    page_title=f"Enterprise ERP Panel — Powered by {DISTRIBUTOR_NAME}", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Mobile UI Styles CSS Engine
st.markdown(f"""
    <style>
    .stApp [data-testid="stHeader"] {{ background: transparent !important; height: 50px !important; }}
    .stApp .block-container {{ padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 100% !important; }}
    .stApp {{ background-color: #0b0f19; color: #f1f5f9; font-family: sans-serif; }}
    [data-testid="stSidebar"] {{ background-color: #111827; border-right: 1px solid #1f2937; }}
    
    div[data-testid="stTextInput"] input, 
    div[data-testid="stNumberInput"] input,
    div[data-testid="stTextArea"] textarea {{
        color: #000000 !important; background-color: #ffffff !important;
        font-weight: bold !important; font-size: 16px !important;
        border: 2px solid #3b82f6 !important; border-radius: 8px !important;
    }}
    div[data-baseweb="select"] > div {{
        background-color: #ffffff !important; color: #000000 !important;
        font-weight: bold !important; font-size: 16px !important;
        border: 2px solid #3b82f6 !important; border-radius: 8px !important;
    }}
    div[data-baseweb="select"] span, div[data-baseweb="select"] div {{ color: #000000 !important; }}
    ul[role="listbox"] li {{ color: #000000 !important; background-color: #ffffff !important; font-weight: 600 !important; }}
    label, p, .stMarkdown div {{ color: #e5e7eb !important; font-weight: 500; }}
    
    div.stButton > button, div.stFormSubmitButton > button {{
        background: linear-gradient(135deg, #1e293b 0%, #111827 100%) !important;
        color: #3b82f6 !important; border: 2px solid #3b82f6 !important;
        border-radius: 12px !important; padding: 15px !important;
        font-weight: bold !important; font-size: 15px !important;
        transition: all 0.3s ease; box-shadow: 0 4px 10px rgba(0,0,0,0.3) !important;
        width: 100% !important; display: flex !important; align-items: center !important; justify-content: center !important;
    }}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
        background: #3b82f6 !important; color: #ffffff !important;
        border: 2px solid #60a5fa !important; box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
    }}
    
    .table-wrapper {{ overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; margin-top: 15px; }}
    .premium-table {{ width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; background: #111827; }}
    .premium-table th {{ background: #1f2937; color: #10b981; padding: 14px; text-align: left; font-size: 13px; border-bottom: 2px solid #374151; white-space: nowrap; text-transform: uppercase;}}
    .premium-table td {{ padding: 14px; border-bottom: 1px solid #1f2937; font-size: 13px; color: #e5e7eb; white-space: nowrap; }}
    .btn-action {{ padding: 6px 12px; border-radius: 6px; font-weight: bold; text-decoration: none; font-size: 12px; display: inline-block; margin-right: 4px; }}
    .btn-c {{ background-color: #2563eb; color: white !important; }}
    .btn-w {{ background-color: #16a34a; color: white !important; }}
    .client-card {{ background: #1f2937; padding: 20px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 15px; }}
    .main-title {{ color: #10b981; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }}
    .front-login-box {{ 
        max-width: 450px; margin: 40px auto; background: #111827; padding: 40px; 
        border-radius: 16px; border: 1px solid #10b981; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); 
    }}
    .system-card {{ background: #1e293b; border: 1px solid #475569; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }}
    .system-card h4 {{ margin: 0 0 10px 0; color: #3b82f6; font-size: 16px; font-weight: bold;}}
    .saas-footer {{ text-align: center; font-size: 12px; color: #6b7280; margin-top: 50px; padding: 15px; border-top: 1px solid #1f2937; }}
    .saas-footer b {{ color: #3b82f6; }}
    </style>
    """, unsafe_allow_html=True)

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
        # MAIN DUAL GATEWAY LOG IN SCREEN
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
                    if not t_meta["active"]:
                        st.error("⚠️ This system access instance is locked by the main distributor.")
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
                            
                        st.session_state['current_node'] = "📊 Core Analytics Dashboard"
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.error("❌ Invalid Tenant, Username, or Password Node Variant.")
                    
        with register_tab:
            st.markdown("<h3 style='text-align:center; color:#3b82f6;'>SaaS Tenant Onboarding</h3>", unsafe_allow_html=True)
            st.caption("Naya ISP Account banana ke liye niche diye gaye parameters fill karein:")
            
            with st.form("saas_tenant_registration_form"):
                reg_tenant_id = st.text_input("Choose Unique Tenant Code (e.g., falcon, alpha)").strip().lower()
                reg_company_name = st.text_input("ISP Company Full Brand Name").strip()
                reg_support_phone = st.text_input("Official Support Helpline Number").strip()
                reg_owner_user = st.text_input("Create Master Admin Username").strip().lower()
                reg_owner_pass = st.text_input("Create Master Admin Password", type="password")
                
                if st.form_submit_button("➕ SUBMIT ACTIVATION APP PROPOSAL"):
                    if not reg_tenant_id or not reg_company_name or not reg_owner_user or not reg_owner_pass:
                        st.error("❌ Tamam mandatory fields fill karna lazmi hain.")
                    elif len(reg_tenant_id) < 3:
                        st.error("❌ Tenant Code kam se kam 3 harf ka hona chahiye.")
                    else:
                        try:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("SELECT COUNT(*) FROM system_tenants WHERE tenant_id = %s", (reg_tenant_id,))
                                    if cursor.fetchone()[0] > 0:
                                        st.error("❌ Box unique variant already recorded on server logs.")
                                    else:
                                        cursor.execute("""
                                            INSERT INTO system_tenants (tenant_id, company_name, support_phone, owner_username, license_active, registration_date)
                                            VALUES (%s, %s, %s, %s, FALSE, %s)
                                        """, (reg_tenant_id, reg_company_name, reg_support_phone, reg_owner_user, datetime.now().strftime("%Y-%m-%d")))
                                        
                                        cursor.execute("""
                                            INSERT INTO users (username, password, role, assignedarea, tenant_id)
                                            VALUES (%s, %s, 'Owner', 'ALL', %s)
                                        """, (reg_owner_user, hash_password(reg_owner_pass), reg_tenant_id))
                                        
                                        conn.commit()
                                        st.success("🎉 Registration Proposal Saved onto Supabase Ledger Engine!")
                                        
                                        alert_payload = f"🔒 LYNX SAAS LICENSE ALERT:\nNew enterprise system activation initiated.\nTenant ID: {reg_tenant_id}\nISP Company: {reg_company_name}\nHelpline Ref: {reg_support_phone}\nStatus: Verification Needed."
                                        encoded_msg = urllib.parse.quote(alert_payload)
                                        
                                        st.markdown("#### 📲 Send Activation Alert to Distributor")
                                        st.warning("Niche diye gaye links par click karke Admin ko activate karne ki request bhejein:")
                                        
                                        st.markdown(f'<a href="https://wa.me/92{MASTER_NOTIFY_NUMBERS[0]}?text={encoded_msg}" target="_blank" style="background:#10b981; color:white; padding:12px; border-radius:8px; display:block; text-align:center; text-decoration:none; font-weight:bold; margin-bottom:10px;">📲 Dispatch Verification Code (Line 1)</a>', unsafe_allow_html=True)
                                        st.markdown(f'<a href="https://wa.me/92{MASTER_NOTIFY_NUMBERS[1]}?text={encoded_msg}" target="_blank" style="background:#3b82f6; color:white; padding:12px; border-radius:8px; display:block; text-align:center; text-decoration:none; font-weight:bold;">📲 Dispatch Verification Code (Line 2)</a>', unsafe_allow_html=True)
                        except Exception as ex:
                            st.error(f"Transaction Fault Error: {ex}")
        
        st.markdown(f"<p style='text-align:center; font-size:11px; color:#4b5563; margin-top:20px;'>Powered by {DISTRIBUTOR_NAME}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    else:
        routing_node = st.session_state['current_node']

# NAVIGATION SIDEBAR WITH TENANT AWARENESS (🛠️ CRASH PATCH INTEGRATED)
if st.session_state['authenticated'] and not st.session_state['portal_mode']:
    with st.sidebar:
        st.markdown(f"<h2 style='color:#10b981; font-weight:900; text-align:center; margin-bottom:5px;'>{str(TENANT_COMPANY_NAME).upper()}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-size:11px; color:#6b7280;'>Domain context: <b>{str(st.session_state.get('tenant_id', 'lynx'))}</b></p>", unsafe_allow_html=True)
        st.markdown("<div class='nav-header'>System Navigation</div>", unsafe_allow_html=True)
        
        if st.button("📊 Core Analytics Dashboard", use_container_width=True):
            st.session_state['current_node'] = "📊 Core Analytics Dashboard"; st.rerun()
        if st.button("👥 Operational Billing Center", use_container_width=True):
            st.session_state['current_node'] = "👥 Operational Billing Center"; st.rerun()
        if st.button("📜 Lifetime Ledger History", use_container_width=True):
            st.session_state['current_node'] = "📜 Lifetime Ledger History"; st.rerun()
            
        if str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"]:
            if st.button("🔐 System Access Control", use_container_width=True):
                st.session_state['current_node'] = "🔐 System Access Control"; st.rerun()
            
        st.write("---")
        assigned_list = st.session_state.get('assigned_areas', ["ALL"])
        area_display = "All Systems" if "ALL" in assigned_list else ", ".join(assigned_list)
        
        # 🛠️ Bulletproof Safe String Rendering to fix the AttributeError
        username_display = str(st.session_state.get('username', 'UNKNOWN')).upper()
        role_display = str(st.session_state.get('user_role', 'STAFF')).upper()
        
        st.markdown(f"<p style='text-align:center; color:#9ca3af;'>👤 Active: <b>{username_display}</b><br>📍 Role: <b style='color:#10b981;'>{role_display}</b><br>🗺️ Areas:<br><span style='color:#60a5fa; font-size:12px;'><b>{area_display}</b></span></p>", unsafe_allow_html=True)
        if st.button("🔒 Logout System", use_container_width=True):
            st.session_state['authenticated'] = False; st.rerun()

# ==========================================
# VIEW 1: CORE ANALYTICS DASHBOARD
# ==========================================
if routing_node == "📊 Core Analytics Dashboard":
    st.markdown(f"<div class='main-title'>⚡ {str(TENANT_COMPANY_NAME).upper()} ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_high_profile = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
    cards_display_areas = all_system_areas.copy()
    if not is_high_profile and "ALL" not in st.session_state['assigned_areas']:
        cards_display_areas = [a for a in all_system_areas if any(a.lower() == s.lower() for s in st.session_state['assigned_areas'])]
    
    if not all_system_areas:
        st.info("💡 Database mapping is empty. Configure your sectors inside System Access Control.")
    elif df_matrix.empty:
        st.warning("⚠️ Operational Database is currently empty. No subscribers registered.")
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
            system_filter = st.selectbox("🌐 Area System Filter", filter_options)
            if system_filter != "ALL ASSIGNED SYSTEMS":
                base_df = base_df[base_df['area'].str.lower() == system_filter.lower()]
        else:
            filter_options = ["ALL SYSTEMS"] + all_system_areas
            system_filter = st.selectbox("🌐 Area System Filter", filter_options)
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
                    wa_payload = f"Dear {row_dict.get('customername','')}, {TENANT_COMPANY_NAME} Bill Update. Arrears: Rs.{row_dict.get('balanceshift',0)}. Expiry: {row_dict.get('expirydate','')}. Support: {TENANT_SUPPORT_PHONE}"
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
            
    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONS CENTER (ISOLATED TRANSACTIONS)
# ==========================================
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 TRANSACTION & TERMINAL OPERATIONS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_isolated_matrix(st.session_state['tenant_id'])
    all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
    is_management = (str(st.session_state.get('user_role', '')).lower() in ["owner", "admin"])
    
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
            
            st.info(f"📊 Rate: Rs. {node_row_dict.get('billamount')} | Arrears: Rs. {node_row_dict.get('balanceshift')} | Current Expiry: {node_row_dict.get('expirydate')}")
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
                    
                    today_dt = datetime.now()
                    current_expiry_str = str(node_row_dict.get('expirydate', '')).strip()
                    try:
                        old_expiry_dt = datetime.strptime(current_expiry_str, "%Y-%m-%d")
                        base_dt = today_dt if old_expiry_dt < (today_dt - relativedelta(months=3)) else old_expiry_dt
                    except Exception:
                        base_dt = today_dt
                    
                    new_expiry = (base_dt + relativedelta(months=billing_months)).strftime("%Y-%m-%d")
                    invoice_uuid = f"INV-{uuid.uuid4().hex[:10].upper()}"
                    
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("UPDATE customers SET balanceshift = %s, status = %s, expirydate = %s WHERE username = %s AND tenant_id = %s", (future_shift, new_state, new_expiry, resolved_uid, st.session_state['tenant_id']))
                            cursor.execute("""
                                INSERT INTO billing_history (invoiceid, customerid, customername, area, phone, datetimestamp, currentpackage, amountpaid, remainingarrears, transactiontype, paymentmethod, discountgiven, tenant_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'BILL_PAYMENT', %s, %s, %s)
                            """, (invoice_uuid, resolved_uid, node_row_dict.get('customername'), node_row_dict.get('area'), node_row_dict.get('phone'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), node_row_dict.get('package'), cash_in, future_shift, pay_method, discount, st.session_state['tenant_id']))
                        conn.commit()
                    st.success(f"🎉 Collection Recorded Cleanly! Extended Lock To: {new_expiry}")
                    st.cache_data.clear(); st.rerun()

    if is_management:
        # TAB 2: PROVISION NEW CLIENT WITH TENANT SCOPE
        with tabs[1]:
            if not all_system_areas:
                st.error("❌ Register an Area Sector inside System Access Controls first.")
            else:
                in_area = st.selectbox("Select Target Hub Location", all_system_areas)
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT packagename, packagerate FROM packages WHERE areaname = %s AND tenant_id = %s", (in_area, st.session_state['tenant_id']))
                        area_pkgs = dict(cur.fetchall())
                
                with st.form("add_client_form_v67"):
                    in_id = st.text_input("Desired Unique Username Key").strip().lower()
                    in_name = st.text_input("Customer Full Name").strip()
                    in_phone = st.text_input("Phone Number").strip()
                    in_cnic = st.text_input("CNIC Number").strip()
                    
                    chosen_pkg = st.selectbox(f"Valid Packages for {in_area}", list(area_pkgs.keys())) if area_pkgs else "Standard Manual Baseline"
                    suggested_rate = area_pkgs[chosen_pkg] if area_pkgs else 1500
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
                                    cursor.execute("SELECT COUNT(*) FROM customers WHERE username = %s AND tenant_id = %s", (in_id, st.session_state['tenant_id']))
                                    if cursor.fetchone()[0] > 0:
                                        st.error("❌ Identity Key / Username duplicate inside your tenant logs.")
                                    else:
                                        default_expiry = (datetime.now() + relativedelta(months=1)).strftime("%Y-%m-%d")
                                        cursor.execute("""
                                            INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate, tenant_id)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s, %s)
                                        """, (in_id, in_name, norm_p, in_cnic, chosen_pkg, in_rate, in_area, in_address, in_sn, default_expiry, st.session_state['tenant_id']))
                                        conn.commit()
                                        st.success(f"🚀 Profile allocated safely! Expiry: {default_expiry}.")
                                        st.cache_data.clear(); st.rerun()

        # TAB 3: Bulk Import Isolated Rows
        with tabs[2]:
            uploaded_file = st.file_uploader("Upload Excel Sheet Matrix Log", type=['xlsx', 'csv'])
            if uploaded_file:
                try:
                    df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                    st.write("📊 Data Preview:", df_upload.head(3))
                    
                    if st.button("⚡ Save Sheet Rows to Live Engine"):
                        df_upload.columns = [c.lower() for c in df_upload.columns]
                        inserted_rows = 0
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                for idx, row in df_upload.iterrows():
                                    clean_id = str(row['username']).strip().lower()
                                    default_expiry = (datetime.now() + relativedelta(months=1)).strftime("%Y-%m-%d")
                                    cursor.execute("""
                                        INSERT INTO customers (username, customername, phone, cnic, package, billamount, area, address, onuserialnumber, balanceshift, status, expirydate, tenant_id)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 'UNPAID', %s, %s)
                                        ON CONFLICT (username, tenant_id) DO NOTHING
                                    """, (clean_id, str(row['customername']), clean_and_validate_phone(str(row['phone'])), str(row.get('cnic','')), str(row.get('package','Standard')), int(float(str(row.get('billamount', 1500)))), str(row['area']), str(row.get('address','')), str(row.get('onuserialnumber','')), default_expiry, st.session_state['tenant_id']))
                                    inserted_rows += 1
                            conn.commit()
                        st.success(f"🚀 Bulk Isolation processed {inserted_rows} entries cleanly!")
                        st.cache_data.clear()
                except Exception as ex:
                    st.error(f"Processing Error: {ex}")

    # TAB: Edit Profiles Engine Block
    with tabs[-1]:
        if not sub_map: st.info("Empty logs.")
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
                
                if st.form_submit_button("💾 COMMIT MODIFICATIONS"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE customers SET customername=%s, phone=%s, address=%s, onuserialnumber=%s, billamount=%s, status=%s
                                WHERE username=%s AND tenant_id=%s
                            """, (up_name, clean_and_validate_phone(up_phone), up_address, up_sn, up_rate, up_status, edit_uid, st.session_state['tenant_id']))
                        conn.commit()
                    st.success("Profile Changes Logged within Tenant context.")
                    st.cache_data.clear(); st.rerun()

# ==========================================
# VIEW 3: LIFETIME AUDIT LEDGER HISTORY
# ==========================================
elif routing_node == "📜 Lifetime Ledger History":
    st.markdown("<div class='main-title'>📜 ACCOUNT LEDGER METRICS & AUDIT TRAIL</div>", unsafe_allow_html=True)
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

# ==========================================
# VIEW 4: SYSTEM ACCESS CONFIGS (TENANT CONTEXT)
# ==========================================
elif routing_node == "🔐 System Access Control":
    if str(st.session_state.get('user_role', '')).lower() not in ["owner", "admin"]:
        st.error("🔴 Administrative Elevation Clearance Required.")
    else:
        st.markdown("<div class='main-title'>🔐 SYSTEM ACCESS & MULTI-TENANT CONFIGURATION PANEL</div>", unsafe_allow_html=True)
        all_system_areas = fetch_isolated_areas(st.session_state['tenant_id'])
        
        adm_tabs = st.tabs([
            "👑 SaaS Whitelabel License Manager" if st.session_state['tenant_id'] == 'lynx' else "🏢 Branding Metadata Controls",
            "⚙️ Access Accounts Management", 
            "📦 Fixed Packages Pricing Matrix", 
            "🗺️ Dynamic Area Hubs Sector",
            "🛠️ Core Structural Destruct Engine"
        ])

        # TAB 0: LYNX EXCLUSIVE MASTER COMMAND HUB
        if st.session_state['tenant_id'] == 'lynx':
            with adm_tabs[0]:
                st.markdown("### 👑 LYNX MASTER ENTERPRISE DISTRIBUTOR COMMAND HUB")
                st.caption("Umer Bhai! Yahan se aap kisi bhi naye registered ISP dealer ka system aur license status live approve ya block kar sakte hain.")
                
                with get_db_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("SELECT * FROM system_tenants ORDER BY registration_date DESC")
                        all_tenants_rows = cur.fetchall()
                
                if all_tenants_rows:
                    df_tenants_view = pd.DataFrame(all_tenants_rows)
                    st.write("#### 📋 Live Registered Tenants Matrix Logs")
                    st.dataframe(df_tenants_view, use_container_width=True)
                    
                    st.write("---")
                    st.markdown("#### ⚙️ Update Tenant License Activation State")
                    tenant_select_list = [t['tenant_id'] for t in all_tenants_rows if t['tenant_id'] != 'lynx']
                    
                    if not tenant_select_list:
                        st.info("Aap ke ilawa abhi tak koi aur tenant register nahi hua.")
                    else:
                        chosen_target_tenant = st.selectbox("Select Target Tenant ID to Modify Access", tenant_select_list, key="lic_tenant_select")
                        current_status = next(item for item in all_tenants_rows if item["tenant_id"] == chosen_target_tenant)["license_active"]
                        
                        new_license_toggle = st.checkbox("Grant Premium Software Activation Access Link", value=current_status)
                        
                        if st.button("💾 LOCK CONFIGURATION STATUS KEY"):
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("UPDATE system_tenants SET license_active = %s WHERE tenant_id = %s", (new_license_toggle, chosen_target_tenant))
                                conn.commit()
                            st.success(f"🎉 Tenant '{chosen_target_tenant}' dynamic lock access updated successfully!")
                            st.cache_data.clear(); st.rerun()
                        
                        st.write("---")
                        
                        # --- 👑 FORCE RESET DOSRAY ISP KA PASSWORD LAYER ---
                        st.markdown("#### 🔑 Force Reset Other ISP User Password")
                        st.caption("Yahan se aap kisi bhi dosray ISP tenant ke master admin ya sub-user ka password directly update kar sakte hain.")
                        
                        pwd_target_tenant = st.selectbox("Select Target ISP (Tenant ID)", tenant_select_list, key="pwd_tenant_select")
                        
                        with get_db_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT username, role FROM users WHERE tenant_id = %s ORDER BY username ASC", (pwd_target_tenant,))
                                tenant_users = cur.fetchall()
                        
                        if tenant_users:
                            user_options = [f"{u[0]} ({u[1]})" for u in tenant_users]
                            selected_user_string = st.selectbox("Select User to Reset Password", user_options, key="pwd_user_select")
                            resolved_username = selected_user_string.split(" (")[0]
                            
                            new_isp_password = st.text_input("Enter New Password Structure", type="password", key="new_isp_pwd_input")
                            
                            if st.button("🔒 FORCE UPDATE USER PASSWORD", use_container_width=True):
                                if len(new_isp_password) < 4:
                                    st.error("❌ Security Password kam se kam 4 characters ka hona chahiye.")
                                else:
                                    hashed_new_pwd = hash_password(new_isp_password)
                                    with get_db_connection() as conn:
                                        with conn.cursor() as cursor:
                                            cursor.execute(
                                                "UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s", 
                                                (hashed_new_pwd, resolved_username, pwd_target_tenant)
                                            )
                                        conn.commit()
                                    st.success(f"🎉 Success! ISP '{pwd_target_tenant}' ke User '{resolved_username}' ka password securely change kar diya gaya hai.")
                                    st.cache_data.clear()
                        else:
                            st.info("Is selected ISP segment mein filhal koi user records majood nahi hain.")
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
                            conn.commit()
                        st.success("Metadata Saved cleanly inside cluster engine.")
                        st.cache_data.clear(); st.rerun()

        # TAB 1: ACCESS ACCOUNTS MANAGEMENT
        with adm_tabs[1]:
            st.markdown("### ⚙️ Access Accounts Management & Credentials")
            with st.form("owner_self_password_form"):
                new_self_pass = st.text_input("Enter New Password Structure", type="password")
                if st.form_submit_button("🔒 Securely Change My Password"):
                    if len(new_self_pass) < 4: st.error("Password string too short.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE users SET password = %s WHERE username = %s AND tenant_id = %s", (hash_password(new_self_pass), st.session_state['username'], st.session_state['tenant_id']))
                            conn.commit()
                        st.success("🎉 Updated successfully!")
            
            st.write("---")
            st.markdown("#### ➕ Provision Sub-User Entity (Admin / Staff Node)")
            with st.form("create_subuser_form"):
                new_username = st.text_input("Entity Username ID").strip().lower()
                new_password = st.text_input("Security Access Code / Password", type="password")
                new_role = st.selectbox("System Architecture Role Level", ["Admin", "Staff"])
                assigned_areas_input = st.text_input("Allocated Sector Clearance", value="ALL").strip()
                
                if st.form_submit_button("🚀 Inject User Profile Node"):
                    if not new_username or not new_password: st.error("Complete mandatory fields.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO users (username, password, role, assignedarea, tenant_id)
                                    VALUES (%s, %s, %s, %s, %s)
                                    ON CONFLICT (username, tenant_id) DO UPDATE 
                                    SET password = EXCLUDED.password, role = EXCLUDED.role, assignedarea = EXCLUDED.assignedarea
                                """, (new_username, hash_password(new_password), new_role, assigned_areas_input, st.session_state['tenant_id']))
                            conn.commit()
                        st.success(f"✅ User node locked onto your isolation segment.")

        # TAB 2: PACKAGES PRICING MATRIX
        with adm_tabs[2]:
            st.markdown("### 📦 Location Pricing Configurator")
            if not all_system_areas: st.info("💡 Empty State: Configure an active Operating Area first.")
            else:
                with st.form("matrix_package_form"):
                    p_name = st.text_input("Tarif ID Flag (e.g., 12 Mbps)").strip()
                    p_area = st.selectbox("Target Core Distribution Area Node", all_system_areas)
                    p_rate = st.number_input("Monthly Price Config (Rs.)", min_value=0, value=1500)
                    
                    if st.form_submit_button("💾 LOCK TARIFF MATRIX ENTRY"):
                        if not p_name: st.error("Name field mandatory.")
                        else:
                            with get_db_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute("""
                                        INSERT INTO packages (packagename, areaname, packagerate, tenant_id) 
                                        VALUES (%s, %s, %s, %s) 
                                        ON CONFLICT (packagename, areaname, tenant_id) 
                                        DO UPDATE SET packagerate = EXCLUDED.packagerate
                                    """, (p_name, p_area, p_rate, st.session_state['tenant_id']))
                                conn.commit()
                            st.success(f"✅ Configured matrix row entry.")
                            st.cache_data.clear(); st.rerun()

            st.write("---")
            st.markdown("#### ❌ Remove Package Profile")
            live_packages_list = fetch_isolated_packages(st.session_state['tenant_id'])
            if live_packages_list:
                pkg_options_map = {f"📦 {p['packagename']} — 📍 Area: {p['areaname']} (Rs. {p['packagerate']})": (p['packagename'], p['areaname']) for p in live_packages_list}
                selected_remove_label = st.selectbox("Select Package to Remove", list(pkg_options_map.keys()))
                if st.button("🗑️ DELETE CHOSEN PACKAGE PROFILE"):
                    t_pkg, t_ar = pkg_options_map[selected_remove_label]
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("DELETE FROM packages WHERE packagename = %s AND areaname = %s AND tenant_id = %s", (t_pkg, t_ar, st.session_state['tenant_id']))
                        conn.commit()
                    st.success("Package wiped successfully.")
                    st.cache_data.clear(); st.rerun()

        # TAB 3: DYNAMIC AREA HUBS SECTOR
        with adm_tabs[3]:
            st.markdown("### 🗺️ Sector Node Operations")
            with st.form("add_area_sector_form"):
                new_area_name = st.text_input("Enter New Network Location Name").strip()
                if st.form_submit_button("➕ COMMIT SECTOR DEPLOYMENT REGISTRY"):
                    if new_area_name:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("INSERT INTO areas VALUES (%s, %s) ON CONFLICT DO NOTHING", (new_area_name, st.session_state['tenant_id']))
                            conn.commit()
                        st.success(f"✅ Area logged to network.")
                        st.cache_data.clear(); st.rerun()
            
            st.write("---")
            st.markdown("#### ❌ Remove Operating Area Hub Node")
            if all_system_areas:
                chosen_delete_area = st.selectbox("Select Area Hub to Remove", all_system_areas)
                if st.button("🗑️ PERMANENTLY REMOVE AREA HUB FROM LEDGER"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT COUNT(*) FROM customers WHERE LOWER(area) = LOWER(%s) AND tenant_id = %s", (chosen_delete_area, st.session_state['tenant_id']))
                            customer_count = cursor.fetchone()[0]
                    if customer_count > 0:
                        st.error(f"❌ Aborted: Binding active with {customer_count} customers within this sector.")
                    else:
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DELETE FROM packages WHERE LOWER(areaname) = LOWER(%s) AND tenant_id = %s", (chosen_delete_area, st.session_state['tenant_id']))
                                cursor.execute("DELETE FROM areas WHERE LOWER(areaname) = LOWER(%s) AND tenant_id = %s", (chosen_delete_area, st.session_state['tenant_id']))
                            conn.commit()
                        st.success("Area Hub successfully purged.")
                        st.cache_data.clear(); st.rerun()

        # TAB 4: ISOLATED DESTRUCT MODULE
        with adm_tabs[4]:
            if str(st.session_state.get('user_role', '')).lower() != "owner":
                st.warning("🔒 Section locked.")
            else:
                st.markdown("### ☢️ Tenant Schema Single Destruction Module")
                st.caption("Yeh action sirf aapke is current tenant scope ka saara data clear karega. Baqi tenants safe rahenge.")
                purge_password = st.text_input("Verify Owner Password Passphrase", type="password", key="purge_pass_gate")
                if st.button("☢️ INITIATE COMPLETE SEGMENT DATA PURGE"):
                    with get_db_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT password FROM users WHERE username = %s AND role='Owner' AND tenant_id = %s", (st.session_state['username'], st.session_state['tenant_id']))
                            match_p = cursor.fetchone()
                    if match_p and verify_password(purge_password, match_p[0]):
                        with get_db_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("DELETE FROM billing_history WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM customers WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM packages WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                                cursor.execute("DELETE FROM areas WHERE tenant_id = %s", (st.session_state['tenant_id'],))
                            conn.commit()
                        st.success("🚀 Your tenant segment has been cleared cleanly!")
                        st.cache_data.clear(); st.rerun()
                    else:
                        st.error("❌ Cryptographic verification failure.")

# ==========================================
# VIEW 5: SUBSCRIBER SELF-SERVICE INVENTORY
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown(f"<div class='main-title'>📱 SUBSCRIBER SELF-SERVICE PORTAL</div>", unsafe_allow_html=True)
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        portal_tenant = st.text_input("Enter ISP Provider Domain Code (e.g., lynx)").strip().lower()
    with col_p2:
        portal_input = st.text_input("Enter Subscriber Username / Mobile No.")
    
    if portal_tenant and portal_input:
        t_meta = fetch_active_tenant_metadata(portal_tenant)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM customers WHERE tenant_id = %s AND (LOWER(username) = LOWER(%s) OR phone = %s)", [portal_tenant, portal_input.strip(), clean_and_validate_phone(portal_input)])
                c_rows = cur.fetchall()
        if not c_rows: 
            st.error("❌ No active profile linked on server records for this provider.")
        else:
            c_dict = c_rows[0]
            st.markdown(f"""
            <div class="client-card" style="border: 2px solid #3b82f6;">
                <h2 style="color:#3b82f6; text-align:center; margin-bottom:5px; font-weight:bold;">📄 DIGITAL BILL & ACCOUNT QUOTATION</h2>
                <p style="text-align:center; color:#9ca3af; font-size:13px; margin-bottom:20px;">Provider: {t_meta["name"]} | Helpline: {t_meta["phone"]}</p>
                <hr style="border: 1px solid #374151;">
                <h3 style="color:#10b981; margin-top:15px;">👤 Account ID: {html.escape(str(c_dict.get('username','')))}</h3>
                <p><b>CUSTOMER NAME:</b> {html.escape(str(c_dict.get('customername','')))}</p>
                <p><b>CONNECTED AREA:</b> {html.escape(str(c_dict.get('area','')))}</p>
                <p><b>ACTIVE PACKAGE PLAN:</b> {html.escape(str(c_dict.get('package','')))}</p>
                <p><b>MONTHLY CHARGES:</b> Rs. {c_dict.get('billamount', 0):,}</p>
                <p style="color:#f43f5e; font-weight:bold;"><b>OUTSTANDING ARREARS:</b> Rs. {c_dict.get('balanceshift', 0):,}</p>
                <p style="color:#10b981; font-weight:bold;"><b>LINE EXPIRY DATE:</b> {c_dict.get('expirydate')}</p>
                <hr style="border: 1px solid #374151; margin-top:20px;">
                <p style="text-align:center; font-size:11px; color:#6b7280;">Maintained via systems licensing by: {DISTRIBUTOR_NAME}</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown(f"<div class='saas-footer'>Distributed & Licensed by: <b>{DISTRIBUTOR_NAME}</b></div>", unsafe_allow_html=True)