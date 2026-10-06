# Automated Sales Invoice Email → SharePoint Filing Service

Production-ready Python automation that continuously monitors a Microsoft 365 mailbox for sales invoice emails, validates recipients and subject patterns, extracts metadata (Client name, O&M code, Invoice period), and automatically archives the invoice PDF into the correct hierarchical SharePoint folder (`Customer Invoicing/Invoices/YYMM/IN-xxx/`).

---

## 1. Project Overview & Mailbox Architecture

> [!IMPORTANT]
> **Mail-Enabled Security Group vs. Processing Mailbox**
> 
> The invoice recipient address (`india.invoicing@cleantechsolar.com`) is a **Mail-Enabled Security Group**, not a user mailbox.
> 
> The application does **not** read the group's mailbox directly via Graph. Instead, emails sent to `india.invoicing@cleantechsolar.com` are delivered to the designated user's mailbox (e.g., Surojit's mailbox).
> 
> The application reads from the configured `PROCESSING_MAILBOX` and checks whether `INVOICE_GROUP_ADDRESS` appears in either the **To** or **CC** recipients before processing.

- **Processing User Mailbox (`PROCESSING_MAILBOX`):** Microsoft 365 mailbox that Graph reads (e.g., `surojit@cleantechsolar.com`).
- **Invoice Group Address (`INVOICE_GROUP_ADDRESS`):** Business mail-enabled security group checked in To/CC (e.g., `india.invoicing@cleantechsolar.com`).
- **Target SharePoint Site:** `https://cleantechenergycorp.sharepoint.com/OM`
- **Target Document Library:** `Customer Invoicing`
- **Root Folder:** `Invoices`
- **Hierarchical Path:** `Customer Invoicing/Invoices/<YYMM>/<IN-xxx>/<Client Name> <Month> <Year>.pdf`
- **Duplication Prevention:** Automatic duplicate detection in SharePoint and SQLite database tracking by Graph `message_id`.
- **Idempotency & Concurrency:** Thread-safe SQLite database with WAL mode and atomic check-or-insert semantics.

---

## 2. Architecture & Flow

```text
Microsoft 365 User Mailbox (PROCESSING_MAILBOX)
       │
       ▼ (Poll every 60s via Microsoft Graph: /users/{PROCESSING_MAILBOX}/messages)
┌────────────────────────────────────────────────────────────────────────┐
│  src/services/email_processor.py                                      │
│                                                                        │
│  1. Check if message_id previously processed in SQLite                │
│  2. Validate To/CC contains INVOICE_GROUP_ADDRESS                     │
│     (india.invoicing@cleantechsolar.com - case-insensitive)           │
│  3. Validate subject contains 'Invoice for the month of'              │
│  4. Extract Client Name, IN-xxx code, Month & Year                     │
│  5. Calculate month folder format YYMM (e.g. 2608) strictly from subject│
│  6. Identify & validate PDF attachment (%PDF- header)                  │
│  7. Generate sanitized filename:                                       │
│     <Client Name> <Month> <Year>.pdf                                  │
│  8. Check if file already exists in SharePoint target folder          │
│  9. Upload invoice PDF to SharePoint                                   │
│ 10. Record processing state & status (SUCCESS / DUPLICATE) in SQLite  │
└────────────────────────────────────────────────────────────────────────┘
       │                                  │
       ▼                                  ▼
SharePoint Online                 SQLite Database
Customer Invoicing/Invoices/     (invoice_automation.db)
└── 2608/                        Stores audit log, message IDs,
    └── IN-091/                  group address, statuses, and file paths.
        └── GRUPO ANTOLIN...pdf
```

### Module Structure
```text
src/
├── main.py                     # Entry point & CLI runner (--dry-run, --once)
├── config.py                   # Pydantic Settings loaded from .env
├── auth/
│   └── graph_auth.py           # MSAL OAuth2 Client Credentials provider
├── graph/
│   ├── graph_client.py         # HTTP client with exponential backoff & pagination
│   ├── outlook_client.py       # User mailbox messages & attachment operations
│   └── sharepoint_client.py    # Site, drive, folder resolution & file upload
├── parsers/
│   └── invoice_subject_parser.py # Regex extraction (Client, O&M, Month, Year, YYMM)
├── services/
│   ├── sharepoint_service.py   # High-level folder tree resolution & duplicate check
│   ├── email_processor.py      # Core business rule pipeline
│   └── invoice_service.py      # Background polling orchestrator & startup diagnostics
├── database/
│   ├── db.py                   # Thread-safe SQLite manager (WAL mode)
│   └── models.py               # ProcessedEmailRecord & ProcessingStatus enum
└── utils/
    ├── filename.py             # SharePoint filename sanitization & PDF validator
    └── logging_config.py       # Logging setup with secret redaction
```

---

## 3. Prerequisites

- Python 3.11 or higher
- Microsoft Entra ID (Azure Active Directory) tenant
- SharePoint Online site (`cleantechenergycorp.sharepoint.com/OM`)
- Microsoft 365 user mailbox receiving the group's emails

---

## 4. Azure Entra ID App Registration Setup

1. Sign in to the [Microsoft Entra admin center](https://entra.microsoft.com/) as an Application Administrator or Global Administrator.
2. Navigate to **Identity** > **Applications** > **App registrations** > **New registration**.
3. Name the application: `Cleantech-Invoice-Automation`.
4. Supported account types: **Accounts in this organizational directory only (Single tenant)**.
5. Click **Register**. Note down the **Application (client) ID** and **Directory (tenant) ID**.
6. Under **Certificates & secrets** > **Client secrets** > **New client secret**:
   - Add a description (e.g., `Production Automation Secret`) and set an expiration policy.
   - Click **Add** and copy the **Value** (`CLIENT_SECRET`).

---

## 5. Required Microsoft Graph Permissions

The service requires the following **Application permissions** (not delegated), with **Admin consent** granted:

| Permission | Type | Reason |
| :--- | :--- | :--- |
| `Mail.Read` | Application | Read incoming emails and attachments from the configured `PROCESSING_MAILBOX`. |
| `Sites.ReadWrite.All` | Application | Dynamically resolve site/drive, check/create folders, and upload invoice PDFs. |

> **Least-Privilege Note:** If your security policy restricts `Mail.Read` across the entire tenant, an Exchange administrator can scope access to only the specific user mailbox using an [Application Access Policy](https://learn.microsoft.com/en-us/graph/auth-limit-mailbox-access) with PowerShell cmdlet `New-ApplicationAccessPolicy`.

Click **Grant admin consent for <Your Organization>** in the Azure portal.

---

## 6. SharePoint Configuration

The service dynamically resolves SharePoint IDs at runtime:
1. **Site Path:** `https://cleantechenergycorp.sharepoint.com/OM` (`SHAREPOINT_HOSTNAME=cleantechenergycorp.sharepoint.com`, `SHAREPOINT_SITE_PATH=/OM`)
2. **Library:** `Customer Invoicing`
3. **Root Folder:** `Invoices`
4. **Month Folder:** `YYMM` (e.g., `2608` for August 2026, calculated directly from the subject)
5. **O&M Folder:** `IN-xxx` (e.g., `IN-091`, extracted from the subject)

No hardcoded drive or folder IDs are required.

---

## 7. Environment Variables

Copy the example file:
```bash
cp .env.example .env
```

Edit `.env` with your values:
```env
# Microsoft Entra ID (Azure AD) Credentials
TENANT_ID=your-azure-tenant-id
CLIENT_ID=your-azure-client-id
CLIENT_SECRET=your-azure-client-secret

# Mailbox and Group Configuration
PROCESSING_MAILBOX=surojit@cleantechsolar.com
INVOICE_GROUP_ADDRESS=india.invoicing@cleantechsolar.com

# SharePoint Target Location
SHAREPOINT_HOSTNAME=cleantechenergycorp.sharepoint.com
SHAREPOINT_SITE_PATH=/OM
SHAREPOINT_LIBRARY_NAME=Customer Invoicing
SHAREPOINT_ROOT_FOLDER=Invoices

# Operational Settings
POLL_INTERVAL_SECONDS=60
LOG_LEVEL=INFO
DRY_RUN=false

# SQLite Database Location
DATABASE_PATH=invoice_automation.db
```

---

## 8. Installation

Create a virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 9. Running Locally

### Continuous Polling Mode:
```bash
python -m src.main
# or:
python src/main.py
```

### Single Execution Run (for Cron or manual verification):
```bash
python -m src.main --once
```

### Startup Diagnostics & Banner:
```text
========================================
Microsoft Graph Connection Test
========================================

Tenant: OK
Authentication: OK

Processing mailbox:
surojit@cleantechsolar.com

Mailbox lookup: OK
Messages endpoint: OK

Invoice group address:
india.invoicing@cleantechsolar.com

SharePoint connection: OK

========================================
System Ready
========================================

==================================================
Cleantech Invoice Automation
==================================================
Processing Mailbox:
surojit@cleantechsolar.com

Invoice Group Address (To/CC Filter):
india.invoicing@cleantechsolar.com

SharePoint:
Customer Invoicing/Invoices

Mode:
PRODUCTION

Polling interval:
60 seconds

Status:
Running...
==================================================
```

---

## 10. Dry-Run Mode

In dry-run mode, the automation validates emails, extracts subject data, checks PDF attachments, and checks duplicate status, but **does not create SharePoint folders or upload files**:

```bash
python -m src.main --dry-run
# or for a single test cycle:
python -m src.main --dry-run --once
```

---

## 11. Production & Cloud Deployment (Without Docker)

### Option A: Local & Background Runner (Easiest)
Run directly on any macOS, Linux VM, or local environment:

1. **Start continuous background service:**
   ```bash
   ./start.sh
   ```
2. **Monitor status & logs:**
   ```bash
   ./status.sh
   tail -f logs/invoice_automation.log
   ```
3. **Stop service:**
   ```bash
   ./stop.sh
   ```

---

### Option B: Local Web Server (Vercel-Compatible)
Test the exact Vercel HTTP API locally on port 8000:
```bash
python api/index.py
```
- **Health check:** `http://localhost:8000/health`
- **Run cycle:** `http://localhost:8000/`
- **Dry-run cycle:** `http://localhost:8000/?dry_run=true`

---

### Option C: Vercel Free Tier Serverless Deployment
This project is fully compatible with **Vercel Free Tier (Hobby)**:

1. **Deploy to Vercel:**
   Push to your GitHub repository and import the repository into [Vercel](https://vercel.com).
2. **Configure Environment Variables in Vercel:**
   Go to **Project Settings** > **Environment Variables** and add:
   - `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`
   - `PROCESSING_MAILBOX`, `INVOICE_GROUP_ADDRESS`
   - `SHAREPOINT_HOSTNAME`, `SHAREPOINT_SITE_PATH`, `SHAREPOINT_LIBRARY_NAME`, `SHAREPOINT_ROOT_FOLDER`
   - `FILTER_START_DATE=2026-10-06`
   - `APP_TIMEZONE=Asia/Kolkata`
3. **Automatic Cron & Endpoints:**
   - [vercel.json](file:///Users/sameermishra/Documents/Invoicing%20Automation/vercel.json) routes incoming requests to [api/index.py](file:///Users/sameermishra/Documents/Invoicing%20Automation/api/index.py).
   - Visiting `https://your-app.vercel.app/` triggers a check cycle and returns JSON results.
   - Vercel Cron is configured to trigger automatic runs, or you can trigger `https://your-app.vercel.app/` via a free webhook scheduler (such as cron-job.org or GitHub Actions).

---

### Option D: Linux Systemd Service (Cloud Server / VM)
For 24/7 background operation on Ubuntu/Debian/RHEL servers:
```bash
sudo bash deploy/install_systemd.sh
```

---

### Option E: Scheduled Cron Job
If you prefer running a single check cycle periodically without background processes:
```bash
*/5 * * * * cd /opt/invoicing-automation && .venv/bin/python -m src.main --once >> logs/cron.log 2>&1
```

---

## 12. Database Schema & Statuses

The SQLite database (`invoice_automation.db`) prevents duplicate processing:

### Schema (`processed_emails` table):
- `id` (INTEGER PRIMARY KEY)
- `message_id` (TEXT UNIQUE)
- `internet_message_id` (TEXT)
- `received_datetime` (TEXT)
- `sender` (TEXT)
- `subject` (TEXT)
- `invoice_group_address` (TEXT)
- `client_name` (TEXT)
- `om_code` (TEXT)
- `invoice_month` (TEXT)
- `invoice_year` (INTEGER)
- `month_folder` (TEXT)
- `attachment_name` (TEXT)
- `saved_filename` (TEXT)
- `target_filename` (TEXT)
- `sharepoint_path` (TEXT)
- `status` (TEXT NOT NULL)
- `error_message` (TEXT)
- `processed_at` (TEXT)
- `created_at` (TEXT)

### Processing Statuses:
- `SUCCESS` / `PROCESSED`: Successfully filed to SharePoint.
- `SKIPPED_RECIPIENT`: `india.invoicing@cleantechsolar.com` was not in To or CC.
- `SKIPPED_SUBJECT`: Missing `Invoice for the month of` in subject.
- `INVALID_PERIOD`: Month name invalid or year is not 4 digits.
- `INVALID_OM_CODE`: Missing valid `IN-\d+` code in subject.
- `NO_PDF`: No `.pdf` attachment found on the email.
- `DUPLICATE`: Identical filename already exists in the target SharePoint folder.
- `SHAREPOINT_ERROR`: Folder creation or file upload failed in Graph API.
- `AUTHENTICATION_ERROR`: Azure AD authentication failed.
- `PROCESSING_ERROR`: Unhandled exception or corrupt attachment.

---

## 13. Testing

Run the full pytest suite (36 unit & integration tests):
```bash
pytest -v
```

Tests cover:
- Graph endpoint uses `PROCESSING_MAILBOX` and never the security group
- Recipient validation for `INVOICE_GROUP_ADDRESS` in To or CC (case-insensitive)
- Configuration validation (missing mailbox / group address error reporting)
- Standard subject parsing & edge cases (Section 30, 31, 38)
- Month conversions (`YYMM`) for all 12 calendar months & cross-year transitions
- O&M code regex precision (`IN-091` vs `IN1821191`)
- Filename generation & SharePoint forbidden character sanitization
- Attachment header detection (`%PDF-`)
- Folder creation & idempotency
- Database concurrency & duplicate suppression
- Dry-run mode non-mutating execution
