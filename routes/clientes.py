from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from database_web import get_db_connection
from decorators import login_required
from pdf_generator import OrderPDFGenerator
import psycopg2.extras
import re
from datetime import datetime, timedelta

bp = Blueprint('clientes', __name__, url_prefix='/clientes')


def _upsert_cobranca_mensal_relatorio(cursor, cliente_id: int, mes: int, ano: int, total_bruto: float):
    cursor.execute('''
        INSERT INTO cobrancas_mensais (cliente_id, mes, ano, total_bruto, total_liquido)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (cliente_id, mes, ano) DO UPDATE
        SET total_bruto = EXCLUDED.total_bruto,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    ''', (cliente_id, mes, ano, total_bruto, total_bruto))
    return cursor.fetchone()[0]

def formatar_cpf_cnpj(value):
    """Formata CPF ou CNPJ"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 11:  # CPF
        return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"
    elif len(digits) == 14:  # CNPJ
        return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"
    else:
        return value  # Retorna sem formatação se não for CPF nem CNPJ

def formatar_telefone(value):
    """Formata telefone"""
    if not value:
        return ''
    # Remove caracteres não numéricos
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) == 10:  # Telefone fixo
        return f"({digits[0:2]}) {digits[2:6]}-{digits[6:10]}"
    elif len(digits) == 11:  # Celular
        return f"({digits[0:2]}) {digits[2:7]}-{digits[7:11]}"
    else:
        return value  # Retorna sem formatação se não tiver 10 ou 11 dígitos

@bp.route('/')
@login_required
def listar():
    """Listar todos os clientes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Adicionar coluna ativo se não existir (migração)
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='clientes' AND column_name='ativo'
                    ) THEN
                        ALTER TABLE clientes ADD COLUMN ativo BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna ativo: {e}")
        
        search = request.args.get('search', '')
        query = "SELECT * FROM clientes"
        params = []
        
        if search:
            query += " WHERE (nome ILIKE %s OR cnpj_cpf ILIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY nome"
        cursor.execute(query, params)
        clientes = cursor.fetchall()
        conn.close()
        
        # Adicionar funções de formatação ao contexto do template
        return render_template('clientes/listar.html', 
                             clientes=clientes, 
                             search=search,
                             formatar_cpf_cnpj=formatar_cpf_cnpj,
                             formatar_telefone=formatar_telefone)
    except Exception as e:
        flash(f'Erro ao carregar clientes: {e}', 'danger')
        return render_template('clientes/listar.html', clientes=[], search='')

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    """Criar novo cliente"""
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        # Remover formatação do CNPJ/CPF e telefone
        cnpj_cpf = re.sub(r'\D', '', request.form.get('cnpj_cpf', '').strip())
        endereco = request.form.get('endereco', '').strip()
        telefone = re.sub(r'\D', '', request.form.get('telefone', '').strip())
        email = request.form.get('email', '').strip()
        
        if not nome:
            flash('Nome é obrigatório!', 'danger')
            return render_template('clientes/form.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Verificar CNPJ/CPF único
            if cnpj_cpf:
                cursor.execute('SELECT id FROM clientes WHERE cnpj_cpf = %s', (cnpj_cpf,))
                if cursor.fetchone():
                    flash('CNPJ/CPF já cadastrado!', 'danger')
                    conn.close()
                    return render_template('clientes/form.html', 
                                         nome=nome, cnpj_cpf=cnpj_cpf, endereco=endereco,
                                         telefone=telefone, email=email)
            
            cursor.execute('''
                INSERT INTO clientes (nome, cnpj_cpf, endereco, telefone, email)
                VALUES (%s, %s, %s, %s, %s)
            ''', (nome, cnpj_cpf or None, endereco or None, telefone or None, email or None))
            
            conn.commit()
            conn.close()
            
            flash('Cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('clientes.listar'))
            
        except Exception as e:
            flash(f'Erro ao cadastrar cliente: {e}', 'danger')
    
    return render_template('clientes/form.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            # Remover formatação do CNPJ/CPF e telefone
            cnpj_cpf = re.sub(r'\D', '', request.form.get('cnpj_cpf', '').strip())
            endereco = request.form.get('endereco', '').strip()
            telefone = re.sub(r'\D', '', request.form.get('telefone', '').strip())
            email = request.form.get('email', '').strip()
            
            if not nome:
                flash('Nome é obrigatório!', 'danger')
                return redirect(url_for('clientes.editar', id=id))
            
            # Verificar CNPJ/CPF único (exceto para o próprio cliente)
            if cnpj_cpf:
                cursor.execute('SELECT id FROM clientes WHERE cnpj_cpf = %s AND id != %s', (cnpj_cpf, id))
                if cursor.fetchone():
                    flash('CNPJ/CPF já cadastrado para outro cliente!', 'danger')
                    conn.close()
                    return redirect(url_for('clientes.editar', id=id))
            
            cursor.execute('''
                UPDATE clientes 
                SET nome = %s, cnpj_cpf = %s, endereco = %s, telefone = %s, email = %s
                WHERE id = %s
            ''', (nome, cnpj_cpf or None, endereco or None, telefone or None, email or None, id))
            
            conn.commit()
            conn.close()
            
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('clientes.listar'))
        
        # GET - carregar dados do cliente
        cursor.execute('SELECT * FROM clientes WHERE id = %s', (id,))
        cliente = cursor.fetchone()
        conn.close()
        
        if not cliente:
            flash('Cliente não encontrado!', 'danger')
            return redirect(url_for('clientes.listar'))
        
        return render_template('clientes/form.html', cliente=cliente)
        
    except Exception as e:
        flash(f'Erro ao editar cliente: {e}', 'danger')
        return redirect(url_for('clientes.listar'))

@bp.route('/excluir/<int:id>', methods=['POST'])
@login_required
def excluir(id):
    """Excluir cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verificar se tem ordens de serviço
        cursor.execute('SELECT COUNT(*) FROM ordens_servico WHERE cliente_id = %s', (id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            flash(f'Não é possível excluir o cliente pois ele possui {count} ordem(ns) de serviço associada(s). Use o botão de inativar para ocultá-lo de novas ordens.', 'warning')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        cursor.execute('DELETE FROM clientes WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        flash('Cliente excluído com sucesso!', 'success')
        
    except Exception as e:
        flash(f'Erro ao excluir cliente: {e}', 'danger')
    
    return redirect(url_for('clientes.listar'))

@bp.route('/toggle_ativo/<int:id>', methods=['POST'])
@login_required
def toggle_ativo(id):
    """Alterna o status ativo/inativo de um cliente"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Adicionar coluna ativo se não existir (migração)
        try:
            cursor.execute('''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='clientes' AND column_name='ativo'
                    ) THEN
                        ALTER TABLE clientes ADD COLUMN ativo BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            ''')
            conn.commit()
        except Exception as e:
            print(f"Erro ao adicionar coluna ativo: {e}")
        
        cursor.execute("SELECT ativo FROM clientes WHERE id = %s", (id,))
        result = cursor.fetchone()
        if result:
            novo_status = not result[0]
            cursor.execute("UPDATE clientes SET ativo = %s WHERE id = %s", (novo_status, id))
            conn.commit()
            flash(f'Cliente {"ativado" if novo_status else "desativado"} com sucesso!', 'success')
        conn.close()
    except Exception as e:
        flash(f'Erro ao alterar status: {e}', 'danger')
    return redirect(url_for('clientes.listar'))

@bp.route('/api/buscar')
@login_required
def api_buscar():
    """API para buscar clientes (usado em autocomplete)"""
    try:
        search = request.args.get('q', '')
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        if search:
            search_pattern_start = f'{search}%'
            search_pattern_any = f'%{search}%'
            cursor.execute('''
                SELECT id, nome FROM clientes 
                WHERE ativo = true AND (nome ILIKE %s OR cnpj_cpf ILIKE %s)
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        WHEN nome ILIKE %s THEN 2
                        ELSE 3
                    END,
                    nome
            ''', (search_pattern_any, search_pattern_any, search_pattern_start, search_pattern_any))
        else:
            cursor.execute('SELECT id, nome FROM clientes WHERE ativo = true ORDER BY nome')
        
        clientes = cursor.fetchall()
        conn.close()
        
        results = [{'id': c['id'], 'nome': c['nome']} for c in clientes]
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/selecionar_mes_relatorio/<int:id>', methods=['GET', 'POST'])
@login_required
def selecionar_mes_relatorio(id):
    """Página para selecionar o mês do relatório"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar dados do cliente
        cursor.execute('SELECT * FROM clientes WHERE id = %s', (id,))
        cliente = cursor.fetchone()
        cursor.execute('SELECT id, nome, tipo FROM formas_pagamento ORDER BY nome')
        formas_pagamento = cursor.fetchall()
        
        if not cliente:
            conn.close()
            flash('Cliente não encontrado!', 'danger')
            return redirect(url_for('clientes.listar'))
        
        if request.method == 'POST':
            data_inicio = (request.form.get('data_inicio') or '').strip()
            data_fim = (request.form.get('data_fim') or '').strip()
            forma_pagamento_id = request.form.get('forma_pagamento_id', type=int)
            parcelas = request.form.get('parcelas', type=int) or 1
            data_pagamento = (request.form.get('data_pagamento') or '').strip()
            data_primeira_parcela = (request.form.get('data_primeira_parcela') or '').strip()
            desconto_tipo = (request.form.get('desconto_tipo') or '').strip()
            desconto_valor = (request.form.get('desconto_valor') or '0').strip()

            if not data_inicio or not data_fim:
                conn.close()
                flash('Informe um período válido para gerar o relatório.', 'danger')
                return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))

            if not forma_pagamento_id:
                conn.close()
                flash('Informe a forma de pagamento antes de emitir o PDF.', 'danger')
                return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))

            cursor.execute('SELECT id, tipo FROM formas_pagamento WHERE id = %s', (forma_pagamento_id,))
            forma_pagamento = cursor.fetchone()
            if not forma_pagamento:
                conn.close()
                flash('Forma de pagamento inválida.', 'danger')
                return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))

            eh_parcelado = (forma_pagamento.get('tipo') or '') == 'Parcelado' and parcelas > 1
            if eh_parcelado and not data_primeira_parcela:
                conn.close()
                flash('Informe a data da primeira parcela.', 'danger')
                return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))
            if not eh_parcelado and not data_pagamento:
                conn.close()
                flash('Informe a data do pagamento.', 'danger')
                return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))

            conn.close()
            return redirect(url_for(
                'clientes.relatorio_mensal',
                id=id,
                data_inicio=data_inicio,
                data_fim=data_fim,
                forma_pagamento_id=forma_pagamento_id,
                parcelas=parcelas,
                data_pagamento=data_pagamento or None,
                data_primeira_parcela=data_primeira_parcela or None,
                desconto_tipo=desconto_tipo or None,
                desconto_valor=desconto_valor
            ))
        
        # GET - mostrar formulário de seleção
        hoje = datetime.now()
        conn.close()
        return render_template('clientes/selecionar_mes_relatorio.html', 
                             cliente=cliente, 
                             formas_pagamento=formas_pagamento,
                             mes_atual=hoje.month, 
                             ano_atual=hoje.year)
        
    except Exception as e:
        flash(f'Erro: {e}', 'danger')
        return redirect(url_for('clientes.listar'))

@bp.route('/relatorio_mensal/<int:id>')
@login_required
def relatorio_mensal(id):
    """Gerar relatório mensal consolidado do cliente"""
    try:
        mes = request.args.get('mes', type=int)
        ano = request.args.get('ano', type=int)
        data_inicio_raw = (request.args.get('data_inicio', '') or '').strip()
        data_fim_raw = (request.args.get('data_fim', '') or '').strip()
        forma_pagamento_id_arg = request.args.get('forma_pagamento_id', type=int)
        parcelas_arg = request.args.get('parcelas', type=int) or 1
        data_pagamento_arg = (request.args.get('data_pagamento', '') or '').strip()
        data_primeira_parcela_arg = (request.args.get('data_primeira_parcela', '') or '').strip()
        desconto_tipo_arg = (request.args.get('desconto_tipo', '') or '').strip()
        desconto_valor_arg = float(request.args.get('desconto_valor', type=float) or 0)

        primeiro_dia_mes = None
        ultimo_dia_mes = None

        if data_inicio_raw and data_fim_raw:
            try:
                primeiro_dia_mes = datetime.strptime(data_inicio_raw, '%Y-%m-%d').date()
                ultimo_dia_mes = datetime.strptime(data_fim_raw, '%Y-%m-%d').date()
            except Exception:
                flash('Período inválido para gerar o relatório!', 'danger')
                return redirect(url_for('clientes.listar'))
        elif mes and ano:
            primeiro_dia_mes = datetime(ano, mes, 1).date()
            if mes == 12:
                ultimo_dia_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
            else:
                ultimo_dia_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)
        else:
            flash('Mês/ano ou período são obrigatórios!', 'danger')
            return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))

        if primeiro_dia_mes > ultimo_dia_mes:
            primeiro_dia_mes, ultimo_dia_mes = ultimo_dia_mes, primeiro_dia_mes
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar dados do cliente
        cursor.execute('SELECT * FROM clientes WHERE id = %s', (id,))
        cliente = cursor.fetchone()
        
        if not cliente:
            flash('Cliente não encontrado!', 'danger')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        cursor.execute('''
            SELECT id, data, total, status, valor_deslocamento, km
            FROM ordens_servico 
            WHERE cliente_id = %s 
            AND data >= %s
            AND data <= %s
            ORDER BY data, id
        ''', (id, primeiro_dia_mes, ultimo_dia_mes))
        ordens = cursor.fetchall()
        
        if not ordens:
            flash(f'Nenhuma ordem de serviço encontrada para este cliente entre {primeiro_dia_mes.strftime("%d/%m/%Y")} e {ultimo_dia_mes.strftime("%d/%m/%Y")}!', 'warning')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        # Coletar todos os IDs das ordens
        ordem_ids = [ordem['id'] for ordem in ordens]
        numeros_os = [str(ordem['id']) for ordem in ordens]
        
        # Buscar todos os serviços de todas as ordens
        cursor.execute('''
            SELECT is_.*, os.id as ordem_id
            FROM itens_servico is_
            JOIN ordens_servico os ON is_.ordem_id = os.id
            WHERE is_.ordem_id = ANY(%s)
            ORDER BY is_.local, is_.data, is_.ordem_id
        ''', (ordem_ids,))
        servicos = cursor.fetchall()
        
        # Buscar todos os materiais de todas as ordens
        cursor.execute('''
            SELECT im.*, os.id as ordem_id
            FROM itens_material im
            JOIN ordens_servico os ON im.ordem_id = os.id
            WHERE im.ordem_id = ANY(%s)
            ORDER BY im.ordem_id
        ''', (ordem_ids,))
        materiais = cursor.fetchall()
        
        # Buscar adicionais (impostos, BDI, descontos)
        cursor.execute('''
            SELECT a.*, os.id as ordem_id
            FROM adicionais a
            JOIN ordens_servico os ON a.ordem_id = os.id
            WHERE a.ordem_id = ANY(%s)
        ''', (ordem_ids,))
        adicionais = cursor.fetchall()
        
        # Preparar dados de frete/deslocamento
        fretes_deslocamentos = []
        for ordem in ordens:
            valor_deslocamento = float(ordem.get('valor_deslocamento', 0) or 0)
            if valor_deslocamento > 0:
                fretes_deslocamentos.append({
                    'data': ordem['data'].strftime('%d/%m/%Y') if ordem.get('data') else '',
                    'km': float(ordem.get('km', 0) or 0),
                    'valor': valor_deslocamento,
                    'ordem_id': ordem['id']
                })
        
        # Calcular totais
        total_servicos = sum(float(s['valor_total']) for s in servicos)
        total_materiais = sum(float(m['valor_total']) for m in materiais)
        total_deslocamento = sum(float(ordem.get('valor_deslocamento', 0) or 0) for ordem in ordens)
        total_impostos = sum(float(a['valor']) for a in adicionais if a['tipo'] == 'imposto')
        total_bdi = sum(float(a['valor']) for a in adicionais if a['tipo'] == 'bdi')
        total_descontos = sum(float(a['valor']) for a in adicionais if a['tipo'] == 'desconto')
        total_geral = total_servicos + total_materiais + total_deslocamento + total_impostos + total_bdi - total_descontos

        pagamento = {}
        desconto_mensal_tipo = None
        desconto_mensal_valor = 0.0
        desconto_mensal_percentual = 0.0
        configuracao_persistida_por_args = False

        mes_cobranca = None
        ano_cobranca = None
        if primeiro_dia_mes.month == ultimo_dia_mes.month and primeiro_dia_mes.year == ultimo_dia_mes.year:
            mes_cobranca = primeiro_dia_mes.month
            ano_cobranca = primeiro_dia_mes.year
        elif mes and ano:
            mes_cobranca = mes
            ano_cobranca = ano

        if mes_cobranca and ano_cobranca:
            if forma_pagamento_id_arg:
                cobranca_id = _upsert_cobranca_mensal_relatorio(cursor, id, mes_cobranca, ano_cobranca, total_geral)
                cursor.execute('SELECT * FROM cobrancas_mensais WHERE id = %s', (cobranca_id,))
                cobranca_atual = cursor.fetchone()
                status_persist = (cobranca_atual.get('status') if cobranca_atual else '') or 'Aguardando Pagamento'
                cursor.execute('SELECT id, nome, tipo FROM formas_pagamento WHERE id = %s', (forma_pagamento_id_arg,))
                forma_pagamento = cursor.fetchone()

                if forma_pagamento:
                    desconto_percentual_persist = 0.0
                    desconto_valor_final_persist = 0.0
                    desconto_tipo_persist = desconto_tipo_arg or None

                    if desconto_tipo_persist == 'percentual':
                        desconto_percentual_persist = max(0.0, min(100.0, desconto_valor_arg))
                        desconto_valor_final_persist = (total_geral * desconto_percentual_persist) / 100.0
                    elif desconto_tipo_persist == 'fixo':
                        desconto_valor_final_persist = max(0.0, desconto_valor_arg)
                    else:
                        desconto_tipo_persist = None

                    total_liquido_persist = max(total_geral - desconto_valor_final_persist, 0.0)
                    eh_parcelado = (forma_pagamento.get('tipo') or '') == 'Parcelado' and parcelas_arg > 1

                    cursor.execute('DELETE FROM cobrancas_mensais_parcelas WHERE cobranca_id = %s', (cobranca_id,))

                    if eh_parcelado:
                        for numero_parcela in range(1, parcelas_arg + 1):
                            vencimento = datetime.strptime(data_primeira_parcela_arg, '%Y-%m-%d').date() + timedelta(days=30 * (numero_parcela - 1))
                            data_pagamento_parcela = vencimento if status_persist == 'Paga' else None
                            cursor.execute('''
                                INSERT INTO cobrancas_mensais_parcelas (cobranca_id, numero_parcela, valor_parcela, data_vencimento, data_pagamento)
                                VALUES (%s, %s, %s, %s, %s)
                            ''', (cobranca_id, numero_parcela, total_liquido_persist / parcelas_arg, vencimento, data_pagamento_parcela))
                        data_pagamento_persist = None
                        data_primeira_persist = datetime.strptime(data_primeira_parcela_arg, '%Y-%m-%d').date() if data_primeira_parcela_arg else None
                    else:
                        data_pagamento_persist = datetime.strptime(data_pagamento_arg, '%Y-%m-%d').date() if data_pagamento_arg else None
                        data_primeira_persist = None
                        data_pagamento_parcela = data_pagamento_persist if status_persist == 'Paga' else None
                        if data_pagamento_persist:
                            cursor.execute('''
                                INSERT INTO cobrancas_mensais_parcelas (cobranca_id, numero_parcela, valor_parcela, data_vencimento, data_pagamento)
                                VALUES (%s, 1, %s, %s, %s)
                            ''', (cobranca_id, total_liquido_persist, data_pagamento_persist, data_pagamento_parcela))

                    cursor.execute('''
                        UPDATE cobrancas_mensais
                        SET forma_pagamento_id = %s,
                            parcelas = %s,
                            data_pagamento = %s,
                            data_primeira_parcela = %s,
                            status = %s,
                            desconto_tipo = %s,
                            desconto_valor = %s,
                            desconto_percentual = %s,
                            total_bruto = %s,
                            total_liquido = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (
                        forma_pagamento_id_arg,
                        parcelas_arg if eh_parcelado else 1,
                        data_pagamento_persist,
                        data_primeira_persist,
                        status_persist,
                        desconto_tipo_persist,
                        desconto_valor_final_persist,
                        desconto_percentual_persist,
                        total_geral,
                        total_liquido_persist,
                        cobranca_id
                    ))
                    conn.commit()
                    configuracao_persistida_por_args = True

            cursor.execute('''
                SELECT cm.*, fp.nome AS forma_pagamento_nome, fp.tipo AS forma_pagamento_tipo
                FROM cobrancas_mensais cm
                LEFT JOIN formas_pagamento fp ON fp.id = cm.forma_pagamento_id
                WHERE cm.cliente_id = %s AND cm.mes = %s AND cm.ano = %s
            ''', (id, mes_cobranca, ano_cobranca))
            cobranca_mensal = cursor.fetchone()

            if cobranca_mensal:
                desconto_mensal_tipo = (cobranca_mensal.get('desconto_tipo') or '').strip() or None
                desconto_mensal_valor = float(cobranca_mensal.get('desconto_valor') or 0)
                desconto_mensal_percentual = float(cobranca_mensal.get('desconto_percentual') or 0)
                total_geral = float(cobranca_mensal.get('total_liquido') or total_geral)
                pagamento = {
                    'forma_pagamento_nome': cobranca_mensal.get('forma_pagamento_nome'),
                    'forma_pagamento_tipo': cobranca_mensal.get('forma_pagamento_tipo'),
                    'parcelas': cobranca_mensal.get('parcelas') or 1,
                    'data_pagamento': cobranca_mensal.get('data_pagamento'),
                    'data_primeira_parcela': cobranca_mensal.get('data_primeira_parcela'),
                    'status': cobranca_mensal.get('status')
                }

        if desconto_tipo_arg and not configuracao_persistida_por_args:
            if desconto_tipo_arg == 'percentual':
                desconto_mensal_percentual = max(0.0, min(100.0, desconto_valor_arg))
                desconto_mensal_valor = (total_geral * desconto_mensal_percentual) / 100.0
                desconto_mensal_tipo = 'percentual'
            elif desconto_tipo_arg == 'fixo':
                desconto_mensal_valor = max(0.0, desconto_valor_arg)
                desconto_mensal_percentual = 0.0
                desconto_mensal_tipo = 'fixo'
            else:
                desconto_mensal_tipo = None
                desconto_mensal_valor = 0.0
                desconto_mensal_percentual = 0.0
            total_geral = max(total_geral - desconto_mensal_valor, 0.0)

        if forma_pagamento_id_arg and not configuracao_persistida_por_args:
            cursor.execute('SELECT id, nome, tipo FROM formas_pagamento WHERE id = %s', (forma_pagamento_id_arg,))
            forma_pagamento = cursor.fetchone()
            if forma_pagamento:
                eh_parcelado = (forma_pagamento.get('tipo') or '') == 'Parcelado' and parcelas_arg > 1
                status_pagamento = (pagamento.get('status') if pagamento else '') or 'Aguardando Pagamento'
                pagamento = {
                    'forma_pagamento_nome': forma_pagamento.get('nome'),
                    'forma_pagamento_tipo': forma_pagamento.get('tipo'),
                    'parcelas': parcelas_arg if eh_parcelado else 1,
                    'data_pagamento': data_pagamento_arg or None,
                    'data_primeira_parcela': data_primeira_parcela_arg or None,
                    'status': status_pagamento
                }
        
        conn.close()
        
        # Preparar dados para o PDF
        if data_inicio_raw and data_fim_raw:
            mes_ano_str = f"{primeiro_dia_mes.strftime('%d/%m/%Y')} a {ultimo_dia_mes.strftime('%d/%m/%Y')}"
            nome_periodo = f"{primeiro_dia_mes.strftime('%Y%m%d')}_{ultimo_dia_mes.strftime('%Y%m%d')}"
        else:
            mes_ano_str = f"{mes:02d}/{ano}"
            nome_periodo = f"{mes:02d}_{ano}"
        report_data = {
            'cliente': {
                'id': cliente['id'],
                'nome': cliente['nome'],
                'cnpj_cpf': cliente.get('cnpj_cpf'),
                'inscricao_estadual': cliente.get('inscricao_estadual'),
                'endereco': cliente.get('endereco'),
                'telefone': cliente.get('telefone'),
                'email': cliente.get('email')
            },
            'mes_ano': mes_ano_str,
            'numeros_os': ', '.join(numeros_os),
            'servicos': [{
                'nome': s['descricao'],
                'qtd': s['qtd'],
                'preco_unit': float(s['valor_unit']),
                'total': float(s['valor_total']),
                'local': s.get('local'),
                'data': s.get('data').strftime('%d/%m/%Y') if s.get('data') else None,
                'ordem_id': s['ordem_id']
            } for s in servicos],
            'materiais': [{
                'nome': m['descricao'].split(' - ')[0] if ' - ' in m['descricao'] else m['descricao'],
                'marca': m['descricao'].split(' - ')[1] if ' - ' in m['descricao'] and len(m['descricao'].split(' - ')) > 1 else '',
                'qtd': m['qtd'],
                'preco_unit': float(m['valor_unit']),
                'total': float(m['valor_total']),
                'data': m.get('data').strftime('%d/%m/%Y') if m.get('data') else None,
                'ordem_id': m['ordem_id']
            } for m in materiais],
            'fretes_deslocamentos': fretes_deslocamentos,
            'totais': {
                'servicos': total_servicos,
                'materiais': total_materiais,
                'deslocamento': total_deslocamento,
                'impostos': total_impostos,
                'bdi': total_bdi,
                'descontos': total_descontos,
                'desconto_mensal_tipo': desconto_mensal_tipo,
                'desconto_mensal_valor': desconto_mensal_valor,
                'desconto_mensal_percentual': desconto_mensal_percentual,
                'geral': total_geral
            },
            'pagamento': pagamento
        }
        
        # Gerar PDF
        pdf_generator = OrderPDFGenerator()
        output_path = pdf_generator.generate_relatorio_mensal_cliente(report_data)
        
        return send_file(output_path, as_attachment=True, download_name=f'Relatorio_Mensal_{cliente["nome"]}_{nome_periodo}.pdf')
        
    except Exception as e:
        flash(f'Erro ao gerar relatório: {e}', 'danger')
        print(f"[ERROR] Erro ao gerar relatório mensal: {e}")
        return redirect(url_for('clientes.listar'))
