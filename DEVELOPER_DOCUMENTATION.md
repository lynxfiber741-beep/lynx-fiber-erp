# Lynx Fiber ERP - Developer Documentation

## 📋 App Overview

**Lynx Fiber ERP** is a multi-tenant SaaS (Software as a Service) billing and customer management system designed for Internet Service Providers (ISPs). Built with Streamlit, it provides a comprehensive solution for managing customers, billing, payments, and operational tasks.

---

## 🎨 Color Scheme & Theme System

### Default Theme: Dark Nebula
```python
THEMES = {
    "Dark Nebula (Default)": {
        "background": "#0f172a",
        "surface": "#1e293b",
        "border": "#334155",
        "heading": "#f8fafc",
        "text": "#cbd5e1",
        "accent": "#3b82f6",
        "success": "#10b981",
        "warning": "#f59e0b",
        "error": "#ef4444"
    }
}
```

### Theme Components
- **Background**: Dark blue-gray (#0f172a)
- **Surface**: Slightly lighter for cards (#1e293b)
- **Border**: Subtle gray (#334155)
- **Heading**: White/off-white (#f8fafc)
- **Text**: Light gray (#cbd5e1)
- **Accent**: Blue (#3b82f6) - Primary action color
- **Success**: Green (#10b981) - Paid status
- **Warning**: Orange (#f59e0b) - Partial status
- **Error**: Red (#ef4444) - Unpaid/Suspended status

---

## 🏗️ Architecture

### Multi-Tenant SaaS Structure
```
lynx-fiber-erp/
├── lynx app.py              # Main Streamlit application
├── sync_api.py              # Offline sync API (FastAPI)
├── requirements.txt         # Python dependencies
└── .streamlit/
    └── secrets.toml         # Database credentials
```

### Key Components
1. **Frontend**: Streamlit web application
2. **Backend**: PostgreSQL database
3. **Sync API**: FastAPI for offline data synchronization
4. **Authentication**: Bcrypt password hashing
5. **Multi-tenancy**: Tenant-based data isolation

---

## 💾 Database Schema

### Tables

#### 1. `customers`
```sql
- username (TEXT, PK with tenant_id)
- customername (TEXT)
- phone (TEXT)
- cnic (TEXT)
- package (TEXT)
- billamount (INTEGER)
- area (TEXT)
- address (TEXT)
- onuserialnumber (TEXT)
- balanceshift (INTEGER) - Arrears
- status (TEXT) - PAID, UNPAID, PARTIAL, SUSPENDED, FREE
- expirydate (TEXT) - Format: YYYY-MM-DD HH:MM:SS
- tenant_id (TEXT, PK with username)
```

#### 2. `areas`
```sql
- areaname (TEXT, PK with tenant_id)
- tenant_id (TEXT, PK with areaname)
```

#### 3. `packages`
```sql
- packagename (TEXT, PK with areaname, tenant_id)
- areaname (TEXT, PK with packagename, tenant_id)
- packagerate (INTEGER)
- tenant_id (TEXT, PK with packagename, areaname)
```

#### 4. `billing_history`
```sql
- invoiceid (TEXT, PK)
- customerid (TEXT)
- customername (TEXT)
- area (TEXT)
- phone (TEXT)
- datetimestamp (TEXT) - Format: YYYY-MM-DD HH:MM:SS
- currentpackage (TEXT)
- amountpaid (INTEGER)
- remainingarrears (INTEGER)
- transactiontype (TEXT) - BILL_PAYMENT, REVERSAL
- paymentmethod (TEXT) - CASH, EASYPAISA, JAZZCASH, BANK_TRANSFER
- discountgiven (INTEGER)
- tenant_id (TEXT)
```

#### 5. `users`
```sql
- username (TEXT, PK with tenant_id)
- password (TEXT) - Bcrypt hashed
- role (TEXT) - Owner, Admin, Staff
- assignedarea (TEXT) - Area permissions
- tenant_id (TEXT, PK with username)
- password_changed_at (TEXT)
```

#### 6. `system_tenants`
```sql
- tenant_id (TEXT, PK)
- company_name (TEXT)
- support_phone (TEXT)
- owner_username (TEXT)
- license_active (BOOLEAN)
- registration_date (TEXT)
- license_expiry_date (TEXT)
- staff_permissions (TEXT) - JSON
- whatsapp_instance_id (TEXT)
- whatsapp_token (TEXT)
- whatsapp_enabled (BOOLEAN)
- whatsapp_templates (TEXT) - JSON
```

#### 7. `activity_logs`
```sql
- log_id (TEXT, PK)
- tenant_id (TEXT)
- username (TEXT)
- action_type (TEXT)
- description (TEXT)
- timestamp (TEXT)
```

---

## 🛠️ Technology Stack

### Core Technologies
- **Frontend Framework**: Streamlit (Python)
- **Backend Database**: PostgreSQL
- **API Framework**: FastAPI (for sync)
- **Password Hashing**: Bcrypt
- **Data Processing**: Pandas
- **PDF Generation**: ReportLab
- **WhatsApp Integration**: Requests library

### Python Dependencies
```txt
streamlit
psycopg2-binary
pandas
bcrypt
python-dateutil
reportlab
requests
```

---

## ✨ Key Features

### 1. **Multi-Tenant Architecture**
- Complete data isolation per tenant
- Tenant-specific branding and configuration
- Role-based access control (Owner, Admin, Staff)
- Area-based permissions for staff

### 2. **Customer Management**
- Add/Edit/Delete customers
- CSV bulk import with validation
- Phone number validation (Pakistani format)
- Area-based customer filtering
- Customer status management (PAID, UNPAID, PARTIAL, SUSPENDED, FREE)

### 3. **Billing & Payments**
- Quick payment from dashboard
- Operational billing center
- Multiple payment methods (CASH, EASYPAISA, JAZZCASH, BANK_TRANSFER)
- Discount support
- Arrears calculation
- Expiry date management with time component
- Duplicate payment prevention (monthly check)
- PDF receipt generation

### 4. **Revenue Calculation**
- Real-time revenue overview
- Area-wise revenue breakdown
- Paid/Partial/Unpaid user counts
- Outstanding arrears tracking
- Current month payment tracking

### 5. **Operational Features**
- Payment reversal functionality
- Line suspension/activation
- Customer status control
- Missing users check (CSV comparison)
- Backup/restore functionality

### 6. **Client Portal**
- Public-facing customer portal
- Bill viewing by username or phone
- Digital bill/quotation display
- Provider branding

### 7. **WhatsApp Integration**
- Configurable WhatsApp API
- Template-based notifications
- Payment confirmation messages
- Multi-tenant WhatsApp settings

### 8. **Offline Support**
- PWA (Progressive Web App) capabilities
- Sync API for offline data
- Manual sync functionality

### 9. **Theme System**
- Multiple color themes
- Dark mode default
- Customizable accent colors
- Consistent UI styling

---

## 🔐 Security Features

### Authentication
- Bcrypt password hashing
- Session-based authentication
- Password change detection
- Session invalidation on password change
- Login attempt logging

### Authorization
- Role-based access control (RBAC)
- Area-based permissions
- Tenant data isolation
- Staff permission configuration

### Data Protection
- SQL injection prevention (parameterized queries)
- Tenant-based data segregation
- Activity logging for audit trail

---

## 📊 API Endpoints (Sync API)

### FastAPI Endpoints (sync_api.py)
```
POST /sync/payment - Sync payment data
POST /sync/customer - Sync customer data
POST /sync/bulk - Bulk sync operations
GET /sync/status - Check sync status
```

---

## 🎯 Key Business Logic

### Payment Processing
1. Check for duplicate payments (current month)
2. Calculate new expiry date
3. Update customer status (PAID/PARTIAL/UNPAID)
4. Calculate arrears (balanceshift)
5. Record transaction in billing_history
6. Generate PDF receipt
7. Send WhatsApp notification (if enabled)

### Expiry Date Calculation
- Base date: Current date or existing expiry (whichever is later)
- Extension: Add months based on payment
- Default time: 12:00:00 if not specified
- Format: YYYY-MM-DD HH:MM:SS

### Revenue Calculation
- Filter by current month payments only
- Count latest payment per user (not sum of all)
- Only include users marked as PAID
- Area-wise breakdown

---

## 🚀 Deployment Requirements

### Environment Variables
```toml
# .streamlit/secrets.toml
DB_URL = "postgresql://user:password@host:port/database"
```

### Database Setup
- PostgreSQL 12+
- Connection pooling (1-20 connections)
- Autocommit enabled

### Python Environment
- Python 3.8+
- Streamlit latest version
- All dependencies from requirements.txt

### Optional Services
- WhatsApp API (for notifications)
- Sync API server (port 8000)

---

## 📱 Mobile Support

### PWA Installation
- Chrome: Menu → Add to Home Screen
- Safari: Share → Add to Home Screen
- Desktop: Install icon in address bar

### Responsive Design
- Mobile-optimized layout
- Touch-friendly interface
- Dark theme for battery saving

---

## 🎨 UI Components

### Custom CSS Classes
```css
.main-title - Page headers
.system-card - Area overview cards
.live-calc-box - Payment calculation display
.client-card - Customer portal bill display
.saas-footer - Footer branding
```

### Streamlit Components
- Tabs for navigation
- Columns for layout
- Expander for details
- Metrics for KPIs
- Dataframes for tables
- File upload for CSV import

---

## 🔧 Configuration

### Default Settings
- Default expiry time: 12:00:00
- Default package: Standard
- Default bill amount: 1500
- Default area: Default
- Password minimum length: 6 characters

### Tenant Configuration
- Company name
- Support phone
- License expiry
- Staff permissions (JSON)
- WhatsApp settings
- Custom templates

---

## 📝 Development Notes

### Code Structure
- Single-file Streamlit app (lynx app.py)
- Modular functions for database operations
- Cached data functions for performance
- Session state for user authentication
- Theme system for UI consistency

### Performance Optimizations
- Database connection pooling
- Cached data functions (3-second TTL)
- Efficient SQL queries
- Lazy loading of large datasets

### Error Handling
- Comprehensive try/except blocks
- User-friendly error messages
- Logging for debugging
- Graceful fallbacks

---

## 🎓 Developer Quick Start

### 1. Setup Database
```sql
-- Tables are auto-created on first run
-- No manual schema setup required
```

### 2. Configure Secrets
```toml
# .streamlit/secrets.toml
DB_URL = "postgresql://user:password@localhost:5432/lynx_erp"
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Application
```bash
streamlit run "lynx app.py"
```

### 5. Default Credentials
- **Tenant ID**: lynx
- **Username**: owner
- **Password**: (Generated on first run, check logs)

---

## 📞 Support & Contact

### Distributor
- **Name**: [DISTRIBUTOR_NAME] (Configurable)
- **License**: Lynx Fiber Pvt Ltd

### Technical Support
- Check logs for detailed error messages
- Review activity_logs table for audit trail
- Use Streamlit Cloud "Manage app" for cloud deployment logs

---

## 🔄 Recent Updates

### Version History
- **v1.0**: Initial release
- **v1.1**: Added duplicate payment prevention
- **v1.2**: Enhanced CSV import with detailed error reporting
- **v1.3**: Added missing users check feature
- **v1.4**: Improved revenue calculation accuracy
- **v1.5**: Added customer details confirmation before payment
- **v1.6**: Fixed theme-related errors
- **v1.7**: Fixed TO_CHAR function compatibility

---

## 📊 Statistics & Metrics

### Dashboard KPIs
- Total customers per area
- Expected revenue (sum of bill amounts)
- Paid users count and collected amount
- Partial accounts count
- Free accounts count
- Unpaid/Suspended users count
- Outstanding arrears

### Billing Metrics
- Payment method breakdown
- Monthly payment trends
- Arrears tracking
- Discount usage

---

## 🎯 Future Enhancements

### Potential Improvements
- Real-time payment notifications
- Automated billing reminders
- Advanced reporting dashboard
- Mobile app (native)
- API for third-party integrations
- Multi-language support
- Advanced analytics

---

## 📄 License

- **Distributed by**: [DISTRIBUTOR_NAME]
- **Licensed to**: Lynx Fiber Pvt Ltd
- **Type**: Multi-tenant SaaS ERP

---

## 🙏 Acknowledgments

Built with Streamlit, PostgreSQL, and modern Python best practices for ISP billing management.
