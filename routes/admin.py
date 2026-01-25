"""
Admin routes for managing users and roles.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
import secrets

from models.user import User
from models.role import Role
from models.server import Server
from utils.authz import require_permission
from utils import settings as settings_utils

bp = Blueprint('admin', __name__)


@bp.route('/admin/users')
@login_required
@require_permission('manage_users')
def users():
    servers = Server.get_all()
    users = []
    for user in User.get_all():
        roles = User.get_roles(user.id)
        role_ids = {role['id'] for role in roles}
        server_ids = User.get_server_access_ids(user.id)
        users.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_superadmin': user.is_superadmin,
            'must_change_password': user.must_change_password,
            'all_servers_access': user.all_servers_access,
            'roles': roles,
            'role_ids': role_ids,
            'server_ids': server_ids,
        })

    all_roles = Role.get_all()
    return render_template(
        'admin_users.html',
        users=users,
        roles=all_roles,
        servers=servers,
        current_user=current_user,
        active_page='users',
        nav_mode='admin'
    )


@bp.route('/admin/users/create', methods=['POST'])
@login_required
@require_permission('manage_users')
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    role_ids = request.form.getlist('roles')
    all_servers_access = request.form.get('all_servers_access') == 'on'
    server_ids = request.form.getlist('servers')

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
        must_change_password=True,
        all_servers_access=all_servers_access
    )
    if not user:
        flash('Username or email already exists', 'error')
        return redirect(url_for('admin.users'))

    if role_ids:
        User.set_roles(user.id, [int(role_id) for role_id in role_ids])
    if not all_servers_access and server_ids:
        User.set_server_access(user.id, [int(server_id) for server_id in server_ids])

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
    if target_user and target_user.id == current_user.id:
        flash('You cannot change your own roles or server access.', 'error')
        return redirect(url_for('admin.users'))

    role_ids = request.form.getlist('roles')
    all_servers_access = request.form.get('all_servers_access') == 'on'
    server_ids = request.form.getlist('servers')

    User.set_roles(user_id, [int(role_id) for role_id in role_ids])
    User.set_all_servers_access(user_id, all_servers_access)
    if all_servers_access:
        User.set_server_access(user_id, [])
    else:
        User.set_server_access(user_id, [int(server_id) for server_id in server_ids])
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
        current_user=current_user,
        active_page='roles',
        nav_mode='admin'
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


@bp.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@require_permission('manage_settings')
def settings():
    db_path = current_app.config['DATABASE']
    existing_key = settings_utils.get_setting(db_path, 'curseforge_api_key', '')
    existing_game_id = settings_utils.get_setting(db_path, 'curseforge_game_id', '70216')
    existing_update_interval = settings_utils.get_setting(db_path, 'mod_auto_update_interval_hours', '6')
    hytale_auto_enabled = settings_utils.get_setting(db_path, 'hytale_auto_update_enabled', '0')
    hytale_update_interval = settings_utils.get_setting(db_path, 'hytale_auto_update_interval_hours', '24')

    if request.method == 'POST':
        api_key = request.form.get('curseforge_api_key', '').strip()
        game_id = request.form.get('curseforge_game_id', '').strip()
        update_interval = request.form.get('mod_auto_update_interval_hours', '').strip()
        clear_key = request.form.get('clear_curseforge_api_key') == 'on'
        hytale_auto_enabled = request.form.get('hytale_auto_update_enabled') == 'on'
        hytale_update_interval = request.form.get('hytale_auto_update_interval_hours', '').strip()

        if clear_key:
            settings_utils.set_setting(db_path, 'curseforge_api_key', '')
        elif api_key:
            settings_utils.set_setting(db_path, 'curseforge_api_key', api_key)

        if game_id:
            settings_utils.set_setting(db_path, 'curseforge_game_id', game_id)

        if update_interval:
            try:
                interval_value = int(update_interval)
                if interval_value < 1:
                    interval_value = 1
                elif interval_value > 24:
                    interval_value = 24
                settings_utils.set_setting(db_path, 'mod_auto_update_interval_hours', str(interval_value))
            except ValueError:
                flash('Update interval must be a number between 1 and 24 hours.', 'error')
                return redirect(url_for('admin.settings'))

        if 'hytale_auto_update_enabled' in request.form or 'hytale_auto_update_interval_hours' in request.form:
            if hytale_update_interval:
                try:
                    interval_value = int(hytale_update_interval)
                    if interval_value < 12:
                        interval_value = 12
                    elif interval_value > 720:
                        interval_value = 720
                    settings_utils.set_setting(db_path, 'hytale_auto_update_interval_hours', str(interval_value))
                except ValueError:
                    flash('Hytale update interval must be a number between 12 and 720 hours.', 'error')
                    return redirect(url_for('admin.settings'))

            settings_utils.set_setting(db_path, 'hytale_auto_update_enabled', '1' if hytale_auto_enabled else '0')

        flash('Settings updated.', 'success')
        return redirect(url_for('admin.settings'))

    api_key_hint = ''
    if existing_key:
        api_key_hint = f"****{existing_key[-4:]}"

    return render_template(
        'admin_settings.html',
        current_user=current_user,
        active_page='settings',
        curseforge_key_hint=api_key_hint,
        curseforge_game_id=existing_game_id,
        mod_auto_update_interval_hours=existing_update_interval,
        hytale_auto_update_enabled=(str(hytale_auto_enabled).lower() in ('1', 'true', 'yes', 'on')),
        hytale_auto_update_interval_hours=hytale_update_interval,
        nav_mode='admin',
    )
