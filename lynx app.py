import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import urllib.parse
from datetime import datetime
from contextlib import contextmanager
import bcrypt

# ==========================================
# CONFIGURATION & POOLING
# ==========================================
DISTRIBUTOR_NAME = "Lynx Fiber Internet"
MASTER_NOTIFY_NUMBERS = ["03215943786", "03118808741"]
DB_URL = "postgresql://postgres.snbmurjcggthdvxyxyrd:DlLaglY98SkOzDq2@aws-1-ap-southeast-1.pooler.southeast-1.pooler.southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"

master_pool = SimpleConnectionPool(1, 15, dsn=DB_URL)

@contextmanager
def get_db_connection():
    conn = master_pool.getconn()
    conn.autocommit = False
    try: yield conn
    except:
        conn.rollback()
        raise
    finally: master_pool.putconn(conn)

# ==========================================
# LICENSE & AUTO-SUSPEND ENGINE
# ==========================================
def check_license_and_remind(tenant_id):
    if tenant_id == 'lynx': return True
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT license_expiry, license_active FROM system_tenants WHERE tenant_id = %s", (tenant_id,))
            res = cur.fetchone()
    
    if not res: return False
    
    expiry_date = datetime.strptime(res['license_expiry'], "%Y-%m-%d")
    today = datetime.now()
    delta = (expiry_date - today).days

    # Auto-Lock if expired
    if delta < 0:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE system_tenants SET license_active = FALSE WHERE tenant_id = %s", (tenant_id,))
            conn.commit()
        st.error("❌ Aapka Portal Expire ho chuka hai. Admin se rabta karein.")
        return False

    # 7-Day Warning
    if 0 <= delta <= 7:
        if delta == 0:
            st.error(f"🚨 ALERT: Portal AAJ expire ho raha hai! Recharge: {MASTER_NOTIFY_NUMBERS[0]}")
        else:
            st.warning(f"⚠️ Warning: Aapka Portal {delta} din mein expire hoga. Recharge: {MASTER_NOTIFY_NUMBERS[0]}")
    
    return res['license_active']

# ==========================================
# UI & MAIN APP LOGIC
# ==========================================
def main():
    st.set_page_config(page_title="Lynx Fiber Portal", layout="wide")
    
    # Initialize Session
    if 'authenticated' not in st.session_state: st.session_state['authenticated'] = False
    
    # Simple Auth Check
    if not st.session_state['authenticated']:
        st.title("🔐 Lynx Fiber Login")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            # Yahan apna authentication logic add karein
            st.session_state['authenticated'] = True
            st.session_state['tenant_id'] = 'lynx' # Example
            st.rerun()
        return

    # License Enforcement
    if not check_license_and_remind(st.session_state['tenant_id']):
        st.stop()

    # Dashboard Logic
    st.sidebar.title(f"Welcome, {DISTRIBUTOR_NAME}")
    st.title("📊 Lynx Fiber Management")
    
    # Yahan aap apna baqi ka main dashboard code paste karein
    st.success("System is running and License is Active.")

if __name__ == "__main__":
    main()