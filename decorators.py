from functools import wraps
from flask import session, flash, redirect, url_for

def login_required(f):
    """Decorator para rotas que requerem login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator para rotas que requerem privilégios de admin"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not session.get('admin', False):
            flash('Acesso negado. Esta funcionalidade requer privilégios de administrador.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function