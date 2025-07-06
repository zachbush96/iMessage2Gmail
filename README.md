# iMessage ⇄ Gmail Bridge

A lightweight Python daemon that forwards incoming iMessages/SMS on macOS to a Gmail inbox and lets you reply via email. Replies are sent back through Messages, creating a seamless two-way SMS workflow during your on‑call windows.

---

## 🔎 Overview

* **Forwarding:** Watches your Messages database for new inbound texts and forwards them to your Gmail account with a **unique token** (`MSGID:<rowid>`).
* **Reply-by-Email:** Polls Gmail for replies to those tokens and sends the email body back as an iMessage/SMS.
* **On‑Call Scheduling:** Only runs during configured time windows (e.g. Wed/Thu nights and Sunday days).
* **Persistence & Autostart:** Remembers last processed message ID in `~/.imessage_gmail_state.json` and launches at login via a LaunchAgent plist.
* **Test Harness:** Built‑in unit tests (`--test` flag) to validate message detection, email forwarding, and reply loops.

---

## ⚙️ Tech Stack

| Component         | Details                                                                         |
| ----------------- | ------------------------------------------------------------------------------- |
| Language          | Python 3.9+                                                                     |
| macOS APIs        | SQLite (read-only) on `~/Library/Messages/chat.db`, AppleScript via `osascript` |
| Email Delivery    | Gmail SMTP (TLS)                                                                |
| Email Reception   | Gmail IMAP                                                                      |
| Scheduling        | Custom Python logic + LaunchAgent                                               |
| Testing Framework | Python `unittest`                                                               |
| Logging           | Python `logging` module                                                         |

---

## 🛠️ Installation

1. **Clone or copy** the script into a folder, e.g.:

   ```bash
   mkdir -p ~/imessage_bridge && cd ~/imessage_bridge
   cp /path/to/imessage_email_forwarder.py .
   ```

2. **Install prerequisites** (none external—uses stdlib).
   Ensure you have Python 3.9+ on your PATH:

   ```bash
   python3 --version
   ```

3. **Enable macOS permissions:**

   * **Full Disk Access:** System Settings → Privacy & Security → Full Disk Access → add Terminal (or your Python launcher).
   * **Automation:** System Settings → Privacy & Security → Automation → allow Terminal → Messages.

4. **Gmail App Password:**
   Generate an App Password (Mail on Mac) at [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) and paste it into `GMAIL_PASS` inside the script.

---

## 📝 Configuration

* **Credentials & Servers:**
  Modify the top of the script:

  ```python
  GMAIL_USER   = "zachbush96@gmail.com"
  GMAIL_PASS   = "<APP_PASSWORD>"
  SMTP_SERVER  = "smtp.gmail.com"; SMTP_PORT = 587
  IMAP_SERVER  = "imap.gmail.com"; IMAP_PORT = 993
  ```

* **Scheduling Windows:**
  Adjust `SCHEDULE` tuples (`weekday, start, end`) in 24‑hour format.

* **Polling Interval:**
  `POLL_SECONDS` controls how often the script checks Gmail for replies.

---

## 🚀 Usage

### Run as a daemon

```bash
python3 imessage_email_forwarder.py
```

### One‑off run for testing

```bash
python3 imessage_email_forwarder.py --test
```

* **Interactive logs** show forwarded subjects, polling activity, and any errors.

---

## 📦 LaunchAgent Setup

1. Create `~/Library/LaunchAgents/com.zach.imessagebridge.plist` with:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
    <dict>
     <key>Label</key><string>com.zach.imessagebridge</string>
     <key>ProgramArguments</key>
       <array>
         <string>/usr/bin/python3</string>
         <string>/Users/zach/imessage_bridge/imessage_email_forwarder.py</string>
       </array>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>/tmp/imsgbridge.out</string>
     <key>StandardErrorPath</key><string>/tmp/imsgbridge.err</string>
    </dict>
   </plist>
   ```
2. Load it:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.zach.imessagebridge.plist
   ```

---

## 🔍 Testing & Troubleshooting

* **Run unit tests:**

  ```bash
  python3 imessage_email_forwarder.py --test
  ```

  Checks new-message detection, email send, reply loop.

* **Enable debug logging:**
  At the top of the script, set:

  ```python
  logging.basicConfig(level=logging.DEBUG)
  ```

* **Common issues:**

  * **DB locked:** Ensure `mode=ro&nolock=1` URI is used.
  * **Permission denied:** Verify Full Disk Access & Automation settings.
  * **SMTP auth fail:** Regenerate the App Password.

---

## 🔒 Security Considerations

* **App Passwords** are safer than full OAuth for unattended scripts.
* **Read-only DB access** prevents accidental modifications to your Messages history.
* **State file** stores only the last row ID—no message content is persisted locally beyond transient JSON.

---

## 🚧 Future Enhancements

* **Attachment support**: Base64-encode or link attachments.
* **Group chat filtering**: Tag group threads differently.
* **OAuth2 flow**: Replace app passwords with a proper token refresh cycle.
* **CI integration**: Add GitHub Actions for automated linting and testing.

---

> Built with ❤️ for Zach's on‑call SMS needs.
