from flask import Blueprint, render_template, request, redirect, url_for, flash
from database_web import get_db_connection
from decorators import login_required
from datetime import datetime, timedelta
import psycopg2.extras

bp = Blueprint('financeiro', __name__, url_prefix='/financeiro')

@bp.route('/')
@login_required
def painel():
    """Painel financeiro"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Filtros
        periodo = request.args.get('periodo', '30')
        cliente_id = request.args.get('cliente_id', type=int)
        
        # Calcular data inicial
        if periodo == '7':
            start_date = datetime.now().date() - timedelta(days=7)
        elif periodo == '30':
            start_date = datetime.now().date() - timedelta(days=30)
        elif periodo == '90':
            start_date = datetime.now().date() - timedelta(days=90)
        elif periodo == 'ano':
            start_date = datetime(datetime.now().year, 1, 1).date()
        else:
            start_date = datetime(2020, 1, 1).date()
        
        # Query de ordens
        query = '''
            SELECT os.*, c.nome as cliente_nome, fp.nome as forma_pagamento_nome
            FROM ordens_servico os
            LEFT JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
            WHERE os.data >= %s
        '''
        params = [start_date]
        
        if cliente_id:
            query += ' AND os.cliente_id = %s'
            params.append(cliente_id)
        
        query += ' ORDER BY os.data DESC'
        cursor.execute(query, params)
        ordens = cursor.fetchall()
        
        # Estatísticas
        cursor.execute('''
            SELECT 
                COUNT(*) as total_os,
                COALESCE(SUM(total), 0) as total_valor,
                COALESCE(SUM(CASE WHEN status = 'Paga' THEN total ELSE 0 END), 0) as valor_pago,
                COALESCE(SUM(CASE WHEN status != 'Paga' THEN total ELSE 0 END), 0) as valor_pendente
            FROM ordens_servico
            WHERE data >= %s
        ''', (start_date,))
        stats = cursor.fetchone()
        
        # Carregar clientes para filtro
        cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        clientes = cursor.fetchall()
        
        conn.close()
        
        return render_template('financeiro/painel.html', ordens=ordens, stats=stats,
                             clientes=clientes, periodo=periodo, cliente_id=cliente_id)
    except Exception as e:
        flash(f'Erro ao carregar painel financeiro: {e}', 'danger')
        return render_template('financeiro/painel.html', ordens=[], stats={}, clientes=[])
