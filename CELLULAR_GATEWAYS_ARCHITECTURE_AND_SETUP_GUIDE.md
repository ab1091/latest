# AllZone AI CRM — Cellular & SMS Gateways Master Guide
### Android Gateway (TextBee) & Apple iPhone Gateway (BlueBubbles + Apple Shortcuts)
**Version:** 2.0  
**Last Updated:** November 2026  
**Status:** Production Ready  

---

## 1. Executive Summary & Architecture Overview

AllZone AI CRM operates a **carrier-grade, zero-per-message-fee cellular SMS infrastructure**. Rather than relying exclusively on third-party aggregators (e.g., Twilio 10DLC with strict registration delays, expensive carrier surcharges, and aggressive spam filtering), AllZone AI CRM integrates directly with **physical cellular hardware**:

1. **Android Cellular Gateway (TextBee Protocol)**: Uses connected physical Android hardware (Xiaomi POCO 2410FPCC5G) running physical SIM cards (Dual Jazz SIMs) to send and receive carrier SMS messages instantaneously (under 1 second) across Pakistan and local GSM networks.
2. **Apple iPhone / Mac Gateway (BlueBubbles Protocol)**: Uses a networked Apple macOS host (`azt@AZTs-MacBook-Air.local`) communicating through an encrypted Cloudflare Zero Trust tunnel to dispatch Apple iMessages and carrier SMS (Green Bubbles) via iOS Text Message Forwarding.
3. **iPhone Direct Queue (Apple Shortcuts Automation)**: A 100% native, app-less iOS automation pipeline that allows an iPhone to autonomously poll a central PostgreSQL database queue (`iphone_sms_queue`) and send SMS messages directly through its active SIM card.
4. **Smart Regional Routing Engine**: Automatically directs outbound communications based on E.164 country codes:
   - Pakistani numbers (`+92...`, `03...`) ➔ Dispatched via **Android POCO Jazz SIMs**.
   - US and international numbers (`+1...`) ➔ Dispatched via **BlueBubbles Mac / iPhone Gateway**.
   - Seamless failover: If the primary hardware gateway encounters an error or timeout, the engine automatically routes through the backup gateway.

```
                          ┌─────────────────────────────────────┐
                          │         AllZone AI CRM Core         │
                          │   (FastAPI Backend :8002 & :8003)   │
                          └──────────────────┬──────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
          [ Pakistan / Local GSM (+92) ]             [ US / International (+1) ]
                       │                                           │
                       ▼                                           ▼
           ┌──────────────────────┐                    ┌──────────────────────┐
           │ TextBee API Gateway  │                    │  Cloudflare Tunnel   │
           │ (api.textbee.dev/v1) │                    │ (trycloudflare.com)  │
           └───────────┬──────────┘                    └───────────┬──────────┘
                       │                                           │
                       ▼ (FCM Push)                                ▼ (HTTP / JSON)
           ┌──────────────────────┐                    ┌──────────────────────┐
           │  POCO Android Phone  │                    │   MacBook Air Host   │
           │  (UP1A / Android 14) │                    │ (BlueBubbles Server) │
           └───────────┬──────────┘                    └───────────┬──────────┘
                       │                                           │
          ┌────────────┴────────────┐                  ┌───────────┴───────────┐
          ▼                         ▼                  ▼                       ▼
    [ SIM Slot 1 ]            [ SIM Slot 2 ]      [ iMessage ]        [ Carrier SMS ]
   Jazz (Azhar H.)          Jazz (Abdul Razaq)   (Apple Devices)    (SMS Relay to iPhone)
   0328 1044778              Signal 4/4 Bars        (667ms)             (Green Bubbles)
```

---

## 2. Android Gateway (TextBee / POCO)

### 2.1 Hardware & Telemetry Specifications
- **Device Brand / Model**: Xiaomi POCO (`model: 2410FPCC5G`, `name: POCO123`)
- **Operating System**: Android 14 (API Level 34, Build `UP1A.231005.007`)
- **TextBee Gateway App**: Version 2.9.0 (Code 20)
- **Cellular SIM Cards**:
  - **Slot 1 (Subscription 2)**: Carrier **Jazz** (`mcc: 410`, `mnc: 01`), Display Name `Azhar Hussain`, Signal Level `4/4` (Full Bars).
  - **Slot 2 (Subscription 1)**: Carrier **Jazz** (`mcc: 410`, `mnc: 01`), Display Name `Abdul Razaq` (`0328 1044778`), Signal Level `4/4` (Full Bars).
- **Power & Battery**: Monitored via API telemetry (Current: 61%, health normal).

### 2.2 How Outbound Sending Works
1. **Trigger**: An automated campaign step, AI follow-up, or CRM agent initiates a text message.
2. **Payload Dispatch**: Backend calls `core.textbee.send_message(phone, message)`:
   ```python
   # ai-service/core/textbee.py
   async with httpx.AsyncClient(timeout=15.0) as client:
       res = await client.post(
           f"{TEXTBEE_BASE_URL}/gateway/devices/{TEXTBEE_DEVICE_ID}/sendSMS",
           headers={"x-api-key": TEXTBEE_API_KEY, "Content-Type": "application/json"},
           json={"recipients": [clean_phone], "message": message}
       )
   ```
3. **Cloud-to-Device Push**: The TextBee coordinator transmits the payload to the POCO device via high-priority Firebase Cloud Messaging (FCM).
4. **Physical GSM Transmission**: The TextBee Android background service invokes `android.telephony.SmsManager.getDefault().sendTextMessage(...)` on the active SIM card.
5. **Confirmation**: Device confirms transmission back to TextBee cloud, returning a unique batch ID (e.g., `batch: 6aecc57457bff70ef2e69749`) in under **800ms**.

### 2.3 How Inbound Receiving Works
1. A contact replies to the Jazz cellular number from their phone.
2. The Android OS receives the GSM PDU broadcast and passes it to TextBee's `SmsReceiver`.
3. TextBee forwards the payload via HTTP POST to the CRM webhook:
   `POST /api/sms/inbound`
4. The CRM looks up the lead by matching the phone number, appends the incoming message to the conversation transcript, and triggers the AI responder (`Riley` / `Henry` / `Leo`).

### 2.4 Android Phone Setup & Maintenance
To ensure 24/7 uptime without Android OS putting the app to sleep:
1. **Disable Battery Optimization**:
   - Go to *Settings ➔ Apps ➔ Manage Apps ➔ TextBee*.
   - Set *Battery Saver* to **No Restrictions**.
2. **Autostart Permission**:
   - Enable **Autostart** toggle so the service recovers if the phone restarts.
3. **Lock App in Memory**:
   - Open Recent Apps, long-press the TextBee app tile, and tap the **Lock** icon.
4. **Keep WiFi / Mobile Data Connected**: Keep the phone connected to office WiFi and keep the phone plugged into a charger.

---

## 3. Apple iPhone Gateway: BlueBubbles Protocol

### 3.1 Overview
The BlueBubbles pipeline bridges the CRM with Apple's Messages ecosystem. It enables:
- Sending and receiving **iMessages** to any Apple user worldwide.
- Sending and receiving **Carrier SMS (Green Bubbles)** to any non-Apple or Android device using an iPhone's cellular SIM card via **Text Message Forwarding**.

### 3.2 Host Environment
- **Host Computer**: `azt@AZTs-MacBook-Air.local` (macOS 26.5.2)
- **BlueBubbles Server**: Version 1.9.12
- **Secure Tunnel**: Cloudflare Zero Trust Tunnel (`https://villages-roberts-apt-mountains.trycloudflare.com`)
- **Apple ID**: `alibaig1091@gmail.com`
- **Send Method**: **`apple-script`** (Executes headless AppleScripts inside macOS `Messages.app` without requiring SIP to be disabled).

### 3.3 BlueBubbles Outbound Message Flow
```
CRM Backend  ──(POST /api/v1/message/text)──>  Cloudflare Tunnel  ──>  BlueBubbles Server (Mac)
                                                                           │
                                                                 (AppleScript Execution)
                                                                           │
                                                                           ▼
                                                                      Messages.app
                                                                      /          \
                                                          (Apple User)            (Android User)
                                                                │                       │
                                                                ▼                       ▼
                                                            iMessage               Carrier SMS
                                                            (APNs)              (Relayed to iPhone)
                                                            [Blue]                    [Green]
```

### 3.4 Crucial Requirement: Carrier SMS (Green Bubbles) Forwarding
To send SMS to non-Apple phones (Android, landlines, or non-iMessage numbers like `+14082175465`):
1. **Register Cellular Number on iPhone**:
   - On the physical iPhone, open **Settings ➔ Messages ➔ Send & Receive**.
   - Ensure the physical cellular phone number is checked under:
     - *"You can receive iMessages to and reply from"*
     - *"Start new conversations from"*
   *(If only an email address is listed, macOS Messages cannot send standard carrier SMS).*
2. **Enable Text Message Forwarding**:
   - On the iPhone, navigate to **Settings ➔ Messages ➔ Text Message Forwarding**.
   - Find your Mac (`AZTs-MacBook-Air`) and toggle the switch **ON**.
   - If prompted, enter the six-digit code displayed on the Mac screen.
3. Once linked, any text sent via BlueBubbles to a non-Apple phone automatically relays through the iPhone's physical SIM card seamlessly.

---

## 4. Apple iPhone Gateway: Apple Shortcuts Queue Method

### 4.1 Overview
The Apple Shortcuts Queue is an autonomous, 100% native method for sending carrier SMS from an iPhone **without installing any third-party apps or jailbreaking**.

The AllZone CRM maintains an atomic message queue in PostgreSQL (`iphone_sms_queue`). The iPhone runs an Apple Shortcut that continuously polls the queue, sends the text via native iOS Messages, and reports back delivery confirmation.

### 4.2 Database Schema
```sql
CREATE TABLE IF NOT EXISTS iphone_sms_queue (
    id VARCHAR(64) PRIMARY KEY,
    phone VARCHAR(32) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'sent', 'failed'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sent_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_iphone_queue_status ON iphone_sms_queue(status, created_at);
```

### 4.3 API Endpoints for Apple Shortcuts

| Endpoint | Method | Response Format | Purpose |
|---|---|---|---|
| `/api/sms/iphone/next-sms` | `GET` | Plain Text (2 lines) | Returns Line 1: `phone`, Line 2: `message`. Atomically locks & claims task. |
| `/api/sms/iphone/pop` | `GET` | JSON | Pops next pending task with `task_id`, `phone`, `message`. |
| `/api/sms/iphone/number` | `GET` | Plain Text | Returns destination phone number only for 1-click shortcuts. |
| `/api/sms/iphone/text` | `GET` | Plain Text | Returns message body only. |
| `/api/sms/iphone/report` | `POST` | JSON (`{"task_id": "...", "status": "sent"}`) | Updates database when iPhone finishes dispatching. |
| `/api/sms/iphone/inbound` | `POST` | JSON (`{"sender": "...", "message": "..."}`) | Ingests incoming carrier SMS from iPhone into CRM. |
| `/api/sms/iphone/status` | `GET` | JSON | Returns count of pending/sent items and recent activity. |

### 4.4 Step-by-Step Apple Shortcut Setup on iPhone

#### Shortcut A: Outbound Dispatch Automation
1. Open the **Shortcuts** app on your iPhone.
2. Tap **+** to create a new Shortcut named `AllZone SMS Dispatcher`.
3. Add the following action sequence:
   ```
   1. Get contents of URL:
      URL: http://3.14.152.78:8002/api/sms/iphone/next-sms
      Method: GET

   2. If [Contents of URL] has any value:
      a. Split [Contents of URL] by [New Lines]
      b. Get Item 1 from [Split Text]  --> Store as Variable `Phone`
      c. Get Item 2 from [Split Text]  --> Store as Variable `Message`

      d. Send Message [Message] to [Phone]:
         (Turn OFF "Show When Run" for 100% headless background sending)

      e. Wait 5 seconds
   3. End If
   ```
4. Set an iOS Automation under **Automation ➔ Create Personal Automation**:
   - Trigger: *Time of Day* (e.g., every hour) or *When Charger is Connected*.
   - Toggle **Run Immediately** (Turn OFF *Ask Before Running*).

#### Shortcut B: Inbound SMS Capture Automation
1. In the Shortcuts app, tap **Automation ➔ + ➔ Create Personal Automation**.
2. Select **Message**:
   - Sender: *Leave blank (Any sender)*
   - Message Contains: *Leave blank*
3. Action:
   ```
   1. Get contents of URL:
      URL: http://3.14.152.78:8002/api/sms/iphone/inbound
      Method: POST
      Request Body: JSON
      Keys:
        - "sender": [Shortcut Input - Sender]
        - "message": [Shortcut Input - Message Body]
   ```
4. Toggle **Run Immediately** (no prompt required).

---

## 5. Smart Routing Engine & Automatic Failover

### 5.1 Smart Route Logic
The direct dispatch handler (`POST /api/sms/direct-send`) automatically selects the optimal hardware route based on the recipient's phone number format:

```python
# ai-service/api/sms/router.py
if provider == "auto":
    # Pakistani mobile numbers (starts with +92, 92, or 03)
    if phone.startswith("+92") or phone.startswith("03") or phone.startswith("92"):
        provider = "textbee"      # Routes to POCO Dual Jazz SIM
    else:
        provider = "bluebubbles"  # Routes to MacBook Air / iPhone SIM (+17373283423)
```

### 5.2 Automatic Failover
If `ENABLE_GATEWAY_FALLBACK=true`:
- If BlueBubbles encounters a Cloudflare tunnel interruption or Mac sleep timeout, the backend logs a warning and automatically falls back to TextBee.
- If TextBee encounters a network timeout, the backend logs a warning and routes via BlueBubbles.
- Every dispatch attempt records the hardware provider used, transmission latency, and batch/GUID identifier in the database conversation log.

---

## 6. Frontend Settings & Diagnostics Guide

Staff and administrators can configure and monitor all cellular gateways directly inside the web application:
**URL:** `http://3.14.152.78:3001/crm-settings` ➔ Tab **📱 Cellular & SMS Gateways**

### Available Dashboard Features:
1. **Gateway Strategy Selector**: Toggle between *Smart Regional Auto-Routing*, *BlueBubbles Primary*, or *Android Primary*, with automatic fallback toggle.
2. **Android Live Card**:
   - Live telemetry: Device name (`POCO123`), Android version, battery percentage (`61%`), SIM 1 and SIM 2 status (`Jazz 4/4 bars`).
   - One-click `Test Android Connection` button.
   - Editable TextBee API Key and Device ID fields with instant saving.
3. **BlueBubbles Live Card**:
   - Live telemetry: Host computer (`azt@AZTs-MacBook-Air.local`), macOS version, server version (`1.9.12`), connected Apple ID.
   - One-click `Test BlueBubbles Connection` button (pings host in under 700ms).
   - Editable Cloudflare Tunnel URL, password (with show/hide toggle), and send method (`apple-script` vs `private-api`).
4. **iPhone Direct Queue Inspector**:
   - Real-time badge counter of pending and sent messages.
   - Live table of queued tasks and timestamps.
   - Manual enqueue input to push test tasks to the iPhone.
5. **Live SMS Test Dispatcher**:
   - Send live test texts to any phone number (`+923324545818`, `+17373283423`, etc.) with instant delivery confirmation and provider identification.

---

## 7. Complete API Reference

### 7.1 Direct SMS Dispatch
```http
POST /api/sms/direct-send HTTP/1.1
Content-Type: application/json

{
  "phone": "+923324545818",
  "message": "Hello from AllZone AI CRM!",
  "provider": "auto"
}
```
**Response (200 OK):**
```json
{
  "ok": true,
  "provider": "textbee (POCO Jazz SIM 0328 1044778)",
  "result": {
    "success": true,
    "batch": "6aecc57457bff70ef2e69749"
  }
}
```

### 7.2 Gateway Settings
```http
GET /api/sms/gateway-settings HTTP/1.1
```
**Response (200 OK):**
```json
{
  "provider": "bluebubbles",
  "enable_fallback": true,
  "bb_server_url": "https://villages-roberts-apt-mountains.trycloudflare.com",
  "bb_password": "••••••••",
  "bb_send_method": "apple-script",
  "textbee_api_key": "txb_••••••••",
  "textbee_device_id": "6ae9fa7a59a24e053fc15a8a",
  "textbee_base_url": "https://api.textbee.dev/api/v1",
  "textbee_phone": "0328 1044778 (Jazz SIM)",
  "bluebubbles_account": "alibaig1091@gmail.com"
}
```

### 7.3 Gateway Health Ping
```http
POST /api/sms/gateway-test HTTP/1.1
Content-Type: application/json

{
  "gateway": "bluebubbles"
}
```
**Response (200 OK):**
```json
{
  "ok": true,
  "data": {
    "computer_id": "azt@AZTs-MacBook-Air.local",
    "os_version": "26.5.2",
    "server_version": "1.9.12",
    "detected_imessage": "alibaig1091@gmail.com",
    "proxy_service": "cloudflare"
  }
}
```

---

## 8. Summary Checklist for Operations

- [x] **Android POCO Gateway**: Running, plugged into charger, battery at 61%, dual Jazz SIMs active with 4/4 signal.
- [x] **BlueBubbles Mac Gateway**: Host `azt@AZTs-MacBook-Air.local` connected via Cloudflare tunnel, AppleScript send method enabled, dispatches verified in 667ms.
- [x] **Smart Regional Routing**: Live on port 8002 & 3001. Automatically routes Pakistani numbers to Android and US numbers to Mac/iPhone.
- [x] **Web UI Dashboard**: Full visual controls and live diagnostic telemetry accessible under CRM Settings ➔ Cellular & SMS Gateways.
- [x] **Git Repository**: All documentation and code synchronized with `main` branch.
