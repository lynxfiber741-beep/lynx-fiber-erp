# Offline Sync Setup Guide

## Overview

The Lynx Fiber ERP now supports full offline sync functionality. Staff can work offline and sync data when internet is available.

## What's Been Implemented

### 1. Frontend (lynx app.py)
- ✅ Offline detection JavaScript
- ✅ Offline queue system (localStorage)
- ✅ Auto-sync when online
- ✅ Offline status indicator (yellow banner)
- ✅ Manual sync button in sidebar
- ✅ PWA manifest and service worker

### 2. Backend (sync_api.py)
- ✅ FastAPI backend for sync operations
- ✅ Payment sync endpoint
- ✅ Customer sync endpoint
- ✅ Batch sync endpoint
- ✅ Sync status endpoint

## Installation Steps

### Step 1: Install Dependencies

```bash
pip install -r requirements_sync.txt
```

Or install individually:
```bash
pip install fastapi uvicorn psycopg2-binary
```

### Step 2: Configure Database URL

The sync API uses the same database as the Streamlit app. Make sure your `.streamlit/secrets.toml` has:
```toml
DB_URL = "postgresql://user:password@localhost/database_name"
```

Set the same DB_URL as environment variable for the sync API:
```bash
export DB_URL="postgresql://user:password@localhost/database_name"
```

Or add to your system environment variables.

### Step 3: Start Sync API Backend

```bash
python sync_api.py
```

Or using uvicorn directly:
```bash
uvicorn sync_api:app --host 0.0.0.0 --port 8000 --reload
```

The API will run on `http://localhost:8000`

### Step 4: Start Streamlit App

```bash
streamlit run "lynx app.py"
```

### Step 5: Test Offline Sync

1. Open the app in browser
2. Go offline (disconnect internet)
3. You should see yellow banner: "⚠️ OFFLINE MODE"
4. Make changes (they will be queued in localStorage)
5. Go online (reconnect internet)
6. Yellow banner should disappear
7. Data should auto-sync to database
8. Or click "🔄 Sync Now" button in sidebar

## How It Works

### Offline Mode
1. App detects no internet connection
2. Yellow banner appears at top
3. All operations are queued in localStorage
4. User can view cached data
5. Changes are stored locally

### Online Mode
1. App detects internet connection
2. Yellow banner disappears
3. Auto-sync triggers
4. Queued operations sent to sync API
5. Sync API processes operations
6. Database updated
7. Queue cleared on success

### Manual Sync
1. Click "🔄 Sync Now" button in sidebar
2. Triggers sync function
3. Sends queued operations to API
4. Shows success/error message

## API Endpoints

### POST /api/sync/payment
Sync offline payment to database

**Request:**
```json
{
  "tenant_id": "lynx",
  "username": "customer1",
  "amount": 1000,
  "payment_method": "CASH",
  "notes": "Offline sync",
  "recorded_by": "staff"
}
```

### POST /api/sync/customer
Sync offline customer creation/update

**Request:**
```json
{
  "tenant_id": "lynx",
  "username": "customer1",
  "customername": "John Doe",
  "phone": "03001234567",
  "cnic": "1234567890123",
  "address": "123 Street",
  "package": "10Mbps",
  "billamount": 1000,
  "area": "Gulshan",
  "onuserialnumber": "SN12345"
}
```

### POST /api/sync/batch
Sync multiple operations in batch

**Request:**
```json
[
  {
    "type": "payment",
    "data": { ... }
  },
  {
    "type": "customer",
    "data": { ... }
  }
]
```

### GET /api/sync/status
Get sync status for tenant

**Request:**
```
GET /api/sync/status?tenant_id=lynx
```

## Troubleshooting

### Sync Not Working
1. Check if sync_api.py is running on port 8000
2. Check browser console for errors
3. Verify DB_URL is set correctly
4. Check if database is accessible

### Yellow Banner Not Showing
1. Check if offline detection JavaScript is loaded
2. Check browser console for errors
3. Verify internet connection status

### Queue Not Clearing
1. Check sync API logs for errors
2. Verify database connection
3. Check if operations are valid
4. Manually clear queue: `localStorage.setItem('offlineQueue', '[]')`

### API Connection Error
1. Make sure sync_api.py is running
2. Check if port 8000 is accessible
3. Verify CORS settings in sync_api.py
4. Check firewall settings

## Production Deployment

### Using Systemd (Linux)

Create `/etc/systemd/system/lynx-sync.service`:
```ini
[Unit]
Description=Lynx ERP Sync API
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/lynx-fiber-erp
Environment="DB_URL=postgresql://user:password@host/database"
ExecStart=/usr/local/bin/uvicorn sync_api:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable lynx-sync
sudo systemctl start lynx-sync
```

### Using Docker

Create `Dockerfile.sync`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements_sync.txt .
RUN pip install -r requirements_sync.txt
COPY sync_api.py .

EXPOSE 8000
CMD ["uvicorn", "sync_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -f Dockerfile.sync -t lynx-sync .
docker run -p 8000:8000 -e DB_URL="postgresql://..." lynx-sync
```

## Security Considerations

1. **API Authentication**: Add JWT or API key authentication to sync_api.py
2. **HTTPS**: Use HTTPS in production for secure sync
3. **Rate Limiting**: Add rate limiting to prevent abuse
4. **Data Validation**: Validate all incoming data
5. **CORS**: Restrict CORS to your domain only

## Performance Optimization

1. **Batch Operations**: Sync multiple operations at once
2. **Compression**: Compress large payloads
3. **Caching**: Cache frequently accessed data
4. **Connection Pooling**: Already implemented in sync_api.py
5. **Async Operations**: Use async/await for better performance

## Monitoring

### Check Sync API Status
```bash
curl http://localhost:8000/health
```

### View Sync Logs
Check sync_api.py console output or configure logging to file

### Monitor Queue Size
In browser console:
```javascript
console.log(JSON.parse(localStorage.getItem('offlineQueue') || '[]').length);
```

## Limitations

1. **Streamlit Architecture**: Some Streamlit features require internet
2. **Conflict Resolution**: Basic implementation, may need enhancement
3. **Large Data**: Large datasets may cause performance issues
4. **Real-time**: Not real-time, sync happens when online
5. **Database Lock**: May need transaction handling for high concurrency

## Future Enhancements

1. **Conflict Resolution**: Advanced conflict detection and resolution
2. **Delta Sync**: Only sync changed data
3. **Background Sync**: Sync in background without blocking UI
4. **Push Notifications**: Notify when sync completes
5. **Offline Analytics**: Track offline usage patterns
6. **Selective Sync**: Choose what to sync
7. **Sync History**: View sync history and logs
8. **Rollback**: Ability to rollback sync operations

## Support

For issues or questions:
1. Check browser console for errors
2. Check sync_api.py logs
3. Verify database connection
4. Test API endpoints directly
5. Check network connectivity

## Summary

Your Lynx Fiber ERP now has full offline sync capability:
- Staff can work offline
- Changes sync automatically when online
- Manual sync available
- Robust error handling
- Production-ready backend

Just install dependencies, start the sync API, and you're ready to go!
