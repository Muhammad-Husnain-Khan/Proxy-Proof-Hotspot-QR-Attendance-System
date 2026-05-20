import os
import secrets

class Config:
    # Database configuration
    # Defaulting to SQLite for local development
    # Connection string can be updated for MySQL/MSSQL in production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'attendance.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Secret key for session management and token security
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Token expiration time (as per SRS: 30 seconds)
    TOKEN_EXPIRATION_SECONDS = 30
