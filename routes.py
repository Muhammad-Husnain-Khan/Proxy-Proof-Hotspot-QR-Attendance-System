from flask import Blueprint, render_template, request, send_file, jsonify, redirect, url_for, flash
from extensions import db
from models import Student, Session, AttendanceRecord
from utils import get_local_ip, generate_qr_code, get_client_mac, TokenManager, process_attendance_excel
from datetime import datetime
import os, json, pandas as pd

main = Blueprint('main', __name__)

# ── Global in-memory state ───────────────────────────────────────────────────
app_state = {'current_excel': None}

# ── Helper: resolve current excel path ──────────────────────────────────────
def _get_excel_path():
    """Returns the best available Excel path from session or app_state."""
    active = Session.query.filter_by(is_active=True).first()
    if active and active.excel_path and os.path.exists(active.excel_path):
        return active.excel_path
    path = app_state.get('current_excel')
    if path and os.path.exists(path):
        return path
    last = Session.query.order_by(Session.id.desc()).first()
    if last and last.excel_path and os.path.exists(last.excel_path):
        return last.excel_path
    return None

def _clean_headers(df):
    """Standardizes headers to DD/MM/YYYY and prefixes with ' to prevent Excel auto-formatting."""
    new_cols = []
    for c in df.columns:
        # 1. Convert datetime objects
        if hasattr(c, 'strftime'):
            s = c.strftime('%d/%m/%Y')
        else:
            s = str(c).strip().replace(' 00:00:00', '').lstrip("'")
            # 2. Convert YYYY-MM-DD strings
            if '-' in s and len(s) == 10:
                try: s = datetime.strptime(s, '%Y-%m-%d').strftime('%d/%m/%Y')
                except: pass
        
        # 3. Add to new headers
        new_cols.append(s)
    df.columns = new_cols
    return df

@main.route('/')
def teacher_dashboard():
    """Teacher dashboard. Shows the management interface."""
    active_session = Session.query.filter_by(is_active=True).first()

    # Auto-restore excel path from last known session if app_state lost it (e.g. server restart)
    if not app_state.get('current_excel'):
        last_session = Session.query.order_by(Session.id.desc()).first()
        if last_session and last_session.excel_path and os.path.exists(last_session.excel_path):
            app_state['current_excel'] = last_session.excel_path

    # Default values
    records = []
    excel_to_use = active_session.excel_path if active_session else app_state.get('current_excel')
    excel_loaded = bool(excel_to_use and os.path.exists(excel_to_use))

    if active_session:
        records = AttendanceRecord.query.filter_by(
            session_id=active_session.id
        ).order_by(AttendanceRecord.timestamp.desc()).all()

    return render_template(
        'teacher.html',
        active_session=active_session,
        records=records,
        excel_loaded=excel_loaded,
        local_ip=get_local_ip()
    )

@main.route('/api/attendance')
def get_attendance():
    """API endpoint to get the list of students who marked attendance in the active session."""
    active_session = Session.query.filter_by(is_active=True).first()
    if not active_session:
        return jsonify([])
    
    records = AttendanceRecord.query.filter_by(session_id=active_session.id).all()
    attendance_list = [{
        "id": r.id,
        "name": r.student.name,
        "roll_number": r.student.roll_number,
        "email": r.student.email,
        "time": r.timestamp.strftime("%H:%M:%S"),
        "mac": r.device_mac
    } for r in records]
    
    return jsonify(attendance_list)

@main.route('/api/edit_cell', methods=['POST'])
def edit_cell():
    """Edits a single attendance cell in the Excel file and saves it."""
    data = request.get_json()
    roll = str(data.get('roll', '')).strip().upper()
    date_col = str(data.get('date_col', '')).strip()
    new_value = str(data.get('value', '-')).strip().upper()

    if new_value not in ('P', 'A', '-'):
        return jsonify({'error': 'Invalid value. Must be P, A, or -'}), 400

    path = _get_excel_path()
    if not path:
        return jsonify({'error': 'No Excel file loaded'}), 404

    try:
        df = pd.read_excel(path, dtype=str, engine='openpyxl').fillna('-')
        df = _clean_headers(df)
        roll_col = next((c for c in df.columns if 'ROLL' in str(c).upper() or ('REG' in str(c).upper() and 'NO' in str(c).upper())), None)

        if not roll_col:
            return jsonify({'error': 'Roll column not found'}), 400
        if date_col not in df.columns:
            return jsonify({'error': f'Date column "{date_col}" not found'}), 400

        # Find row and update value
        mask = df[roll_col].str.strip().str.upper() == roll
        if not mask.any():
            return jsonify({'error': f'Student {roll} not found'}), 404

        df.loc[mask, date_col] = new_value
        df.to_excel(path, index=False, engine='openpyxl')

        return jsonify({'status': 'ok', 'roll': roll, 'date_col': date_col, 'value': new_value})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/start_session', methods=['POST'])
def start_session():
    """Endpoint to initialize a new session with selectable modes."""
    # This route is now combined with upload_excel for simplicity
    return redirect(url_for('main.teacher_dashboard'))

@main.route('/api/refresh_qr', methods=['POST'])
def refresh_qr():
    """Manually refreshes the QR token and resets the timer."""
    TokenManager.generate_token()
    return jsonify({"status": "success", "seconds_remaining": TokenManager.get_seconds_remaining()})

COURSES_FILE = os.path.join('temp_uploads', 'courses.json')

def load_courses():
    os.makedirs('temp_uploads', exist_ok=True)
    if os.path.exists(COURSES_FILE):
        with open(COURSES_FILE) as f:
            return json.load(f)
    return []

def save_courses(courses):
    os.makedirs('temp_uploads', exist_ok=True)
    with open(COURSES_FILE, 'w') as f:
        json.dump(courses, f)

@main.route('/api/courses', methods=['GET'])
def get_courses():
    return jsonify(load_courses())

@main.route('/api/courses', methods=['POST'])
def add_course():
    name = (request.get_json() or {}).get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    courses = load_courses()
    if name not in courses:
        courses.append(name)
        save_courses(courses)
    return jsonify({'status': 'ok', 'courses': courses})

@main.route('/api/courses/delete', methods=['POST'])
def delete_course():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    print(f"DEBUG: Request to delete course: '{name}'")
    courses = load_courses()
    print(f"DEBUG: Current courses: {courses}")
    if name in courses:
        courses.remove(name)
        save_courses(courses)
        print(f"DEBUG: Course removed successfully. New list: {courses}")
    else:
        print(f"DEBUG: Course '{name}' NOT found in list.")
    return jsonify({'status': 'ok', 'courses': courses})

@main.route('/api/export_attendance.xlsx')
def export_excel_direct():
    """Export the current Excel file directly without ending the session."""
    # Try active session first
    active_session = Session.query.filter_by(is_active=True).first()
    path = active_session.excel_path if active_session else None

    # Fall back to the most recently ended session
    if not path:
        last_session = Session.query.order_by(Session.id.desc()).first()
        path = last_session.excel_path if last_session else None

    # Fall back to app_state
    if not path:
        path = app_state.get('current_excel')

    if not path or not os.path.exists(path):
        return jsonify({'error': 'No sheet loaded'}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name='attendance.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@main.route('/api/set_duration', methods=['POST'])
def set_duration():
    """Changes the QR refresh duration without regenerating the current token."""
    duration = int((request.get_json() or {}).get('duration', 30))
    if duration < 5:
        return jsonify({'error': 'Minimum 5 seconds'}), 400
    TokenManager._current_duration = duration
    
    # Update active session duration if exists
    active_session = Session.query.filter_by(is_active=True).first()
    if active_session:
        active_session.token_duration = duration
        db.session.commit()
        
    return jsonify({'status': 'ok', 'duration': duration})


@main.route('/api/mark_manually', methods=['POST'])
def mark_manually():
    """Manually marks a student as present in the active session."""
    active_session = Session.query.filter_by(is_active=True).first()
    if not active_session:
        return jsonify({'error': 'No active session'}), 404
    
    data = request.get_json()
    roll = str(data.get('roll', '')).strip().upper()
    
    student = Student.query.filter_by(roll_number=roll).first()
    if not student:
        return jsonify({'error': f'Student {roll} not found in whitelist'}), 404
    
    # Check if already marked
    existing = AttendanceRecord.query.filter_by(session_id=active_session.id, student_id=student.id).first()
    if existing:
        return jsonify({'status': 'ok', 'message': 'Already marked'})
    
    new_record = AttendanceRecord(
        session_id=active_session.id,
        student_id=student.id,
        device_mac='MANUAL'
    )
    db.session.add(new_record)
    db.session.commit()
    
    return jsonify({'status': 'ok'})


@main.route('/api/delete_sheet', methods=['POST'])
def delete_sheet():
    """Clears the currently loaded Excel file."""
    path = app_state.get('current_excel')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass
    app_state['current_excel'] = None
    
    # Also clear from active session if any
    active_session = Session.query.filter_by(is_active=True).first()
    if active_session:
        active_session.excel_path = None
        db.session.commit()
        
    return jsonify({'status': 'ok'})

@main.route('/api/remove_attendance/<int:record_id>', methods=['POST'])
def remove_attendance(record_id):
    """Removes a specific attendance record."""
    record = AttendanceRecord.query.get_or_404(record_id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({"status": "success"})

@main.route('/upload_excel', methods=['POST'])
def upload_excel():
    """Handles Excel upload, parses it, and redirects to preview stage."""
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('main.teacher_dashboard'))

    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.xlsx'):
        flash('Please upload a valid .xlsx file.', 'error')
        return redirect(url_for('main.teacher_dashboard'))

    temp_dir = 'temp_uploads'
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    file_path = os.path.join(temp_dir, 'current_sheet.xlsx')
    file.save(file_path)
    app_state['current_excel'] = file_path
    
    # If there's an active session, update its excel_path too
    active_session = Session.query.filter_by(is_active=True).first()
    if active_session:
        active_session.excel_path = file_path
        db.session.commit()

    return redirect(url_for('main.teacher_dashboard'))

@main.route('/api/preview_excel')
def preview_excel():
    """Returns the parsed Excel data for the preview grid."""
    active_session = Session.query.filter_by(is_active=True).first()
    path = active_session.excel_path if active_session else app_state.get('current_excel')
    if not path or not os.path.exists(path):
        return jsonify({'error': 'No file uploaded'}), 404

    try:
        df = pd.read_excel(path, dtype=str, engine='openpyxl')
        df = _clean_headers(df)
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        df = df.fillna('-')

        # Detect key columns
        roll_col = next((c for c in df.columns if 'ROLL' in str(c).upper() or ('REG' in str(c).upper() and 'NO' in str(c).upper())), None)
        name_col = next((c for c in df.columns if 'NAME' in str(c).upper()), None)
        s_no_col = next((c for c in df.columns if any(x in str(c).upper() for x in ['S#', 'S.NO', 'SR.', 'SERIAL', 'SL.'])), None)

        if not roll_col:
            return jsonify({'error': 'Could not find Roll Number column in the Excel file.'}), 400

        # All other columns (non roll, non name, non s_no) are treated as date attendance columns
        # Exclude summary columns like A (Absents) and L (Leaves)
        fixed_cols = [c for c in [roll_col, name_col, s_no_col] if c]
        date_cols = [c for c in df.columns if c not in fixed_cols and str(c).strip().upper() not in ['A', 'L', 'ABSENT', 'LEAVE']]

        students = []
        for _, row in df.iterrows():
            entry = {
                'roll': str(row[roll_col]).strip() if roll_col else '',
                'name': str(row[name_col]).strip() if name_col else '',
                's_no': str(row[s_no_col]).strip() if s_no_col else '',
                'attendance': {col: str(row[col]).strip() for col in date_cols}
            }
            students.append(entry)

        return jsonify({
            'roll_col': roll_col,
            'name_col': name_col,
            's_no_col': s_no_col,
            'date_cols': date_cols,
            'students': students
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/start_with_excel', methods=['POST'])
def start_with_excel():
    """Starts a session using the already-uploaded Excel file."""
    course_name = request.form.get('course_name')
    mode = request.form.get('mode', 'strict')
    custom_time = request.form.get('custom_time')

    if not course_name:
        return jsonify({'status': 'error', 'message': 'Course Name is required'}), 400

    # Find the excel path from any available source (no re-upload needed)
    path = app_state.get('current_excel')

    if not path or not os.path.exists(path):
        # Try the most recent session (active or ended)
        last_session = Session.query.order_by(Session.id.desc()).first()
        if last_session and last_session.excel_path and os.path.exists(last_session.excel_path):
            path = last_session.excel_path
            app_state['current_excel'] = path  # Restore into memory

    if not path or not os.path.exists(path):
        return jsonify({'status': 'error', 'message': 'No student sheet found. Please upload an Excel sheet first.'}), 400

    try:
        df = pd.read_excel(path, dtype=str, engine='openpyxl')
        df = _clean_headers(df)
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        df = df.fillna('-')
        roll_col = next((c for c in df.columns if 'ROLL' in str(c).upper() or ('REG' in str(c).upper() and 'NO' in str(c).upper())), None)
        name_col = next((c for c in df.columns if 'NAME' in str(c).upper()), None)

        if not roll_col:
            return jsonify({'status': 'error', 'message': 'Excel must have a Roll Number column'}), 400

        # Populate / update student whitelist from sheet
        for _, row in df.iterrows():
            roll = str(row[roll_col]).strip().upper()
            name = str(row[name_col]).strip() if name_col else f'Student {roll}'
            if not roll or roll == '-':
                continue
            student = Student.query.filter_by(roll_number=roll).first()
            if not student:
                student = Student(roll_number=roll, name=name, email=f'{roll}@student.edu')
                db.session.add(student)
            else:
                student.name = name
        db.session.commit()

        # Determine token duration
        try:
            # Prefer custom_time if provided, else mode if it's a number, else default 30
            if custom_time and str(custom_time).isdigit():
                duration = int(custom_time)
            elif mode and str(mode).isdigit():
                duration = int(mode)
            else:
                duration = 30
            
            if duration < 5: duration = 30 # Sanity check
        except:
            duration = 30

        # Start session
        Session.query.update({Session.is_active: False})
        new_session = Session(course_name=course_name, token_duration=duration, excel_path=path)
        db.session.add(new_session)
        db.session.commit()

        TokenManager.generate_token(duration=duration)
        return jsonify({'status': 'ok', 'message': f'Session started! {len(df)} students whitelisted.', 'course': course_name})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500



@main.route('/end_session', methods=['POST'])
def end_session():
    """Deactivates the current session and returns JSON summary."""
    active_session = Session.query.filter_by(is_active=True).first()
    if not active_session:
        return jsonify({'status': 'no_session'}), 404

    # Calculate Summary
    present_count = AttendanceRecord.query.filter_by(session_id=active_session.id).count()
    
    # Get total students from the Excel
    total_students = 0
    excel_path = active_session.excel_path
    if excel_path and os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path, engine='openpyxl')
            df = _clean_headers(df)
            df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
            total_students = len(df)
            
            # Process and generate the final Excel
            records = AttendanceRecord.query.filter_by(session_id=active_session.id).all()
            present_students = [r.student for r in records]
            process_attendance_excel(excel_path, present_students)
        except Exception as e:
            print(f"Error processing excel at end of session: {e}")
            # Continue so the session at least ends

    absent_count = total_students - present_count
    
    # Deactivate
    active_session.is_active = False
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'course_name': active_session.course_name,
        'present': present_count,
        'absent': absent_count,
        'total': total_students,
        'download_url': url_for('main.export_excel_direct')
    })

@main.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join('temp_uploads', filename), as_attachment=True)

@main.route('/api/qrcode')
def serve_qrcode():
    """Serves the dynamic QR code image."""
    active_session = Session.query.filter_by(is_active=True).first()
    if not active_session:
        return "No active session", 404
        
    # Refresh token ONLY if expired or doesn't exist
    if not TokenManager.is_token_fresh():
        # Sync duration with active session
        TokenManager.generate_token(duration=active_session.token_duration)
        token = TokenManager._current_token
    else:
        token = TokenManager._current_token
        
    local_ip = get_local_ip()
    payload = f"http://{local_ip}:5000/mark?token={token}"
    
    qr_img = generate_qr_code(payload)
    return send_file(qr_img, mimetype='image/png', download_name='qrcode.png')

@main.route('/api/token_status')
def token_status():
    """Returns the remaining time for the current token, synced with active session."""
    active_session = Session.query.filter_by(is_active=True).first()
    total = active_session.token_duration if active_session else TokenManager._current_duration
    
    # Optional: Proactively sync TokenManager if it differs
    if active_session and TokenManager._current_duration != active_session.token_duration:
        TokenManager._current_duration = active_session.token_duration

    return jsonify({
        "seconds_remaining": TokenManager.get_seconds_remaining(),
        "total_duration": total
    })

@main.route('/mark', methods=['GET', 'POST'])
def mark_attendance():
    """Student portal for marking attendance."""
    token = request.args.get('token') or request.form.get('token')
    
    if request.method == 'GET':
        if not TokenManager.is_token_valid(token):
            return render_template('error.html', message="Token Expired or Invalid. Please scan again."), 403
        return render_template('student.html', token=token)

    # POST Logic
    roll_number = request.form.get('roll_number', '').strip().upper()
    
    # Backend Validation for XXL-XXXX
    import re
    if not re.match(r'^[0-9]{2}L-[0-9]{4}$', roll_number):
        return render_template('error.html', message="Invalid Roll Number format. Expected XXL-XXXX (e.g. 24L-3007)"), 400

    # 1. Validate Token
    if not TokenManager.is_token_valid(token):
        return render_template('error.html', message="Session expired while submitting. Please scan the latest QR code."), 403
        
    # 2. Get active session
    active_session = Session.query.filter_by(is_active=True).first()
    if not active_session:
        return render_template('error.html', message="No active session found."), 404
        
    # 3. Anti-Proxy: Resolve MAC address
    client_ip = request.remote_addr
    client_mac = get_client_mac(client_ip)
    
    if not client_mac:
        client_mac = "UNKNOWN"

    # 4. Check if MAC has already been used in this session for a DIFFERENT student
    existing_record_with_mac = AttendanceRecord.query.filter_by(
        session_id=active_session.id, 
        device_mac=client_mac
    ).first()
    
    # 5. Check student identity by roll number (Whitelist check)
    student = Student.query.filter_by(roll_number=roll_number).first()
    if not student:
        return render_template('error.html', message="Attendance Denied! Your roll number was not found in the teacher's uploaded sheet."), 403

    if existing_record_with_mac and existing_record_with_mac.student_id != student.id:
        return render_template('error.html', message="Proxy Attempt Detected! This device has already marked attendance for another student."), 403

    # Check if this student already marked attendance
    already_marked = AttendanceRecord.query.filter_by(
        session_id=active_session.id,
        student_id=student.id
    ).first()
    
    if already_marked:
        return render_template('success.html', message=f"You marked your attendance: {student.roll_number} - P. Please disconnect from hotspot.")

    # 6. Record Attendance
    new_record = AttendanceRecord(
        session_id=active_session.id,
        student_id=student.id,
        device_mac=client_mac
    )
    db.session.add(new_record)
    db.session.commit()
    
    return render_template('success.html', message="Attendance marked successfully! Please disconnect from hotspot.")
