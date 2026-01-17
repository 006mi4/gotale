"""
Admin routes for managing users and roles.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import secrets

from models.user import User
from models.role import Role
from utils.authz import require_permission

bp = Blueprint('admin', __name__)


@bp.route('/admin/users')
@login_required
@require_permission('manage_users')
def users():
    users = []
    for user in User.get_all():
        roles = User.get_roles(user.id)
        role_ids = {role['id'] for role in roles}
        users.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_superadmin': user.is_superadmin,
            'must_change_password': user.must_change_password,
            'roles': roles,
            'role_ids': role_ids,
        })

    all_roles = Role.get_all()
    return render_template('admin_users.html', users=users, roles=all_roles, current_user=current_user)


@bp.route('/admin/users/create', methods=['POST'])
@login_required
@require_permission('manage_users')
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    role_ids = request.form.getlist('roles')

    if not username or len(username) < 3 or len(username) > 20:
        flash('Username must be between 3 and 20 characters', 'error')
        return redirect(url_for('admin.users'))
    if not email or '@' not in email:
        flash('Valid email address required', 'error')
        return redirect(url_for('admin.users'))

    generated_password = secrets.token_urlsafe(10)
    user = User.create_user(
        username,
        email,
        generated_password,
        is_superadmin=False,
        must_change_password=True
    )
    if not user:
        flash('Username or email already exists', 'error')
        return redirect(url_for('admin.users'))

    if role_ids:
        User.set_roles(user.id, [int(role_id) for role_id in role_ids])

    flash(f'User created. Temporary password: {generated_password}', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/admin/users/<int:user_id>/roles', methods=['POST'])
@login_required
@require_permission('manage_users')
def update_user_roles(user_id):
    if current_user.id == user_id:
        flash('You cannot change your own roles.', 'error')
        return redirect(url_for('admin.users'))

    target_user = User.get_by_id(user_id)
    if target_user and target_user.is_superadmin:
        flash('You cannot change roles for a superadmin.', 'error')
        return redirect(url_for('admin.users'))

    role_ids = request.form.getlist('roles')
    User.set_roles(user_id, [int(role_id) for role_id in role_ids])
    flash('User roles updated.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/admin/roles')
@login_required
@require_permission('manage_roles')
def roles():
    roles = Role.get_all()
    permission_catalog = Role.get_permission_catalog()
    role_permission_ids = {
        role.id: Role.get_permission_ids(role.id) for role in roles
    }
    return render_template(
        'admin_roles.html',
        roles=roles,
        permissions=permission_catalog,
        role_permission_ids=role_permission_ids,
        current_user=current_user
    )


@bp.route('/admin/roles/create', methods=['POST'])
@login_required
@require_permission('manage_roles')
def create_role():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    permission_ids = [int(pid) for pid in request.form.getlist('permissions')]

    if not name:
        flash('Role name is required', 'error')
        return redirect(url_for('admin.roles'))

    role_id = Role.create(name, description or None)
    if not role_id:
        flash('Role name already exists', 'error')
        return redirect(url_for('admin.roles'))

    if permission_ids:
        Role.set_permissions(role_id, permission_ids)

    flash('Role created.', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/admin/roles/<int:role_id>/permissions', methods=['POST'])
@login_required
@require_permission('manage_roles')
def update_role_permissions(role_id):
    permission_ids = [int(pid) for pid in request.form.getlist('permissions')]
    Role.set_permissions(role_id, permission_ids)
    flash('Role permissions updated.', 'success')
    return redirect(url_for('admin.roles'))


@bp.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
@login_required
@require_permission('manage_roles')
def delete_role(role_id):
    Role.delete(role_id)
    flash('Role deleted.', 'success')
    return redirect(url_for('admin.roles'))
