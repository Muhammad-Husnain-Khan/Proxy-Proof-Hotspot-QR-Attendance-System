from datetime import datetime
from extensions import db

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(20), unique=True, nullable=True)
    mac_address_history = db.Column(db.Text, nullable=True)
    
    # Relationships
    records = db.relationship('AttendanceRecord', backref='student', lazy=True)

    def __repr__(self):
        return f'<Student {self.email}>'

class Session(db.Model):
    __tablename__ = 'sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    token_duration = db.Column(db.Integer, default=30)
    excel_path = db.Column(db.String(255), nullable=True)
    
    # Relationships
    records = db.relationship('AttendanceRecord', backref='session', lazy=True)

    def __repr__(self):
        return f'<Session {self.course_name} at {self.start_time}>'

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    device_mac = db.Column(db.String(17), nullable=False) # Logs the MAC used at the time

    def __repr__(self):
        return f'<AttendanceRecord Student:{self.student_id} Session:{self.session_id}>'
