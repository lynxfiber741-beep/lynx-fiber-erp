"""
FastAPI Backend for Offline Sync Operations
This is a separate backend service for handling offline data synchronization.
Run this alongside the Streamlit app for full offline sync functionality.

Installation:
pip install fastapi uvicorn psycopg2-binary

Run:
uvicorn sync_api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2 import pool
from datetime import datetime
import os
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lynx ERP Sync API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
DB_URL = os.getenv("DB_URL", "postgresql://user:password@localhost/lynx_erp")
sync_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL)

def get_db_connection():
    conn = sync_pool.getconn()
    conn.autocommit = True
    try:
        yield conn
    finally:
        sync_pool.putconn(conn)

@app.get("/")
async def root():
    return {"message": "Lynx ERP Sync API", "status": "online"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/sync/payment")
async def sync_payment(payment_data: Dict[str, Any]):
    """
    Sync offline payment to database
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Insert payment into billing_history
                cursor.execute("""
                    INSERT INTO billing_history 
                    (tenant_id, username, payment_date, amount, payment_method, notes, recorded_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    payment_data.get('tenant_id'),
                    payment_data.get('username'),
                    payment_data.get('payment_date', datetime.now()),
                    payment_data.get('amount'),
                    payment_data.get('payment_method', 'CASH'),
                    payment_data.get('notes', 'Offline sync'),
                    payment_data.get('recorded_by', 'staff')
                ))
                
                # Update customer balance
                cursor.execute("""
                    UPDATE customers 
                    SET balanceshift = balanceshift - %s,
                        status = 'PAID'
                    WHERE tenant_id = %s AND username = %s
                """, (
                    payment_data.get('amount'),
                    payment_data.get('tenant_id'),
                    payment_data.get('username')
                ))
                
        return {"status": "success", "message": "Payment synced successfully"}
    except Exception as e:
        logger.error(f"Payment sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/customer")
async def sync_customer(customer_data: Dict[str, Any]):
    """
    Sync offline customer creation/update to database
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if customer exists
                cursor.execute("""
                    SELECT username FROM customers 
                    WHERE tenant_id = %s AND username = %s
                """, (customer_data.get('tenant_id'), customer_data.get('username')))
                
                if cursor.fetchone():
                    # Update existing customer
                    cursor.execute("""
                        UPDATE customers SET
                            customername = %s,
                            phone = %s,
                            cnic = %s,
                            address = %s,
                            package = %s,
                            billamount = %s,
                            area = %s,
                            onuserialnumber = %s
                        WHERE tenant_id = %s AND username = %s
                    """, (
                        customer_data.get('customername'),
                        customer_data.get('phone'),
                        customer_data.get('cnic'),
                        customer_data.get('address'),
                        customer_data.get('package'),
                        customer_data.get('billamount'),
                        customer_data.get('area'),
                        customer_data.get('onuserialnumber'),
                        customer_data.get('tenant_id'),
                        customer_data.get('username')
                    ))
                else:
                    # Insert new customer
                    cursor.execute("""
                        INSERT INTO customers 
                        (tenant_id, username, customername, phone, cnic, address, package, billamount, area, onuserialnumber, status, balanceshift)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        customer_data.get('tenant_id'),
                        customer_data.get('username'),
                        customer_data.get('customername'),
                        customer_data.get('phone'),
                        customer_data.get('cnic'),
                        customer_data.get('address'),
                        customer_data.get('package'),
                        customer_data.get('billamount'),
                        customer_data.get('area'),
                        customer_data.get('onuserialnumber'),
                        'UNPAID',
                        0
                    ))
                
        return {"status": "success", "message": "Customer synced successfully"}
    except Exception as e:
        logger.error(f"Customer sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync/batch")
async def sync_batch(operations: List[Dict[str, Any]]):
    """
    Sync multiple offline operations in batch
    """
    results = []
    for operation in operations:
        try:
            if operation.get('type') == 'payment':
                result = await sync_payment(operation.get('data', {}))
            elif operation.get('type') == 'customer':
                result = await sync_customer(operation.get('data', {}))
            else:
                result = {"status": "error", "message": "Unknown operation type"}
            results.append(result)
        except Exception as e:
            results.append({"status": "error", "message": str(e)})
    
    return {"results": results, "total": len(results)}

@app.get("/api/sync/status")
async def sync_status(tenant_id: str):
    """
    Get sync status for a tenant
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Get last sync time (you'd need to add a sync_log table for this)
                cursor.execute("""
                    SELECT MAX(payment_date) as last_payment 
                    FROM billing_history 
                    WHERE tenant_id = %s
                """, (tenant_id,))
                result = cursor.fetchone()
                
                return {
                    "tenant_id": tenant_id,
                    "last_sync": result[0] if result and result[0] else None,
                    "status": "online"
                }
    except Exception as e:
        logger.error(f"Sync status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
