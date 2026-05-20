import socket
import qrcode
import io
import secrets
from datetime import datetime, timedelta
from getmac import get_mac_address
from config import Config

def get_local_ip():
    """
    Resolves the host machine's Local Network IP.
    Prioritizes the common Windows Mobile Hotspot gateway (192.168.137.1).
    """
    try:
        # Check all network interfaces to find the one matching the hotspot pattern
        # This is a robust way to find the 'Mobile Hotspot' interface on Windows
        interfaces = socket.getaddrinfo(socket.gethostname(), None)
        ips = [i[4][0] for i in interfaces if i[4][0].startswith('192.168.')]
        
        # Prioritize 192.168.137.1 (Default for Windows Hotspot)
        if '192.168.137.1' in ips:
            return '192.168.137.1'
        
        # Fallback to the first local IP found
        if ips:
            return ips[0]
            
        # Generic fallback
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def generate_qr_code(data):
    """
    Generates a QR code PNG and returns it as a byte stream.
    """
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return img_io

def get_client_mac(client_ip):
    """
    Resolves the MAC address of a client IP on the local network using the ARP table.
    """
    return get_mac_address(ip=client_ip)

import pandas as pd
import io, traceback
from datetime import datetime
from flask import send_file

def process_attendance_excel(file_path, present_students_data):
    """
    Processes an Excel sheet and marks 'P' or 'A' based on attendance.
    present_students_data: List of dicts or objects with 'roll_number' or 'name'.

    Returns a Flask send_file response with the correct .xlsx MIME type,
    so the browser downloads it as a proper Excel file (not binary garbage).
    """
    try:
        # Load the Excel file — explicitly use openpyxl engine
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # Standardize headers to 'DD/MM/YYYY
        new_cols = []
        for c in df.columns:
            if hasattr(c, 'strftime'): s = c.strftime('%d/%m/%Y')
            else:
                s = str(c).strip().replace(' 00:00:00', '').lstrip("'")
                if '-' in s and len(s) == 10:
                    try: s = datetime.strptime(s, '%Y-%m-%d').strftime('%d/%m/%Y')
                    except: pass
            new_cols.append(s)
        df.columns = new_cols
        
        # Current Date Column Header
        date_col = datetime.now().strftime("%d/%m/%Y")
        
        # If the column doesn't exist, create it with 'A' (Absent) as default
        if date_col not in df.columns:
            df[date_col] = 'A'
            
        # Get list of present identifiers (Roll Numbers)
        present_identifiers = [
            str(s.roll_number).strip().upper()
            for s in present_students_data
            if s.roll_number
        ]

        # Find Roll Number column dynamically
        roll_col = next(
            (c for c in df.columns if any(x in str(c).upper() for x in ['ROLL', 'REG', 'ID', 'NO'])),
            None
        )

        if not roll_col:
            print(f"Error: Could not find Roll Number column in Excel. Columns: {df.columns.tolist()}")
            return None

        def mark_p(row):
            val = str(row[roll_col]).strip().upper()
            if val in present_identifiers:
                return 'P'
            # Keep existing value if it's already 'P'
            existing = str(row[date_col]).strip().upper()
            if existing == 'P':
                return 'P'
            return 'A'

        df[date_col] = df.apply(mark_p, axis=1)
        
        # Save back to the SAME file (overwriting) so the persistent download route works
        df.to_excel(file_path, index=False, engine='openpyxl')
        
        # ✅ FIX: Write to an in-memory BytesIO stream with openpyxl engine
        # This avoids filesystem permission issues and guarantees a valid .xlsx binary
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)  # Rewind stream to the beginning before sending

        # ✅ FIX: Return a proper Flask response with the correct MIME type
        # This tells the browser it's an Excel file, not raw binary
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='attendance.xlsx'
        )
        
    except Exception as e:
        print(f"Excel Processing Error: {e}")
        import traceback
        traceback.print_exc()
        return None


class TokenManager:
    """
    Manages dynamic expiring tokens.
    """
    _current_token = None
    _expiration_time = None
    _current_duration = Config.TOKEN_EXPIRATION_SECONDS

    @classmethod
    def generate_token(cls, duration=None):
        if duration:
            cls._current_duration = int(duration)
        cls._current_token = secrets.token_hex(16)
        cls._expiration_time = datetime.utcnow() + timedelta(seconds=cls._current_duration)
        return cls._current_token

    @classmethod
    def is_token_valid(cls, token):
        if not cls._current_token or not cls._expiration_time:
            return False
        
        # Check if token matches and has not expired
        is_match = (token == cls._current_token)
        is_fresh = (datetime.utcnow() < cls._expiration_time)
        
        return is_match and is_fresh

    @classmethod
    def is_token_fresh(cls):
        """Checks if the CURRENT token is still within its validity period."""
        if not cls._current_token or not cls._expiration_time:
            return False
        return datetime.utcnow() < cls._expiration_time

    @classmethod
    def get_seconds_remaining(cls):
        if not cls._expiration_time:
            return 0
        remaining = (cls._expiration_time - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))