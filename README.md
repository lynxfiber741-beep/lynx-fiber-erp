# Lynx Fiber ERP System

A comprehensive multi-tenant ISP (Internet Service Provider) management system built with Streamlit and PostgreSQL.

## Features

- **Multi-tenant Architecture**: Support for multiple ISP companies with isolated data
- **Role-based Access Control**: Owner, Admin, and Staff roles with granular permissions
- **Customer Management**: Complete subscriber lifecycle management
- **Billing Operations**: Payment collection, arrears tracking, and receipt generation
- **WhatsApp Integration**: Automated notifications via Green-API
- **Dashboard Analytics**: Real-time metrics and reporting
- **Bulk Import**: Excel/CSV customer data import
- **Activity Logging**: Comprehensive audit trail
- **Theme Engine**: Multiple UI themes (Dark Nebula, Light Corporate, Midnight Crimson, Ocean Wave)
- **Client Portal**: Self-service portal for subscribers

## Security Features

- **Password Hashing**: bcrypt for secure password storage
- **Rate Limiting**: Login attempt protection (5 attempts, 15-minute lockout)
- **Input Validation**: Phone numbers, CNIC, username validation
- **SQL Injection Protection**: Parameterized queries throughout
- **Error Logging**: Comprehensive logging for debugging and monitoring
- **Environment Variables**: Secure configuration via environment variables

## Prerequisites

- Python 3.8 or higher
- PostgreSQL database
- pip package manager

## Installation

### 1. Clone the Repository

```bash
cd "c:\Users\Competent\Desktop\Dont Open\lynx-fiber-erp"
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate  # On Windows
# source .venv/bin/activate  # On Linux/Mac
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Database

Create a PostgreSQL database and update the connection string in `.streamlit/secrets.toml`:

```toml
DB_URL = "postgresql://username:password@hostname:5432/database_name"
```

Example:
```toml
DB_URL = "postgresql://postgres:yourpassword@localhost:5432/lynx_erp"
```

### 5. Set Default Owner Password (Optional)

Set an environment variable for the default owner password:

```bash
# On Windows (PowerShell)
$env:DEFAULT_OWNER_PASSWORD = "your_secure_password"

# On Windows (Command Prompt)
set DEFAULT_OWNER_PASSWORD=your_secure_password

# On Linux/Mac
export DEFAULT_OWNER_PASSWORD="your_secure_password"
```

**Note**: If not set, a secure random password will be generated and displayed in the logs on first run. Change it immediately after first login.

### 6. Run the Application

```bash
streamlit run "lynx app.py"
```

The application will be available at `http://localhost:8501`

## Default Credentials

After first run, the default owner credentials are:

- **Tenant ID**: `lynx`
- **Username**: `owner`
- **Password**: Check the logs for the generated password or use the environment variable set above

**Important**: Change the default password immediately after first login!

## Configuration

### Database Schema

The application automatically creates the following tables on first run:

- `system_tenants` - Tenant configuration and licensing
- `users` - User accounts with roles
- `customers` - Subscriber records
- `areas` - Geographic/service areas
- `packages` - Internet packages with pricing
- `billing_history` - Transaction records
- `activity_logs` - Audit trail

### WhatsApp Integration

To enable WhatsApp notifications:

1. Get Green-API credentials from https://green-api.com/
2. Navigate to **System Access Control** → **Branding & WhatsApp Controls**
3. Enable WhatsApp and enter:
   - Instance ID
   - API Token
4. Customize message templates as needed

### Staff Permissions

Configure staff permissions in **System Access Control**:

- Allow editing customer name
- Allow editing phone number
- Allow editing physical address
- Allow editing ONU hardware serial
- Allow changing monthly package price
- Allow overriding status (Paid/Suspended)

## Usage Guide

### Dashboard

- View area-wise customer overview
- Monitor revenue metrics
- Filter by status (Paid, Unpaid, Free, Suspended)
- Quick pay functionality

### Billing Center

- **Capital Collection Hub**: Process payments and extend subscriptions
- **Status & Reversal Control**: Suspend/activate lines, reverse payments
- **Provision New Client**: Add new subscribers
- **Bulk Import**: Import customers from Excel/CSV
- **Edit Terminal Profile**: Update customer information
- **Remove Subscriber**: Delete customer records

### Ledger History

- View complete transaction history
- Filter paid users by date range
- Export payment reports

### System Access Control (Owner/Admin only)

- **SaaS License Manager**: Manage tenant licenses
- **Access Accounts**: Manage staff users and permissions
- **Package Pricing**: Configure area-specific packages
- **Area Hubs**: Manage service areas
- **Data Backup**: Export database snapshots
- **Activity Logs**: View system audit trail

### Client Portal

- Self-service portal for subscribers
- View bill and account status
- Check expiry dates

## Input Validation

The application validates:

- **Username**: 3-20 alphanumeric characters
- **Phone Number**: Pakistani format (10-12 digits)
- **CNIC**: XXXXX-XXXXXXX-X format
- **Password**: Minimum 6 characters

## Rate Limiting

- Maximum 5 failed login attempts
- 15-minute account lockout
- Automatic unlock after lockout period

## Backup and Restore

### Backup

1. Navigate to **System Access Control** → **Data Backup Vault**
2. Select backup scope (Current Tenant or Full Server)
3. Click "Generate System Backup Snapshot"
4. Download the JSON file

### Restore

Currently, restore functionality must be done manually by importing the JSON data into the database.

## Troubleshooting

### Database Connection Error

```
🔴 Critical Configuration Error: 'DB_URL' is missing from Streamlit Secrets!
```

**Solution**: Ensure `.streamlit/secrets.toml` exists with valid DB_URL.

### License Expired

```
⚠️ 🔐 SOFTWARE LICENSE SUSPENDED OR EXPIRED!
```

**Solution**: Contact system administrator or update license expiry in database.

### Account Locked

```
⚠️ Account locked due to too many failed attempts.
```

**Solution**: Wait 15 minutes for automatic unlock or contact administrator.

## Development

### Code Structure

- `lynx app.py` - Main application file
- `.streamlit/secrets.toml` - Configuration file
- `requirements.txt` - Python dependencies

### Adding New Features

1. Add new functions to appropriate sections
2. Update database schema if needed
3. Add input validation for user inputs
4. Include error logging
5. Test thoroughly before deployment

## Security Best Practices

1. **Change Default Password**: Immediately after first login
2. **Use Strong Passwords**: Minimum 8 characters with mixed case, numbers, and symbols
3. **Regular Backups**: Schedule regular database backups
4. **Monitor Logs**: Check activity logs regularly
5. **Limit Staff Access**: Grant minimum necessary permissions
6. **Keep Dependencies Updated**: Regularly update Python packages
7. **Use HTTPS**: Deploy behind SSL/TLS in production

## Support

For issues or questions:
- Check the troubleshooting section
- Review activity logs for error details
- Contact system administrator

## License

This is a proprietary SaaS solution licensed by Lynx Fiber Internet.

## Version History

- **v1.0** - Initial release with core ERP functionality
- **v1.1** - Added security enhancements (rate limiting, input validation)
- **v1.2** - Fixed deprecated APIs and improved error logging
- **v1.3** - SQL injection protection and environment variable support

---

**Distributed & Licensed by: Lynx Fiber Internet**
