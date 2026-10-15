# Migration Guide - Multi-Account Architecture

## Overview

This document describes the multi-account architecture changes introduced in MediaFlow. This is a **new feature** that adds support for managing multiple Xiaohongshu accounts per user.

## What's New

### Architecture Changes

The system now uses a proxy pattern with an external multi-account manager service:

```
MediaFlow FastAPI (8000) → xiaohongshu-mcp Manager (8080) → Browser Containers
```

- **FastAPI**: Handles user authentication, stores user-to-account mappings only
- **Multi-Account Manager**: Manages actual account credentials, cookies, and browser sessions
- **Browser Containers**: Isolated browser instances for each account (managed by manager)

### New Features

1. **Multi-Account Support**: Users can now bind and manage multiple Xiaohongshu accounts
2. **QR Code Login**: Get QR codes for account login via the manager
3. **Login Status Check**: Verify if an account is logged in
4. **Default Account**: Set a default account for publishing
5. **Graceful Degradation**: System works partially when manager is unavailable

## Breaking Changes

**None**. This is a backward-compatible feature addition.

## Migration Steps

### For New Users

1. Ensure the multi-account manager service is running on port 8080
2. Start MediaFlow normally
3. Navigate to account management to add accounts

### For Existing Users

No action required. Existing functionality remains unchanged.

## Environment Configuration

### Required Service

The multi-account manager must be running:

```bash
# Start the xiaohongshu-mcp service on port 8080
# See xiaohongshu-mcp documentation for setup instructions
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MULTI_ACCOUNT_MANAGER_URL` | `http://localhost:8080` | Multi-account manager URL |

## API Changes

### New Endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/xiaohongshu/accounts/` | Create new account binding |
| GET | `/api/xiaohongshu/accounts/` | List all accounts for user |
| GET | `/api/xiaohongshu/accounts/{id}` | Get account details |
| DELETE | `/api/xiaohongshu/accounts/{id}` | Delete account binding |
| PUT | `/api/xiaohongshu/accounts/{id}/default` | Set as default account |
| POST | `/api/xiaohongshu/accounts/{id}/qrcode` | Get login QR code |
| GET | `/api/xiaohongshu/accounts/{id}/status` | Check login status |

### Backward Compatibility

The legacy endpoint still works:

| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/xiaohongshu/account` | Returns default account (if available) |

## Troubleshooting

### Manager Service Not Running

If the multi-account manager is not running:
- Account listing returns partial data (bindings only)
- Account creation fails
- QR code and login status features are unavailable

**Solution**: Start the xiaohongshu-mcp service on port 8080

### Timeout Issues

If endpoints timeout when manager is down:
- This is expected behavior
- The health check has a 5-second timeout

**Solution**: Ensure manager is running or adjust timeout if needed

## Database Changes

New table added: `xiaohongshu_account_bindings`

```sql
CREATE TABLE xiaohongshu_account_bindings (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    mcp_account_id VARCHAR(8) NOT NULL UNIQUE,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

The legacy `xiaohongshu_accounts` table remains unchanged for backward compatibility.