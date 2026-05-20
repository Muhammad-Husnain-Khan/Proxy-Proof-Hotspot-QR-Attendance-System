# 🚀 Proxy-Proof Hotspot-QR Attendance System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-lightgrey?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A state-of-the-art, high-security local attendance system designed specifically to **completely eliminate proxy attendance**. It achieves this by combining **local physical proximity** (Wi-Fi Hotspot restriction) with **temporal security** (dynamic, 30-second auto-expiring QR codes) and **hardware identity locking** (device MAC address logging).

---

## 🔒 The Core Security Architecture (Anti-Proxy Heuristics)

Standard QR code systems are prone to cheating: one student scans the code, screenshots it, and sends it to their friends at home. This system stops that completely using a **three-layered security heuristic**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ANTI-PROXY TRIFECTA                            │
├───────────────────┬───────────────────────────────┬─────────────────────┤
│ 📶 Proximity      │ ⏱️ Temporal                    │ 📱 Hardware         │
│ Local Wi-Fi       │ Dynamic expiring tokens       │ MAC Address locking │
│ (No Hotspot =     │ (QR regenerates every 30s;    │ (1 device =         │
│  No Webpage)      │  screenshots expire instantly)│  1 attendance mark) │
└───────────────────┴───────────────────────────────┴─────────────────────┘
```

1. **Local Network Proximity (Physical constraint)**
   The Flask server is hosted locally on the teacher's laptop and binds to `0.0.0.0`. Students *must* physically connect their devices to the teacher's Windows Mobile Hotspot network (typically using the default gateway `192.168.137.1`) to access the submission portal. They cannot access it from home or school Wi-Fi.
2. **Temporal Token Security (Anti-Sharing)**
   The QR code embeds a cryptographically secure token that expires strictly every **30 seconds** (or a custom duration set by the teacher). If a student screenshots the QR code and shares it, the token will already be invalid by the time a remote user scans it.
3. **Hardware Device Binding (Anti-Double Marking)**
   When a student submits their attendance, the backend uses ARP table resolution via the `getmac` library to capture the device's unique **MAC address** based on their local IP. If a student tries to submit attendance for a friend using the same phone, the system detects that the MAC address has already been logged for another student in this session and blocks it.

---

## 🌟 Key Features

* **Dynamic QR Codes:** Automatically refreshes the QR code and synced countdown timer using smooth frontend AJAX polling (prevents screen flashing).
* **Excel Upload & Live Roster Preview:** Teachers can upload their existing university course Excel sheet (`.xlsx`) to automatically whitelist students.
* **Smart Roster Parser:** Automatically detects Roll Numbers, Student Names, and existing columns, and cleans up dates and cell formatting to prevent Excel corruptions.
* **Manual Roster Modifications:** Directly edit attendance cells (`P` / `A` / `-`) on the dashboard's interactive preview grid or manually mark a student as present in real-time.
* **Live Attendance Counters:** Displays real-time updates as students check-in.
* **One-Click Sheet Export:** Compiles attendance directly back into the uploaded Excel format with the current date's attendance correctly marked (`P` or `A`) and triggers a clean browser download.

---

## 🛠️ Tech Stack

* **Backend:** Python 3.10+, Flask
* **ORM & Database:** SQLAlchemy with SQLite (easily swappable to PostgreSQL, MySQL, or MS SQL Server via database abstraction)
* **Spreadsheet Processing:** Pandas & OpenPyXL
* **QR Engine:** QRCode [PIL] (Generates standard high-contrast, fast-parsing QR PNG streams directly into memory)
* **Networking:** Getmac (low-level ARP table querying)
* **Frontend:** Vanilla HTML5, CSS3 (Modern dark-themed Glassmorphism aesthetic), Vanilla JavaScript

---

## 📁 Directory Structure

```text
My QR-hotspot hybrid system/
├── app.py                  # Application entry point & factory
├── config.py               # Settings (SQLite configuration, expiration timers)
├── extensions.py           # Database initializations (SQLAlchemy instance)
├── models.py               # DB Models (Student, Session, AttendanceRecord)
├── routes.py               # REST API endpoints, Excel engines, and student portal
├── utils.py                # Network utility, MAC grabber, QR generator, TokenManager
├── static/
│   ├── css/
│   │   └── style.css       # Custom Glassmorphic/Indigo styled dashboard layout
│   └── js/
│       └── timer.js         # Synced 30-second token tracking script
├── templates/
│   ├── teacher.html        # Teacher interactive workspace & projector screen
│   ├── student.html        # Student landing/email input page
│   ├── success.html        # Verified check-in confirmation page
│   └── error.html          # Dynamic portal error page (Anti-proxy, timeout, mismatch)
├── temp_uploads/           # Local store for the currently uploaded sheet
└── requirements.txt        # Backend dependencies
```

---

## 🚀 Setting Up the System

### Phase 1: Local Network Preparation (Host Machine)
1. **Enable Mobile Hotspot:**
   On your Windows laptop, open your settings, search for **Mobile Hotspot**, and turn it on.
   * *Note: Windows Mobile Hotspot default IP gateway is standardly `192.168.137.1`. The application will automatically detect and bind to this interface.*
2. **Connect Students:**
   Instruct all attending students to join this Mobile Hotspot network on their phones or tablets.

### Phase 2: Installing and Launching the App
1. **Clone the repository and enter the directory:**
   ```bash
   git clone <your-repo-url>
   cd "My QR-hotspot hybrid system"
   ```

2. **Create a virtual environment & activate it:**
   * **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   * **macOS/Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the Server:**
   ```bash
   python app.py
   ```
   *The server will run on `http://0.0.0.0:5000` to allow all devices connected to your hotspot to access it.*

---

## 📖 Teacher & Student Workflows

### 🧑‍🏫 Teacher Workflow
1. Run the system on your laptop, then open `http://localhost:5000` or `http://192.168.137.1:5000` in your web browser.
2. Under **Course Selection**, select or add the target course.
3. Upload your student whitelist Excel sheet (`.xlsx`) containing at least a `Roll Number` column (formats like `24L-3007` or standard enrollment numbers are supported).
4. Click **Start Session**.
5. Project your laptop screen. A dynamic QR code will appear with a visual countdown timer refreshing every 30 seconds.
6. As students scan, see their details and hardware ID logs populating the live roster feed. 
7. If someone lacks a working camera, search their name in the live grid and check them in manually.
8. Click **End Session** to close the portal. The application will instantly save the updated record back to your Excel file and trigger an auto-download of your ready-to-submit class roster.

### 🧑‍🎓 Student Workflow
1. Connect your smartphone to the teacher's local Wi-Fi Hotspot.
2. Open your camera app or a QR code scanner and scan the moving QR code projected on the whiteboard.
3. Tap the link to land on the secure check-in portal (`http://192.168.137.1:5000/mark?token=...`).
4. Type in your registered university **Roll Number** (e.g. `24L-3007`) and submit.
5. Once marked present, a "Success" screen will prompt you to disconnect from the hotspot to free up network bandwidth.

---

## ⚡ Troubleshooting
* **Phone displays "No Internet Connection":**
  This is normal since the hotspot is only acting as a local offline bridge to host the Flask app. If the phone prompts to switch to cellular data, select **"Stay connected to Wi-Fi"** or **"Keep Wi-Fi connection"**, otherwise the portal will not load.
* **Cannot load page on phone:**
  Make sure your phone is actually connected to the Hotspot and has not dropped off, and confirm that the teacher's firewall is not blocking incoming requests on local port `5000`.

---

*Developed with ❤️ as a secure, fast, and administrative solution for classrooms.*
