"""
Authorization helpers for role-based permissions.
"""

from functools import wraps
from flask import request, jsonify, render_template
from flask_login import current_user
from models.user import User


def has_permission(permission_key):
    if not current_user.is_authenticated:
        return False
    if current_user.is_superadmin:
        return True
    return User.has_permission(current_user.id, permission_key)


def require_permission(permission_key):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if has_permission(permission_key):
                return func(*args, **kwargs)
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Forbidden'}), 403
            return render_template('403.html'), 403
        return wrapped
    return decorator
