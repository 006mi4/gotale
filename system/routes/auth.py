"""
Authentication routes for login, logout, and setup
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
import sqlite3

from models.user import User

bp = Blueprint('auth', __name__)

def is_setup_completed():
    """Check if initial setup is completed"""
    try:
        conn = sqlite3.connect(current_app.config['DATABASE'])
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM settings WHERE key = 'setup_completed'")
        result = cursor.fetchone()
        conn.close()

        return result and result[0] == '1'
    except:
        return False

def mark_setup_completed():
    """Mark setup as completed in database"""
    try:
        conn = sqlite3.connect(current_app.config['DATABASE'])
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value)
            VALUES ('setup_completed', '1')
        """)

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error marking setup completed: {e}")
        return False

@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Initial setup page - create superadmin account"""

    # Redirect if setup already completed
    if is_setup_completed():
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        errors = []

        if not username or len(username) < 3 or len(username) > 20:
            errors.append('Username must be between 3 and 20 characters')

        if not email or '@' not in email:
            errors.append('Valid email address required')

        if not password or len(password) < 8:
            errors.append('Password must be at least 8 characters')

        if password != confirm_password:
            errors.append('Passwords do not match')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('setup.html', username=username, email=email)

        # Create superadmin user
        user = User.create_user(username, email, password, is_superadmin=True)

        if not user:
            flash('Username or email already exists', 'error')
            return render_template('setup.html', username=username, email=email)

        # Mark setup as completed
        mark_setup_completed()

        flash('Setup completed successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('setup.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""

    # Redirect to setup if not completed
    if not is_setup_completed():
        return redirect(url_for('auth.setup'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter username and password', 'error')
            return render_template('login.html', username=username)

        # Verify user
        user = User.get_by_username(username)

        if not user:
            flash('Invalid username or password', 'error')
            return render_template('login.html', username=username)

        # Verify password
        if not User.verify_password(username, password):
            flash('Invalid username or password', 'error')
            return render_template('login.html', username=username)

        # Log user in
        login_user(user)
        flash(f'Welcome back, {user.username}!', 'success')

        # Redirect to next page or dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)

        return redirect(url_for('dashboard.index'))

    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    """Logout current user"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))
