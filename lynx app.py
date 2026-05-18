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
from sqlalchemy import create_engine, text

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
    page_title="LYNX Fiber Enterprise ERP v54.2", 
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        background: #3b82f6 !important; color: #ffffff !important; border: 2px solid #60a5fa !important;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
    }
    [data-testid="stSidebar"] div.stButton > button {
        background: #111827 !important; color: #9ca3af !important; border: 1px solid #374151 !important;
        border-radius: 8px !important; padding: 10px !important; text-align: left !important; justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] div.stButton > button:hover { background: #10b981 !important; color: white !important; border: 1px solid #10b981 !important; }
    
    .table-wrapper { overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; margin-top: 15px; }
    .premium-table { width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; background: #111827; }
    .premium-table th { background: #1f2937; color: #10b981; padding: 14px; text-align: left; font-size: 13px; border-bottom: 2px solid #374151; white-space: nowrap; text-transform: uppercase;}
    .premium-table td { padding: 14px; border-bottom: 1px solid #1f2937; font-size: 13px; color: #e5e7eb; white-space: nowrap; }
    .main-title { color: #10b981; font-size: 28px; font-weight: 800; text-align: center; margin-bottom: 25px; }
    .front-login-box { max-width: 450px; margin: 60px auto; background: #111827; padding: 40px; border-radius: 16px; border: 1px solid #10b981; box-shadow: 0 15px 35px rgba(16, 185, 129, 0.2); }
    .nav-header { font-size: 12px; font-weight: bold; color: #6b7280; text-transform: uppercase; margin-bottom: 10px; padding-left: 5px; }
    .system-card { background: #1e293b; border: 1px solid #374151; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center; }
    .system-card h4 { margin: 0 0 10px 0; color: #10b981; font-size: 16px; font-weight: bold;}
    .system-card p { margin: 5px 0; font-size: 14px; color: #e5e7eb; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. DIRECT DATABASE ENGINE (SQLALCHEMY POOLING)
# ==========================================
encoded_pass = urllib.parse.quote_plus("DlLaglY98SkOzDq2")
DB_URL = f"postgresql://postgres.hvnqenuoyaefojzshvik:{encoded_pass}@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"

@st.cache_resource
def get_sqlalchemy_engine():
    return create_engine(
        DB_URL,
        pool_size=15,             
        max_overflow=25,          
        pool_timeout=30,          
        pool_recycle=1800         
    )

@contextmanager
def get_db_connection():
    engine = get_sqlalchemy_engine()
    conn = None
    try:
        conn = engine.raw_connection()
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
                    areaname TEXT PRIMARY KEY
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
                    packagename TEXT PRIMARY KEY,
                    packagerate INTEGER NOT NULL CHECK(packagerate >= 0)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('Admin', 'Staff')),
                    assignedarea TEXT DEFAULT 'ALL'
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
                    amountpaid INTEGER NOT NULL CHECK(amountpaid >= 0),
                    remainingarrears INTEGER NOT NULL CHECK(remainingarrears >= 0),
                    transactiontype TEXT NOT NULL,
                    paymentmethod TEXT NOT NULL,
                    discountgiven INTEGER DEFAULT 0
                )
            """)
            
            # Default Data Injection
            cursor.execute("SELECT COUNT(*) FROM areas")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO areas VALUES ('Sanghoi System')")
                cursor.execute("INSERT INTO areas VALUES ('Saeela System')")
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin'")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users VALUES ('admin', 'lynxadmin123', 'Admin', 'ALL')")
                cursor.execute("INSERT INTO users VALUES ('staff', 'lynxstaff123', 'Staff', 'Sanghoi System')")
            
            cursor.execute("SELECT COUNT(*) FROM packages")
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO packages VALUES ('15 Mbps Fiber', 1500)")
                cursor.execute("INSERT INTO packages VALUES ('25 Mbps Fiber', 2000)")
                cursor.execute("INSERT INTO packages VALUES ('35 Mbps Fiber', 2500)")
                
        conn.commit()

try:
    build_database_schema()
except Exception as e:
    st.error(f"Schema Builder Failed: {e}")

def fetch_live_matrix():
    try:
        engine = get_sqlalchemy_engine()
        df = pd.read_sql_query("SELECT * FROM customers ORDER BY customername ASC", engine)
        if not df.empty:
            df.columns = [c.lower() for c in df.columns]
            extended_cols = GLOBAL_TARGET_ORDER + [c for c in df.columns if c not in GLOBAL_TARGET_ORDER]
            return df.reindex(columns=extended_cols)
        return pd.DataFrame(columns=GLOBAL_TARGET_ORDER + ['balanceshift', 'status', 'expirydate'])
    except Exception:
        return pd.DataFrame()

def fetch_active_areas():
    engine = get_sqlalchemy_engine()
    df = pd.read_sql_query("SELECT areaname FROM areas ORDER BY areaname ASC", engine)
    if not df.empty:
        return df.iloc[:, 0].tolist()
    return ["Sanghoi System", "Saeela System"]

# ==========================================
# 4. ROUTING ENGINE CONFIGURATION & GLOBAL GATEWAY
# ==========================================
col_port1, col_port2 = st.columns([1, 4])

with col_port1:
    if st.button("📱 Client Portal" if not st.session_state['portal_mode'] else "🖥️ ERP Panel", use_container_width=True):
        st.session_state['portal_mode'] = not st.session_state['portal_mode']
        st.rerun()

show_client_portal = st.session_state['portal_mode']

if show_client_portal:
    routing_node = "📱 Client Portal"
else:
    if not st.session_state['authenticated']:
        st.markdown("<div class='front-login-box'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:#10b981; font-weight:900; margin-bottom:5px;'>LYNX FIBER NET</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#9ca3af; margin-bottom:30px;'>Enterprise ERP System v54.2</p>", unsafe_allow_html=True)
        
        user_input = (st.text_input("Username Key", key="front_user") or "").strip().lower()
        pass_input = st.text_input("Security Password", type="password", key="front_pass")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Authorize & Launch Dashboard", use_container_width=True):
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT role, username, assignedarea FROM users WHERE LOWER(username) = %s AND password = %s", (user_input, pass_input))
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
# VIEW 1: CORE ANALYTICS DASHBOARD (FIXED & COMPLETED)
# ==========================================
if routing_node == "📊 Core Analytics Dashboard":
    st.markdown("<div class='main-title'>⚡ LYNX FIBER ENTERPRISE ANALYTICS</div>", unsafe_allow_html=True)
    
    df_matrix = fetch_live_matrix()
    all_system_areas = fetch_active_areas()
    
    if df_matrix.empty:
        st.warning("⚠️ Operational Database is currently empty.")
    else:
        # Filter based on Assigned Area for Staff
        if st.session_state['assigned_area'] != "ALL":
            df_matrix = df_matrix[df_matrix['area'].str.lower() == st.session_state['assigned_area'].lower()]
            all_system_areas = [st.session_state['assigned_area']]

        st.markdown("### 🌐 Active System Node Overview")
        
        # Loop through areas and display stats in 2 columns grid
        for i in range(0, len(all_system_areas), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(all_system_areas):
                    current_hub = all_system_areas[i + j]
                    segment = df_matrix[df_matrix['area'].str.lower() == current_hub.lower()]
                    
                    total_users = len(segment)
                    paid_users = len(segment[segment['status'] == 'PAID'])
                    unpaid_users = len(segment[segment['status'] == 'UNPAID'])
                    total_revenue = segment['billamount'].sum()
                    
                    with cols[j]:
                        st.markdown(f"""
                        <div class='system-card'>
                            <h4>📍 {current_hub}</h4>
                            <p>Total Subscribes: <b>{total_users}</b></p>
                            <p>✅ Paid: <b>{paid_users}</b> | ❌ Unpaid: <b>{unpaid_users}</b></p>
                            <p>Expected Recovery: <b>PKR {total_revenue:,}/-</b></p>
                        </div>
                        """, unsafe_allow_html=True)

        # Main Table view below metrics
        st.markdown("### 📋 Complete Customer Directory")
        
        # Render clean HTML Table for Mobile View
        display_df = df_matrix[GLOBAL_TARGET_ORDER + ['status', 'expirydate']]
        
        table_html = "<div class='table-wrapper'><table class='premium-table'><thead><tr>"
        for col in display_df.columns:
            table_html += f"<th>{col.upper()}</th>"
        table_html += "</tr></thead><tbody>"
        
        for _, row in display_df.iterrows():
            table_html += "<tr>"
            for col in display_df.columns:
                val = row[col]
                if col == 'status':
                    color = "#10b981" if val == 'PAID' else "#ef4444"
                    table_html += f"<td style='color:{color}; font-weight:bold;'>{val}</td>"
                else:
                    table_html += f"<td>{html.escape(str(val))}</td>"
            table_html += "</tr>"
        table_html += "</tbody></table></div>"
        
        st.markdown(table_html, unsafe_allow_html=True)

# ==========================================
# VIEW 2: OPERATIONAL BILLING CENTER
# ==========================================
elif routing_node == "👥 Operational Billing Center":
    st.markdown("<div class='main-title'>👥 OPERATIONAL BILLING CENTER</div>", unsafe_allow_html=True)
    df_matrix = fetch_live_matrix()
    
    if df_matrix.empty:
        st.info("No active users found.")
    else:
        # Search Box for Quick Access
        search_q = st.text_input("🔍 Search Customer (Name, Username, Phone, ONU SN):", "").strip().lower()
        
        if search_q:
            filtered_df = df_matrix[
                df_matrix['customername'].str.lower().str.contains(search_q) |
                df_matrix['username'].str.lower().str.contains(search_q) |
                df_matrix['phone'].str.contains(search_q) |
                df_matrix['onuserialnumber'].str.lower().str.contains(search_q)
            ]
        else:
            filtered_df = df_matrix

        # Display filtered records
        if filtered_df.empty:
            st.error("No record matches your search.")
        else:
            st.markdown(f"**Found Records:** {len(filtered_df)}")
            # Render table or action logic here...
            st.dataframe(filtered_df[GLOBAL_TARGET_ORDER + ['status']])

# ==========================================
# VIEW 3: CLIENT PORTAL MODE
# ==========================================
elif routing_node == "📱 Client Portal":
    st.markdown("<div class='main-title'>📱 LYNX FIBER CUSTOMER PORTAL</div>", unsafe_allow_html=True)
    client_search = st.text_input("Enter your Registered Mobile Number / Username:", key="client_phone_search")
    
    if client_search:
        df_matrix = fetch_live_matrix()
        user_row = df_matrix[
            (df_matrix['phone'] == client_search) | 
            (df_matrix['username'].str.lower() == client_search.lower())
        ]
        
        if not user_row.empty:
            user_data = user_row.iloc[0]
            st.markdown(f"""
            <div class='front-login-box' style='margin-top:20px; border-color:#3b82f6;'>
                <h3 style='color:#3b82f6; text-align:center;'>👋 Welcome, {user_data['customername']}</h3>
                <hr style='border-color:#1f2937;'>
                <p><b>Username:</b> {user_data['username']}</p>
                <p><b>Package Profile:</b> {user_data['package']}</p>
                <p><b>Monthly Bill:</b> PKR {user_data['billamount']}/-</p>
                <p><b>Account Status:</b> <span style='color:{"#10b981" if user_data["status"]=="PAID" else "#ef4444"}; font-weight:bold;'>{user_data['status']}</span></p>
                <p><b>Expiry / Renew Date:</b> {user_data['expirydate']}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error("❌ Profile not found. Please verify your details or contact support.")