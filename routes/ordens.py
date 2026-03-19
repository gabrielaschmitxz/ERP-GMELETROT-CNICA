from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from database_web import get_db_connection
from decorators import login_required
from mapbox_integration_web import MapboxIntegration
from pdf_generator import OrderPDFGenerator
from datetime import datetime, timedelta
import psycopg2.extras
import json

bp = Blueprint('ordens', __name__, url_prefix='/ordens')
mapbox = MapboxIntegration()
pdf_generator = OrderPDFGenerator()


def _calcular_total_mensal(cursor, cliente_id: int, primeiro_dia, ultimo_dia) -> float:
    cursor.execute('''
        SELECT COALESCE(SUM(total), 0)
        FROM ordens_servico
        WHERE cliente_id = %s
          AND data >= %s AND data <= %s
          AND tipo_documento != 'ORC'
    ''', (cliente_id, primeiro_dia, ultimo_dia))
    return float(cursor.fetchone()[0] or 0)


def _upsert_cobranca_mensal(cursor, cliente_id: int, mes: int, ano: int, total_bruto: float):
    cursor.execute('''
        INSERT INTO cobrancas_mensais (cliente_id, mes, ano, total_bruto, total_liquido)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (cliente_id, mes, ano) DO UPDATE
        SET total_bruto = EXCLUDED.total_bruto,
            total_liquido = EXCLUDED.total_liquido,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    ''', (cliente_id, mes, ano, total_bruto, total_bruto))
    return cursor.fetchone()[0]


def _atualizar_status_ordens_mensais(cursor, cliente_id: int, primeiro_dia_mes, ultimo_dia_mes, status: str):
    cursor.execute('''
        UPDATE ordens_servico
        SET status = %s
        WHERE cliente_id = %s
          AND data >= %s AND data <= %s
          AND tipo_documento != 'ORC'
    ''', (status, cliente_id, primeiro_dia_mes, ultimo_dia_mes))


def _sincronizar_cobranca_mensal_por_ordens(cursor, cliente_id: int, data_referencia):
    primeiro_dia_mes = datetime(data_referencia.year, data_referencia.month, 1).date()
    if data_referencia.month == 12:
        ultimo_dia_mes = datetime(data_referencia.year + 1, 1, 1).date() - timedelta(days=1)
    else:
        ultimo_dia_mes = datetime(data_referencia.year, data_referencia.month + 1, 1).date() - timedelta(days=1)

    total_bruto = _calcular_total_mensal(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes)
    cobranca_id = _upsert_cobranca_mensal(cursor, cliente_id, primeiro_dia_mes.month, primeiro_dia_mes.year, total_bruto)

    cursor.execute('''
        SELECT
            COUNT(*) AS total_ordens,
            COUNT(*) FILTER (WHERE status = 'Paga') AS ordens_pagas
        FROM ordens_servico
        WHERE cliente_id = %s
          AND data >= %s AND data <= %s
          AND tipo_documento != 'ORC'
    ''', (cliente_id, primeiro_dia_mes, ultimo_dia_mes))
    resumo = cursor.fetchone()

    total_ordens = int(resumo['total_ordens'] or 0)
    ordens_pagas = int(resumo['ordens_pagas'] or 0)

    if total_ordens <= 0:
        return

    cursor.execute('SELECT status, parcelas FROM cobrancas_mensais WHERE id = %s', (cobranca_id,))
    cobranca = cursor.fetchone()
    status_atual = (cobranca.get('status') if cobranca else '') or 'Aguardando Pagamento'
    parcelas = int(cobranca.get('parcelas') or 1) if cobranca else 1

    if ordens_pagas == total_ordens:
        cursor.execute('''
            UPDATE cobrancas_mensais
            SET status = 'Paga',
                data_pagamento = CASE
                    WHEN COALESCE(parcelas, 1) <= 1 THEN COALESCE(data_pagamento, CURRENT_DATE)
                    ELSE data_pagamento
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (cobranca_id,))
    elif status_atual == 'Paga':
        if parcelas <= 1:
            cursor.execute('''
                UPDATE cobrancas_mensais
                SET status = 'Aguardando Pagamento',
                    data_pagamento = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (cobranca_id,))
        else:
            cursor.execute('''
                UPDATE cobrancas_mensais
                SET status = 'Aguardando Pagamento',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (cobranca_id,))


@bp.route('/mensal/status/<int:cliente_id>', methods=['POST'])
@login_required
def mensal_status(cliente_id):
    """Atualiza o status do pagamento mensal do cliente no perÃ­odo."""
    try:
        mes = request.form.get('mensal_mes', type=int) or datetime.now().month
        ano = request.form.get('mensal_ano', type=int) or datetime.now().year
        novo_status = (request.form.get('status') or '').strip()
        tipo_pagamento = (request.form.get('tipo_pagamento') or 'uma').strip().lower()
        if not novo_status:
            flash('Status Ã© obrigatÃ³rio!', 'danger')
            return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

        primeiro_dia_mes = datetime(ano, mes, 1).date()
        if mes == 12:
            ultimo_dia_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
        else:
            ultimo_dia_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        total_bruto = _calcular_total_mensal(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes)
        cobranca_id = _upsert_cobranca_mensal(cursor, cliente_id, mes, ano, total_bruto)

        cursor.execute('''
            SELECT cm.*, fp.tipo AS forma_pagamento_tipo
            FROM cobrancas_mensais cm
            LEFT JOIN formas_pagamento fp ON fp.id = cm.forma_pagamento_id
            WHERE cm.id = %s
        ''', (cobranca_id,))
        cobranca = cursor.fetchone()

        if not cobranca:
            conn.close()
            flash('Cobranca mensal nao encontrada!', 'danger')
            return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

        eh_parcelado = cobranca['forma_pagamento_tipo'] == 'Parcelado' and (cobranca.get('parcelas') or 1) > 1

        if novo_status == 'Paga' and not cobranca.get('forma_pagamento_id'):
            conn.close()
            flash('Configure a forma de pagamento antes de marcar como paga.', 'danger')
            return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

        if novo_status == 'Paga' and eh_parcelado:
            parcelas_totais = int(cobranca.get('parcelas') or 1)
            cursor.execute('''
                SELECT COUNT(*) AS total
                FROM cobrancas_mensais_parcelas
                WHERE cobranca_id = %s AND data_pagamento IS NOT NULL
            ''', (cobranca_id,))
            parcelas_pagas = int(cursor.fetchone()['total'] or 0)

            if parcelas_pagas >= parcelas_totais:
                cursor.execute('''
                    UPDATE cobrancas_mensais
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (novo_status, cobranca_id))
                _atualizar_status_ordens_mensais(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes, novo_status)
                conn.commit()
                conn.close()
                flash('Status mensal atualizado! Todas as parcelas ja estavam pagas.', 'success')
                return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

            if tipo_pagamento == 'todas':
                cursor.execute('''
                    UPDATE cobrancas_mensais_parcelas
                    SET data_pagamento = CURRENT_DATE
                    WHERE cobranca_id = %s AND data_pagamento IS NULL
                ''', (cobranca_id,))
                cursor.execute('''
                    UPDATE cobrancas_mensais
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (novo_status, cobranca_id))
                _atualizar_status_ordens_mensais(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes, novo_status)
                conn.commit()
                conn.close()
                flash('Todas as parcelas restantes da cobranca mensal foram registradas.', 'success')
                return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

            cursor.execute('''
                SELECT id, numero_parcela
                FROM cobrancas_mensais_parcelas
                WHERE cobranca_id = %s AND data_pagamento IS NULL
                ORDER BY numero_parcela
                LIMIT 1
            ''', (cobranca_id,))
            proxima_parcela = cursor.fetchone()
            if proxima_parcela:
                cursor.execute('''
                    UPDATE cobrancas_mensais_parcelas
                    SET data_pagamento = CURRENT_DATE
                    WHERE id = %s
                ''', (proxima_parcela['id'],))

            cursor.execute('''
                SELECT COUNT(*) AS total
                FROM cobrancas_mensais_parcelas
                WHERE cobranca_id = %s AND data_pagamento IS NOT NULL
            ''', (cobranca_id,))
            parcelas_pagas = int(cursor.fetchone()['total'] or 0)
            status_final = 'Paga' if parcelas_pagas >= parcelas_totais else 'Aguardando Pagamento'

            cursor.execute('''
                UPDATE cobrancas_mensais
                SET status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (status_final, cobranca_id))
            _atualizar_status_ordens_mensais(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes, status_final)

            conn.commit()
            conn.close()

            if proxima_parcela:
                if status_final == 'Paga':
                    flash(f"Parcela {proxima_parcela['numero_parcela']}/{parcelas_totais} registrada! Cobranca mensal totalmente paga.", 'success')
                else:
                    flash(f"Parcela {proxima_parcela['numero_parcela']}/{parcelas_totais} registrada! Ainda ha parcelas pendentes.", 'info')
            else:
                flash('Status mensal atualizado!', 'success')
            return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

        # Regra de negÃ³cio: alterar o status de TODAS as ordens (OS) do cliente no mÃªs/ano selecionado
        cursor.execute('''
            UPDATE cobrancas_mensais
            SET status = %s,
                updated_at = CURRENT_TIMESTAMP,
                data_pagamento = CASE WHEN %s = 'Paga' THEN COALESCE(data_pagamento, CURRENT_DATE) ELSE NULL END
            WHERE id = %s
        ''', (novo_status, novo_status, cobranca_id))
        _atualizar_status_ordens_mensais(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes, novo_status)

        conn.commit()
        conn.close()

        flash('Status mensal atualizado!', 'success')
        return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))
    except Exception as e:
        flash(f'Erro ao atualizar status mensal: {e}', 'danger')
        return redirect(url_for('ordens.listar', aba='mensal'))


@bp.route('/mensal/desconto/<int:cliente_id>', methods=['POST'])
@login_required
def mensal_desconto(cliente_id):
    """Aplica desconto (fixo ou percentual) no total mensal consolidado."""
    try:
        mes = request.form.get('mensal_mes', type=int) or datetime.now().month
        ano = request.form.get('mensal_ano', type=int) or datetime.now().year
        desconto_tipo = (request.form.get('desconto_tipo') or '').strip()
        desconto_valor = float(request.form.get('desconto_valor') or 0)

        primeiro_dia_mes = datetime(ano, mes, 1).date()
        if mes == 12:
            ultimo_dia_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
        else:
            ultimo_dia_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)

        conn = get_db_connection()
        cursor = conn.cursor()
        total_bruto = _calcular_total_mensal(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes)
        cobranca_id = _upsert_cobranca_mensal(cursor, cliente_id, mes, ano, total_bruto)

        desconto_percentual = 0.0
        desconto_valor_final = 0.0
        if desconto_tipo == 'percentual':
            desconto_percentual = max(0.0, min(100.0, desconto_valor))
            desconto_valor_final = (total_bruto * desconto_percentual) / 100.0
        elif desconto_tipo == 'fixo':
            desconto_valor_final = max(0.0, desconto_valor)
        else:
            desconto_tipo = None

        total_liquido = max(total_bruto - desconto_valor_final, 0.0)

        cursor.execute('''
            UPDATE cobrancas_mensais
            SET desconto_tipo = %s,
                desconto_valor = %s,
                desconto_percentual = %s,
                total_liquido = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (desconto_tipo, desconto_valor_final, desconto_percentual, total_liquido, cobranca_id))

        conn.commit()
        conn.close()

        flash('Desconto mensal aplicado!', 'success')
        return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))
    except Exception as e:
        flash(f'Erro ao aplicar desconto mensal: {e}', 'danger')
        return redirect(url_for('ordens.listar', aba='mensal'))


@bp.route('/mensal/pagamento/<int:cliente_id>', methods=['POST'])
@login_required
def mensal_pagamento(cliente_id):
    """Configura forma de pagamento do relatÃ³rio mensal e gera parcelas automaticamente (30/30 dias)."""
    try:
        mes = request.form.get('mensal_mes', type=int) or datetime.now().month
        ano = request.form.get('mensal_ano', type=int) or datetime.now().year
        forma_pagamento_id = request.form.get('forma_pagamento_id', type=int)
        parcelas = request.form.get('parcelas', type=int) or 1
        data_pagamento_raw = (request.form.get('data_pagamento') or '').strip()
        data_primeira_raw = (request.form.get('data_primeira_parcela') or '').strip()
        desconto_tipo = (request.form.get('desconto_tipo') or '').strip()
        desconto_valor = float(request.form.get('desconto_valor') or 0)

        data_pagamento = None
        data_primeira = None
        if data_pagamento_raw:
            data_pagamento = datetime.strptime(data_pagamento_raw, '%Y-%m-%d').date()
        if data_primeira_raw:
            data_primeira = datetime.strptime(data_primeira_raw, '%Y-%m-%d').date()

        if not forma_pagamento_id:
            flash('Forma de pagamento Ã© obrigatÃ³ria!', 'danger')
            return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))

        primeiro_dia_mes = datetime(ano, mes, 1).date()
        if mes == 12:
            ultimo_dia_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
        else:
            ultimo_dia_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # total bruto
        total_bruto = _calcular_total_mensal(cursor, cliente_id, primeiro_dia_mes, ultimo_dia_mes)
        cobranca_id = _upsert_cobranca_mensal(cursor, cliente_id, mes, ano, total_bruto)
        cursor.execute('SELECT * FROM cobrancas_mensais WHERE id = %s', (cobranca_id,))
        cobranca_atual = cursor.fetchone()
        status_atual = (cobranca_atual.get('status') if cobranca_atual else '') or 'Aguardando Pagamento'

        # aplicar desconto jÃ¡ salvo (se houver)
        desconto_percentual = 0.0
        desconto_valor_final = 0.0
        if desconto_tipo == 'percentual':
            desconto_percentual = max(0.0, min(100.0, desconto_valor))
            desconto_valor_final = (total_bruto * desconto_percentual) / 100.0
        elif desconto_tipo == 'fixo':
            desconto_valor_final = max(0.0, desconto_valor)
        else:
            desconto_tipo = None
        total_liquido = max(total_bruto - desconto_valor_final, 0.0)

        # buscar tipo da forma de pagamento
        cursor.execute('SELECT tipo FROM formas_pagamento WHERE id = %s', (forma_pagamento_id,))
        fp = cursor.fetchone()
        fp_tipo = (fp['tipo'] if fp else '') or ''

        # limpar parcelas anteriores (regerar)
        cursor.execute('DELETE FROM cobrancas_mensais_parcelas WHERE cobranca_id = %s', (cobranca_id,))

        status = status_atual
        if fp_tipo != 'Parcelado' or parcelas <= 1:
            # Ã€ vista
            parcelas = 1
            if not data_pagamento:
                flash('Informe a data de pagamento (Ã  vista).', 'danger')
                conn.close()
                return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))
            data_pagamento_parcela = data_pagamento if status == 'Paga' else None
            cursor.execute('''
                INSERT INTO cobrancas_mensais_parcelas (cobranca_id, numero_parcela, valor_parcela, data_vencimento, data_pagamento)
                VALUES (%s, 1, %s, %s, %s)
            ''', (cobranca_id, total_liquido, data_pagamento, data_pagamento_parcela))
            cursor.execute('''
                UPDATE cobrancas_mensais
                SET forma_pagamento_id=%s, parcelas=%s, data_pagamento=%s, data_primeira_parcela=NULL, status=%s,
                    total_bruto=%s, desconto_tipo=%s, desconto_valor=%s, desconto_percentual=%s, total_liquido=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            ''', (
                forma_pagamento_id, parcelas, data_pagamento, status,
                total_bruto, desconto_tipo, desconto_valor_final, desconto_percentual, total_liquido,
                cobranca_id
            ))
        else:
            # Parcelado
            if not data_primeira:
                flash('Informe a data da primeira parcela (parcelado).', 'danger')
                conn.close()
                return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))
            parcelas = max(1, parcelas)
            valor_parcela = (total_liquido / parcelas) if parcelas > 0 else 0.0
            for n in range(1, parcelas + 1):
                venc = data_primeira + timedelta(days=30 * (n - 1))
                data_pagamento_parcela = venc if status == 'Paga' else None
                cursor.execute('''
                    INSERT INTO cobrancas_mensais_parcelas (cobranca_id, numero_parcela, valor_parcela, data_vencimento, data_pagamento)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (cobranca_id, numero_parcela) DO UPDATE
                    SET valor_parcela = EXCLUDED.valor_parcela,
                        data_vencimento = EXCLUDED.data_vencimento,
                        data_pagamento = EXCLUDED.data_pagamento
                ''', (cobranca_id, n, valor_parcela, venc, data_pagamento_parcela))
            cursor.execute('''
                UPDATE cobrancas_mensais
                SET forma_pagamento_id=%s, parcelas=%s, data_pagamento=NULL, data_primeira_parcela=%s, status=%s,
                    total_bruto=%s, desconto_tipo=%s, desconto_valor=%s, desconto_percentual=%s, total_liquido=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
            ''', (
                forma_pagamento_id, parcelas, data_primeira, status,
                total_bruto, desconto_tipo, desconto_valor_final, desconto_percentual, total_liquido,
                cobranca_id
            ))

        conn.commit()
        conn.close()

        if request.form.get('redirect_to_pdf') == '1':
            data_inicio_pdf = (request.form.get('pdf_data_inicio') or '').strip()
            data_fim_pdf = (request.form.get('pdf_data_fim') or '').strip()
            if data_inicio_pdf and data_fim_pdf:
                return redirect(url_for(
                    'clientes.relatorio_mensal',
                    id=cliente_id,
                    data_inicio=data_inicio_pdf,
                    data_fim=data_fim_pdf,
                    forma_pagamento_id=forma_pagamento_id,
                    parcelas=parcelas,
                    data_pagamento=(data_pagamento.isoformat() if data_pagamento else ''),
                    data_primeira_parcela=(data_primeira.isoformat() if data_primeira else ''),
                    desconto_tipo=desconto_tipo or '',
                    desconto_valor=(desconto_percentual if desconto_tipo == 'percentual' else desconto_valor_final)
                ))

        flash('Pagamento mensal configurado!', 'success')
        return redirect(url_for('ordens.listar', aba='mensal', mensal_mes=mes, mensal_ano=ano))
    except Exception as e:
        flash(f'Erro ao configurar pagamento mensal: {e}', 'danger')
        return redirect(url_for('ordens.listar', aba='mensal'))

@bp.route('/')
@login_required
def listar():
    """Listar todas as ordens de serviÃ§o"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Aba ativa (Geral ou Mensal)
        aba = (request.args.get('aba', 'geral') or 'geral').strip().lower()
        
        # Filtros (aba Geral)
        cliente_id = request.args.get('cliente_id', type=int)
        status = request.args.get('status', '')
        tipo_documento = request.args.get('tipo_documento', '')
        forma_pagamento_id = request.args.get('forma_pagamento_id', type=int)
        mes = (request.args.get('mes', '') or '').strip()
        pesquisa = request.args.get('pesquisa', '').strip()
        
        # Filtros (aba Mensal)
        mensal_mes = request.args.get('mensal_mes', type=int)
        mensal_ano = request.args.get('mensal_ano', type=int)
        mensal_data_inicio = (request.args.get('mensal_data_inicio', '') or '').strip()
        mensal_data_fim = (request.args.get('mensal_data_fim', '') or '').strip()
        hoje = datetime.now()
        if not mensal_mes:
            mensal_mes = hoje.month
        if not mensal_ano:
            mensal_ano = hoje.year
        
        query = '''
            SELECT os.*, c.nome as cliente_nome, fp.nome as forma_pagamento_nome, fp.tipo as forma_pagamento_tipo,
                   COALESCE(pp.parcelas_pagas, 0) as parcelas_pagas
            FROM ordens_servico os
            LEFT JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
            LEFT JOIN (
                SELECT ordem_id, COUNT(*) AS parcelas_pagas
                FROM parcelas_pagas
                GROUP BY ordem_id
            ) pp ON pp.ordem_id = os.id
            WHERE 1=1
        '''
        params = []
        
        if cliente_id:
            query += ' AND os.cliente_id = %s'
            params.append(cliente_id)
        
        if status:
            query += ' AND os.status = %s'
            params.append(status)

        if tipo_documento:
            query += ' AND os.tipo_documento = %s'
            params.append(tipo_documento)
        
        if forma_pagamento_id:
            query += ' AND os.forma_pagamento_id = %s'
            params.append(forma_pagamento_id)
        
        if mes:
            try:
                # Formato esperado: YYYY-MM
                ano, mes_num = mes.split('-')
                query += ' AND EXTRACT(YEAR FROM os.data) = %s AND EXTRACT(MONTH FROM os.data) = %s'
                params.append(int(ano))
                params.append(int(mes_num))
            except:
                pass
        
        if pesquisa:
            try:
                # Tentar converter para nÃºmero (ID da ordem)
                ordem_id = int(pesquisa)
                query += ' AND os.id = %s'
                params.append(ordem_id)
            except ValueError:
                # Se nÃ£o for nÃºmero, pesquisar por nome do cliente
                query += ' AND c.nome ILIKE %s'
                params.append(f'%{pesquisa}%')
        
        query += ' ORDER BY os.id DESC'
        cursor.execute(query, params)
        ordens = cursor.fetchall()
        
        # Carregar clientes para filtro (mesma conexÃ£o)
        cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        clientes = cursor.fetchall()
        
        # Carregar formas de pagamento para filtro
        cursor.execute('SELECT id, nome, tipo, parcelas_max FROM formas_pagamento ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        # --------------------
        # Aba Mensal (clientes com cobranÃ§a mensal consolidada)
        # --------------------
        # PerÃ­odo da aba Mensal: por padrÃ£o mÃªs/ano; se vier data_inicio/data_fim usa o intervalo
        primeiro_dia_mes = datetime(mensal_ano, mensal_mes, 1).date()
        if mensal_mes == 12:
            ultimo_dia_mes = datetime(mensal_ano + 1, 1, 1).date() - timedelta(days=1)
        else:
            ultimo_dia_mes = datetime(mensal_ano, mensal_mes + 1, 1).date() - timedelta(days=1)
        if mensal_data_inicio and mensal_data_fim:
            try:
                primeiro_dia_mes = datetime.strptime(mensal_data_inicio, '%Y-%m-%d').date()
                ultimo_dia_mes = datetime.strptime(mensal_data_fim, '%Y-%m-%d').date()
            except Exception:
                pass
        
        # Clientes da aba Mensal: todos que tiverem ordens (OS) no perÃ­odo selecionado
        cursor.execute('''
            SELECT DISTINCT c.id, c.nome, c.cnpj_cpf
            FROM ordens_servico os
            INNER JOIN clientes c ON c.id = os.cliente_id
            WHERE os.data >= %s AND os.data <= %s
              AND os.tipo_documento != 'ORC'
            ORDER BY c.nome
        ''', (primeiro_dia_mes, ultimo_dia_mes))
        clientes_mensais = cursor.fetchall()
        clientes_mensais_ids = [c['id'] for c in clientes_mensais] if clientes_mensais else []
        
        ordens_por_cliente = {}
        totais_map = {}
        cobrancas_map = {}
        
        if clientes_mensais_ids:
            cursor.execute('''
                SELECT os.id, os.cliente_id, os.data, os.tipo_documento, os.codigo_orcamento, os.total, os.status,
                       os.parcelas, fp.nome AS forma_pagamento_nome, fp.tipo AS forma_pagamento_tipo,
                       COALESCE(pp.parcelas_pagas, 0) AS parcelas_pagas
                FROM ordens_servico os
                LEFT JOIN formas_pagamento fp ON fp.id = os.forma_pagamento_id
                LEFT JOIN (
                    SELECT ordem_id, COUNT(*) AS parcelas_pagas
                    FROM parcelas_pagas
                    GROUP BY ordem_id
                ) pp ON pp.ordem_id = os.id
                WHERE os.cliente_id = ANY(%s)
                  AND os.data >= %s AND os.data <= %s
                  AND os.tipo_documento != 'ORC'
                ORDER BY os.cliente_id, os.data, os.id
            ''', (clientes_mensais_ids, primeiro_dia_mes, ultimo_dia_mes))
            ordens_mensais = cursor.fetchall()
            
            for o in ordens_mensais:
                cid = o['cliente_id']
                ordens_por_cliente.setdefault(cid, []).append(o)
                totais_map[cid] = float(totais_map.get(cid, 0) or 0) + float(o.get('total') or 0)
            
            cursor.execute('''
                SELECT cm.*, fp.nome AS forma_pagamento_nome, fp.tipo AS forma_pagamento_tipo,
                       COALESCE(cmp.parcelas_pagas, 0) AS parcelas_pagas
                FROM cobrancas_mensais cm
                LEFT JOIN formas_pagamento fp ON fp.id = cm.forma_pagamento_id
                LEFT JOIN (
                    SELECT cobranca_id, COUNT(*) FILTER (WHERE data_pagamento IS NOT NULL) AS parcelas_pagas
                    FROM cobrancas_mensais_parcelas
                    GROUP BY cobranca_id
                ) cmp ON cmp.cobranca_id = cm.id
                WHERE cm.cliente_id = ANY(%s) AND cm.mes = %s AND cm.ano = %s
            ''', (clientes_mensais_ids, mensal_mes, mensal_ano))
            cobrancas = cursor.fetchall()
            if cobrancas:
                cobrancas = [
                    c for c in cobrancas
                    if float(c.get('total_bruto') or 0) > 0 or float(c.get('total_liquido') or 0) > 0
                ]
            cobrancas_map = {c['cliente_id']: c for c in cobrancas} if cobrancas else {}
        
        conn.close()
        
        return render_template(
            'ordens/listar.html',
            # Geral
            ordens=ordens, clientes=clientes, formas_pagamento=formas_pagamento,
            cliente_id=cliente_id, status=status, forma_pagamento_id=forma_pagamento_id, mes=mes, pesquisa=pesquisa,
            tipo_documento=tipo_documento,
            # Tabs
            aba=aba,
            # Mensal
            mensal_mes=mensal_mes, mensal_ano=mensal_ano,
            mensal_data_inicio=mensal_data_inicio, mensal_data_fim=mensal_data_fim,
            clientes_mensais=clientes_mensais,
            ordens_por_cliente=ordens_por_cliente,
            totais_mensais_por_cliente=totais_map,
            cobrancas_mensais_por_cliente=cobrancas_map,
            primeiro_dia_mes=primeiro_dia_mes,
            ultimo_dia_mes=ultimo_dia_mes
        )
    except Exception as e:
        flash(f'Erro ao carregar ordens: {e}', 'danger')
        return render_template('ordens/listar.html', ordens=[], clientes=[], formas_pagamento=[])

@bp.route('/nova', methods=['GET', 'POST'])
@login_required
def nova():
    """Criar nova ordem de serviÃ§o"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            cliente_id = data.get('cliente_id')
            tipo_documento = (data.get('tipo_documento') or 'OS').strip()
            data_ordem_str = data.get('data')
            endereco_origem = data.get('endereco_origem', '').strip()
            endereco_destino = data.get('endereco_destino', '').strip()
            servicos = data.get('servicos', [])
            materiais = data.get('materiais', [])
            adicionais = data.get('adicionais', [])
            forma_pagamento_id = data.get('forma_pagamento_id')
            assinatura_id = data.get('assinatura_id')
            parcelas = data.get('parcelas', 1)
            distance_data = data.get('distance_data', {})
            
            if not cliente_id:
                return jsonify({'success': False, 'error': 'Cliente Ã© obrigatÃ³rio!'}), 400
            
            # Validar: precisa ter endereÃ§os OU distance_data com KM
            has_distance_data = distance_data and distance_data.get('distance_km')
            if (not endereco_origem or not endereco_destino) and not has_distance_data:
                return jsonify({'success': False, 'error': 'Preencha os endereÃ§os ou informe os KM manualmente!'}), 400
            
            # Se nÃ£o tem endereÃ§os mas tem KM, usar valores padrÃ£o
            if not endereco_origem:
                endereco_origem = 'NÃ£o informado'
            if not endereco_destino:
                endereco_destino = 'NÃ£o informado'
            
            if not servicos and not materiais:
                return jsonify({'success': False, 'error': 'Adicione pelo menos um serviÃ§o ou material!'}), 400
            
            # Converter data
            try:
                data_ordem = datetime.strptime(data_ordem_str, "%d/%m/%Y").date()
            except:
                data_ordem = datetime.now().date()
            
            # Calcular totais
            servicos_total = sum(s.get('total', 0) for s in servicos)
            materiais_total = sum(m.get('total', 0) for m in materiais)
            impostos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'imposto')
            bdi_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'bdi')
            descontos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'desconto')
            deslocamento_total = distance_data.get('displacement_cost', 0) or 0
            
            total_geral = (servicos_total + materiais_total + deslocamento_total + 
                          impostos_total + bdi_total - descontos_total)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Se for orÃ§amento, gerar cÃ³digo independente (sequencial)
            codigo_orcamento = None
            status_inicial = 'Nova'
            if tipo_documento == 'ORC':
                cursor.execute("SELECT COALESCE(MAX(codigo_orcamento), 0) + 1 FROM ordens_servico WHERE tipo_documento = 'ORC'")
                codigo_orcamento = cursor.fetchone()[0]

            # Inserir ordem
            cursor.execute('''
                INSERT INTO ordens_servico (cliente_id, data, endereco_origem, endereco_destino,
                                          km, valor_deslocamento, total, status, forma_pagamento_id, parcelas, assinatura_id,
                                          tipo_documento, codigo_orcamento)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (cliente_id, data_ordem, endereco_origem, endereco_destino,
                  distance_data.get('distance_km', 0), deslocamento_total, total_geral, 
                  status_inicial, forma_pagamento_id, parcelas, assinatura_id,
                  tipo_documento, codigo_orcamento))
            
            ordem_id = cursor.fetchone()[0]
            
            # MigraÃ§Ã£o automÃ¡tica: adicionar colunas 'local' e 'data' na tabela itens_servico se nÃ£o existirem
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='data'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # MigraÃ§Ã£o automÃ¡tica: adicionar coluna 'data' na tabela itens_material se nÃ£o existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_material' AND column_name='data'
                    ) THEN
                        ALTER TABLE itens_material ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            conn.commit()
            
            # Inserir serviÃ§os
            for servico in servicos:
                descricao = servico.get('nome', '')
                if servico.get('tempo') and servico.get('taxa'):
                    descricao += f" - Tempo: {servico['tempo']}h x Taxa: R$ {servico['taxa']:.2f}/h"
                
                # Tratar local de forma segura (pode ser None ou string vazia)
                local = servico.get('local')
                if local:
                    local = str(local).strip() or None
                else:
                    local = None
                
                # Tratar data de forma segura
                data_servico = servico.get('data')
                if data_servico:
                    try:
                        if isinstance(data_servico, str):
                            data_servico = datetime.strptime(data_servico, "%Y-%m-%d").date()
                    except:
                        data_servico = None
                else:
                    data_servico = None
                
                cursor.execute('''
                    INSERT INTO itens_servico (ordem_id, servico_id, descricao, qtd, valor_unit, valor_total, local, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (ordem_id, servico.get('id'), descricao, servico.get('qtd', 1),
                      servico.get('preco_unit', 0), servico.get('total', 0), local, data_servico))
            
            # Inserir materiais
            for material in materiais:
                descricao = material.get('nome', '')
                if material.get('marca'):
                    descricao += f" - {material['marca']}"
                
                # Converter data se fornecida
                data_material = None
                if material.get('data'):
                    try:
                        data_material = datetime.strptime(material.get('data'), '%Y-%m-%d').date()
                    except:
                        pass
                
                cursor.execute('''
                    INSERT INTO itens_material (ordem_id, material_id, descricao, qtd, valor_unit, valor_total, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (ordem_id, material.get('id'), descricao, material.get('qtd', 1),
                      material.get('preco_unit', 0), material.get('total', 0), data_material))
            
            # Inserir adicionais
            for adicional in adicionais:
                cursor.execute('''
                    INSERT INTO adicionais (ordem_id, tipo, descricao, valor)
                    VALUES (%s, %s, %s, %s)
                ''', (ordem_id, adicional.get('tipo'), adicional.get('descricao'), adicional.get('valor', 0)))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'ordem_id': ordem_id, 'message': 'Ordem de serviÃ§o salva com sucesso!'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # GET - mostrar formulÃ¡rio
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Otimizar: fazer todas as consultas na mesma conexÃ£o
        cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        clientes = cursor.fetchall()
        
        cursor.execute('SELECT id, nome, tipo, parcelas_max FROM formas_pagamento WHERE ativo = true ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        # Adicionar coluna cargo se nÃ£o existir (migraÃ§Ã£o) - apenas uma vez
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='assinaturas' AND column_name='cargo'
                    ) THEN
                        ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'TÃ©cnico Eletricista Industrial/Residencial';
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna cargo: {e}")
        
        cursor.execute('SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE ativo = true ORDER BY padrao DESC, nome')
        assinaturas = cursor.fetchall()
        
        # Carregar listas para seleÃ§Ã£o (otimizado: apenas campos necessÃ¡rios) - apenas ativos
        cursor.execute('SELECT id, nome, preco_unit FROM servicos WHERE ativo = true ORDER BY nome')
        servicos = cursor.fetchall()
        
        cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais WHERE ativo = true ORDER BY nome')
        materiais = cursor.fetchall()
        
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'imposto' AND ativo = true ORDER BY descricao")
        impostos = cursor.fetchall()
        
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'bdi' AND ativo = true ORDER BY descricao")
        bdi_list = cursor.fetchall()
        
        conn.close()
        
        return render_template('ordens/form.html', ordem=None,
                             clientes=clientes, 
                             formas_pagamento=formas_pagamento,
                             servicos=servicos, materiais=materiais,
                             impostos=impostos, bdi_list=bdi_list,
                             assinaturas=assinaturas)
    except Exception as e:
        flash(f'Erro ao carregar formulÃ¡rio: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/calcular_distancia', methods=['POST'])
@login_required
def calcular_distancia():
    """Calcular distÃ¢ncia entre endereÃ§os"""
    try:
        data = request.get_json()
        origem = data.get('origem', '').strip()
        destino = data.get('destino', '').strip()
        taxa_km = float(data.get('taxa_km', 5.0))
        
        if not origem or not destino:
            return jsonify({'success': False, 'error': 'Preencha ambos os endereÃ§os!'}), 400
        
        result = mapbox.process_addresses(origem, destino)
        
        if result['success']:
            # Recalcular com taxa personalizada
            if taxa_km and taxa_km > 0:
                result['displacement_cost'] = round(result['distance_km'] * taxa_km, 2)
            
            return jsonify({'success': True, 'data': result})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Erro ao calcular distÃ¢ncia')}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar ordem de serviÃ§o"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            cliente_id = data.get('cliente_id')
            data_ordem_str = data.get('data')
            endereco_origem = data.get('endereco_origem', '').strip()
            endereco_destino = data.get('endereco_destino', '').strip()
            servicos = data.get('servicos', [])
            materiais = data.get('materiais', [])
            adicionais = data.get('adicionais', [])
            forma_pagamento_id = data.get('forma_pagamento_id')
            assinatura_id = data.get('assinatura_id')
            parcelas = data.get('parcelas', 1)
            distance_data = data.get('distance_data', {})
            
            if not cliente_id:
                return jsonify({'success': False, 'error': 'Cliente Ã© obrigatÃ³rio!'}), 400
            
            # Converter data
            try:
                data_ordem = datetime.strptime(data_ordem_str, "%d/%m/%Y").date()
            except:
                data_ordem = datetime.now().date()
            
            # Calcular totais
            servicos_total = sum(s.get('total', 0) for s in servicos)
            materiais_total = sum(m.get('total', 0) for m in materiais)
            impostos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'imposto')
            bdi_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'bdi')
            descontos_total = sum(a.get('valor', 0) for a in adicionais if a.get('tipo') == 'desconto')
            deslocamento_total = distance_data.get('displacement_cost', 0) or 0
            
            total_geral = (servicos_total + materiais_total + deslocamento_total + 
                          impostos_total + bdi_total - descontos_total)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Atualizar ordem
            cursor.execute('''
                UPDATE ordens_servico 
                SET cliente_id=%s, data=%s, endereco_origem=%s, endereco_destino=%s,
                    km=%s, valor_deslocamento=%s, total=%s, forma_pagamento_id=%s, parcelas=%s, assinatura_id=%s
                WHERE id=%s
            ''', (cliente_id, data_ordem, endereco_origem, endereco_destino,
                  distance_data.get('distance_km', 0), deslocamento_total, total_geral, 
                  forma_pagamento_id, parcelas, assinatura_id, id))
            
            # MigraÃ§Ã£o automÃ¡tica: adicionar coluna 'local' na tabela itens_servico se nÃ£o existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='itens_servico' AND column_name='local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                END $$;
            ''')
            conn.commit()
            
            # MigraÃ§Ã£o automÃ¡tica: adicionar colunas 'local' e 'data' na tabela itens_servico se nÃ£o existirem
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_servico' AND column_name = 'local'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN local VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_servico' AND column_name = 'data'
                    ) THEN
                        ALTER TABLE itens_servico ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # MigraÃ§Ã£o automÃ¡tica: adicionar coluna 'data' na tabela itens_material se nÃ£o existir
            cursor.execute('''
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'itens_material' AND column_name = 'data'
                    ) THEN
                        ALTER TABLE itens_material ADD COLUMN data DATE;
                    END IF;
                END $$;
            ''')
            
            # Limpar itens antigos para recriar
            cursor.execute('DELETE FROM itens_servico WHERE ordem_id=%s', (id,))
            cursor.execute('DELETE FROM itens_material WHERE ordem_id=%s', (id,))
            cursor.execute('DELETE FROM adicionais WHERE ordem_id=%s', (id,))
            
            # Inserir serviÃ§os
            for servico in servicos:
                descricao = servico.get('nome', '')
                if servico.get('tempo') and servico.get('taxa'):
                    descricao += f" - Tempo: {servico['tempo']}h x Taxa: R$ {servico['taxa']:.2f}/h"
                
                # Tratar local de forma segura (pode ser None ou string vazia)
                local = servico.get('local')
                if local:
                    local = str(local).strip() or None
                else:
                    local = None
                
                # Tratar data de forma segura
                data_servico = servico.get('data')
                if data_servico:
                    try:
                        if isinstance(data_servico, str):
                            data_servico = datetime.strptime(data_servico, "%Y-%m-%d").date()
                    except:
                        data_servico = None
                else:
                    data_servico = None
                
                cursor.execute('''
                    INSERT INTO itens_servico (ordem_id, servico_id, descricao, qtd, valor_unit, valor_total, local, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (id, servico.get('id'), descricao, servico.get('qtd', 1),
                      servico.get('preco_unit', 0), servico.get('total', 0), local, data_servico))
            
            # Inserir materiais
            for material in materiais:
                descricao = material.get('nome', '')
                if material.get('marca'):
                    descricao += f" - {material['marca']}"
                
                # Converter data se fornecida
                data_material = None
                if material.get('data'):
                    try:
                        data_material = datetime.strptime(material.get('data'), '%Y-%m-%d').date()
                    except:
                        pass
                
                cursor.execute('''
                    INSERT INTO itens_material (ordem_id, material_id, descricao, qtd, valor_unit, valor_total, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (id, material.get('id'), descricao, material.get('qtd', 1),
                      material.get('preco_unit', 0), material.get('total', 0), data_material))
            
            # Inserir adicionais
            for adicional in adicionais:
                cursor.execute('''
                    INSERT INTO adicionais (ordem_id, tipo, descricao, valor)
                    VALUES (%s, %s, %s, %s)
                ''', (id, adicional.get('tipo'), adicional.get('descricao'), adicional.get('valor', 0)))
            
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'ordem_id': id, 'message': 'Ordem de serviÃ§o atualizada com sucesso!'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # GET - Carregar dados para ediÃ§Ã£o
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar Ordem
        cursor.execute('SELECT * FROM ordens_servico WHERE id = %s', (id,))
        ordem = cursor.fetchone()
        
        if not ordem:
            flash('Ordem nÃ£o encontrada!', 'danger')
            return redirect(url_for('ordens.listar'))
            
        # Buscar Itens
        cursor.execute('SELECT * FROM itens_servico WHERE ordem_id = %s', (id,))
        db_servicos = cursor.fetchall()
        
        cursor.execute('SELECT * FROM itens_material WHERE ordem_id = %s', (id,))
        db_materiais = cursor.fetchall()
        
        cursor.execute('SELECT * FROM adicionais WHERE ordem_id = %s', (id,))
        db_adicionais = cursor.fetchall()
        
        # Preparar JSON para o frontend
        servicos_js = []
        for s in db_servicos:
            servicos_js.append({
                'id': s['servico_id'],
                'nome': s['descricao'].split(' - ')[0],
                'preco_unit': float(s['valor_unit']),
                'qtd': s['qtd'],
                'total': float(s['valor_total']),
                'tempo': 0, 'taxa': 0, # Simplificado
                'local': s.get('local') or None,
                'data': s.get('data').strftime('%Y-%m-%d') if s.get('data') else None
            })
            
        materiais_js = []
        for m in db_materiais:
            # Calcular adicional a partir dos valores salvos
            # Se total != preco_unit * qtd, entÃ£o hÃ¡ um adicional aplicado
            preco_unit = float(m['valor_unit'])
            qtd = m['qtd']
            total = float(m['valor_total'])
            
            # Calcular adicional: preco_com_adicional = total / qtd
            # adicional = ((preco_com_adicional / preco_unit) - 1) * 100
            adicional = 0.0
            if preco_unit > 0 and qtd > 0:
                preco_com_adicional = total / qtd
                adicional = ((preco_com_adicional / preco_unit) - 1) * 100
                # Arredondar para evitar problemas de precisÃ£o
                adicional = round(adicional, 2)
            
            materiais_js.append({
                'id': m['material_id'],
                'nome': m['descricao'].split(' - ')[0],
                'preco_unit': preco_unit,
                'adicional': adicional,
                'qtd': qtd,
                'total': total,
                'data': m['data'].strftime('%Y-%m-%d') if m.get('data') else None
            })
            
        adicionais_js = []
        for a in db_adicionais:
            adicionais_js.append({
                'tipo': a['tipo'],
                'descricao': a['descricao'],
                'valor': float(a['valor'])
            })
            
        # Carregar listas auxiliares (otimizado: apenas campos necessÃ¡rios)
        cursor.execute('SELECT id, nome FROM clientes WHERE ativo = true ORDER BY nome')
        clientes = cursor.fetchall()
        cursor.execute('SELECT id, nome, tipo, parcelas_max FROM formas_pagamento WHERE ativo = true ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        # Adicionar coluna cargo se nÃ£o existir (migraÃ§Ã£o) - apenas uma vez
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='assinaturas' AND column_name='cargo'
                    ) THEN
                        ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'TÃ©cnico Eletricista Industrial/Residencial';
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna cargo: {e}")
        
        cursor.execute('SELECT id, nome, cargo, caminho_imagem, ativo, padrao FROM assinaturas WHERE ativo = true ORDER BY padrao DESC, nome')
        assinaturas = cursor.fetchall()
        cursor.execute('SELECT id, nome, preco_unit FROM servicos WHERE ativo = true ORDER BY nome')
        servicos_list = cursor.fetchall()
        cursor.execute('SELECT id, nome, marca, preco_unit FROM materiais WHERE ativo = true ORDER BY nome')
        materiais_list = cursor.fetchall()
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'imposto' AND ativo = true ORDER BY descricao")
        impostos = cursor.fetchall()
        cursor.execute("SELECT id, descricao, valor FROM impostos_bdi WHERE tipo = 'bdi' AND ativo = true ORDER BY descricao")
        bdi_list = cursor.fetchall()
        
        conn.close()
        
        return render_template('ordens/form.html', 
                             ordem=ordem,
                             servicos_json=json.dumps(servicos_js),
                             materiais_json=json.dumps(materiais_js),
                             adicionais_json=json.dumps(adicionais_js),
                             clientes=clientes, 
                             formas_pagamento=formas_pagamento, 
                             servicos=servicos_list, 
                             materiais=materiais_list,
                             impostos=impostos, 
                             bdi_list=bdi_list,
                             assinaturas=assinaturas)
                             
    except Exception as e:
        flash(f'Erro ao carregar ediÃ§Ã£o: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/gerar_pdf/<int:id>')
@login_required
def gerar_pdf(id):
    """Gerar PDF da ordem de serviÃ§o"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar dados da ordem
        cursor.execute('''
            SELECT os.*, c.id as cliente_id, c.nome as cliente_nome,
                   ass.nome as assinatura_nome
            FROM ordens_servico os
            JOIN clientes c ON os.cliente_id = c.id
            LEFT JOIN assinaturas ass ON os.assinatura_id = ass.id
            WHERE os.id = %s
        ''', (id,))
        ordem = cursor.fetchone()
        
        if not ordem:
            flash('Ordem de serviÃ§o nÃ£o encontrada!', 'danger')
            return redirect(url_for('ordens.listar'))
        
        # Buscar serviÃ§os, materiais e adicionais
        cursor.execute('SELECT * FROM itens_servico WHERE ordem_id = %s', (id,))
        servicos = cursor.fetchall()
        
        cursor.execute('SELECT * FROM itens_material WHERE ordem_id = %s', (id,))
        materiais = cursor.fetchall()
        
        cursor.execute('SELECT * FROM adicionais WHERE ordem_id = %s', (id,))
        adicionais = cursor.fetchall()
        
        conn.close()
        
        # Preparar dados para PDF
        order_data = {
            'ordem_id': ordem['id'],
            'tipo_documento': ordem.get('tipo_documento'),
            'codigo_orcamento': ordem.get('codigo_orcamento'),
            'cliente_id': ordem['cliente_id'],
            'data_emissao': ordem['data'].strftime("%d/%m/%Y") if ordem['data'] else datetime.now().strftime("%d/%m/%Y"),
            'servicos': [{'id': s['servico_id'], 'nome': s['descricao'], 'qtd': s['qtd'], 
                         'preco_unit': float(s['valor_unit']), 'total': float(s['valor_total']),
                         'local': s.get('local') or None,
                         'data': s.get('data').strftime('%Y-%m-%d') if s.get('data') else None} 
                        for s in servicos],
            'materiais': [{'id': m['material_id'], 'nome': m['descricao'].split(' - ')[0] if ' - ' in m['descricao'] else m['descricao'],
                          'marca': m['descricao'].split(' - ')[1] if ' - ' in m['descricao'] and len(m['descricao'].split(' - ')) > 1 else '',
                          'qtd': m['qtd'], 'preco_unit': float(m['valor_unit']), 'total': float(m['valor_total']),
                          'data': m.get('data').strftime('%d/%m/%Y') if m.get('data') else None} 
                         for m in materiais],
            'adicionais': [{'tipo': a['tipo'], 'descricao': a['descricao'], 'valor': float(a['valor'])} 
                          for a in adicionais],
            'distance_data': {'distance_km': float(ordem['km'] or 0), 
                            'displacement_cost': float(ordem['valor_deslocamento'] or 0)},
            'forma_pagamento_id': ordem['forma_pagamento_id']
        }
        
        if ordem['assinatura_nome']:
            order_data['assinatura'] = {
                'nome': ordem['assinatura_nome']
            }
        
        pdf_path = pdf_generator.generate_pdf(order_data)
        if ordem.get('tipo_documento') == 'ORC':
            numero_doc = ordem.get('codigo_orcamento') or ordem['id']
            download_name = f"Orcamento_{numero_doc}.pdf"
        else:
            download_name = f"OrdemDeServico_{id}.pdf"

        return send_file(pdf_path, as_attachment=True, 
                        download_name=download_name, mimetype='application/pdf')
        
    except Exception as e:
        flash(f'Erro ao gerar PDF: {e}', 'danger')
        return redirect(url_for('ordens.listar'))

@bp.route('/alterar_status/<int:id>', methods=['POST'])
@login_required
def alterar_status(id):
    """Alterar status da ordem"""
    try:
        novo_status = request.form.get('status', '').strip()
        tipo_pagamento = request.form.get(f'tipo_pagamento_{id}', 'uma')  # 'uma' ou 'todas'

        if not novo_status:
            flash('Status ? obrigat?rio!', 'danger')
            return redirect(url_for('ordens.listar'))

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Buscar dados da ordem
        cursor.execute('''
            SELECT os.*, fp.tipo as forma_pagamento_tipo
            FROM ordens_servico os
            LEFT JOIN formas_pagamento fp ON os.forma_pagamento_id = fp.id
            WHERE os.id = %s
        ''', (id,))
        ordem = cursor.fetchone()

        if not ordem:
            flash('Ordem n?o encontrada!', 'danger')
            conn.close()
            return redirect(url_for('ordens.listar'))

        # Se est? marcando como "Paga" e a forma de pagamento ? parcelada
        if novo_status == 'Paga' and ordem['forma_pagamento_tipo'] == 'Parcelado' and ordem['parcelas'] and ordem['parcelas'] > 1:
            # Verificar quantas parcelas j? foram pagas
            cursor.execute('SELECT COUNT(*) as total FROM parcelas_pagas WHERE ordem_id = %s', (id,))
            parcelas_pagas_count = cursor.fetchone()['total']

            # Se todas as parcelas j? foram pagas, marcar como totalmente paga
            if parcelas_pagas_count >= ordem['parcelas']:
                cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', (novo_status, id))
                _sincronizar_cobranca_mensal_por_ordens(cursor, ordem['cliente_id'], ordem['data'])
                conn.commit()
                flash('Status atualizado com sucesso! (Todas as parcelas j? foram pagas)', 'success')
            else:
                valor_parcela = ordem['total'] / ordem['parcelas']
                parcelas_restantes = ordem['parcelas'] - parcelas_pagas_count

                if tipo_pagamento == 'todas':
                    # Marcar todas as parcelas restantes
                    for num_parcela in range(parcelas_pagas_count + 1, ordem['parcelas'] + 1):
                        # Calcular data de vencimento (30 dias por parcela a partir da data da ordem)
                        data_vencimento = ordem['data'] + timedelta(days=30 * num_parcela)
                        cursor.execute('''
                            INSERT INTO parcelas_pagas (ordem_id, numero_parcela, valor_parcela, data_pagamento, data_vencimento)
                            VALUES (%s, %s, %s, CURRENT_DATE, %s)
                            ON CONFLICT (ordem_id, numero_parcela) DO NOTHING
                        ''', (id, num_parcela, valor_parcela, data_vencimento))

                    cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', (novo_status, id))
                    _sincronizar_cobranca_mensal_por_ordens(cursor, ordem['cliente_id'], ordem['data'])
                    flash(f'Todas as {parcelas_restantes} parcelas restantes foram registradas! Ordem totalmente paga.', 'success')
                else:
                    # Marcar apenas uma parcela
                    numero_parcela = parcelas_pagas_count + 1
                    data_vencimento = ordem['data'] + timedelta(days=30 * numero_parcela)

                    cursor.execute('''
                        INSERT INTO parcelas_pagas (ordem_id, numero_parcela, valor_parcela, data_pagamento, data_vencimento)
                        VALUES (%s, %s, %s, CURRENT_DATE, %s)
                        ON CONFLICT (ordem_id, numero_parcela) DO NOTHING
                    ''', (id, numero_parcela, valor_parcela, data_vencimento))

                    # Verificar se todas as parcelas foram pagas agora
                    cursor.execute('SELECT COUNT(*) as total FROM parcelas_pagas WHERE ordem_id = %s', (id,))
                    parcelas_pagas_count = cursor.fetchone()['total']

                    if parcelas_pagas_count >= ordem['parcelas']:
                        cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', (novo_status, id))
                        _sincronizar_cobranca_mensal_por_ordens(cursor, ordem['cliente_id'], ordem['data'])
                        flash(f'Parcela {numero_parcela}/{ordem["parcelas"]} registrada! Ordem totalmente paga.', 'success')
                    else:
                        cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', ('Aguardando Pagamento', id))
                        _sincronizar_cobranca_mensal_por_ordens(cursor, ordem['cliente_id'], ordem['data'])
                        flash(f'Parcela {numero_parcela}/{ordem["parcelas"]} registrada! Ainda h? parcelas pendentes.', 'info')

                conn.commit()
        else:
            # Para formas de pagamento n?o parceladas ou quando n?o ? para marcar como "Paga"
            cursor.execute('UPDATE ordens_servico SET status = %s WHERE id = %s', (novo_status, id))
            _sincronizar_cobranca_mensal_por_ordens(cursor, ordem['cliente_id'], ordem['data'])
            conn.commit()
            flash('Status atualizado com sucesso!', 'success')

        conn.close()
    except Exception as e:
        flash(f'Erro ao atualizar status: {e}', 'danger')

    return redirect(url_for('ordens.listar'))


@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir ordem de serviÃ§o"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Excluir itens relacionados primeiro
        cursor.execute('DELETE FROM itens_servico WHERE ordem_id = %s', (id,))
        cursor.execute('DELETE FROM itens_material WHERE ordem_id = %s', (id,))
        cursor.execute('DELETE FROM adicionais WHERE ordem_id = %s', (id,))
        
        # Excluir a ordem
        cursor.execute('DELETE FROM ordens_servico WHERE id = %s', (id,))
        
        conn.commit()
        conn.close()
        
        flash('Ordem de serviÃ§o excluÃ­da com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir ordem: {e}', 'danger')
    
    return redirect(url_for('ordens.listar'))

