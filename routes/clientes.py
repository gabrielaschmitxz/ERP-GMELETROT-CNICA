from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from database_web import get_db_connection
from decorators import login_required
from pdf_generator import OrderPDFGenerator
import psycopg2.extras
import re
from datetime import datetime, timedelta

bp = Blueprint('clientes', __name__, url_prefix='/clientes')

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
        
        search = request.args.get('search', '')
        query = "SELECT * FROM clientes"
        params = []
        
        if search:
            query += " WHERE nome ILIKE %s OR cnpj_cpf ILIKE %s"
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
            flash(f'Não é possível excluir o cliente pois ele possui {count} ordem(ns) de serviço associada(s).', 'danger')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        cursor.execute('DELETE FROM clientes WHERE id = %s', (id,))
        conn.commit()
        conn.close()
        
        flash('Cliente excluído com sucesso!', 'success')
        
    except Exception as e:
        flash(f'Erro ao excluir cliente: {e}', 'danger')
    
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
                WHERE nome ILIKE %s OR cnpj_cpf ILIKE %s
                ORDER BY 
                    CASE 
                        WHEN nome ILIKE %s THEN 1
                        WHEN nome ILIKE %s THEN 2
                        ELSE 3
                    END,
                    nome
            ''', (search_pattern_any, search_pattern_any, search_pattern_start, search_pattern_any))
        else:
            cursor.execute('SELECT id, nome FROM clientes ORDER BY nome')
        
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
        conn.close()
        
        if not cliente:
            flash('Cliente não encontrado!', 'danger')
            return redirect(url_for('clientes.listar'))
        
        if request.method == 'POST':
            # Redirecionar para gerar o relatório com o mês selecionado
            mes = request.form.get('mes')
            ano = request.form.get('ano')
            return redirect(url_for('clientes.relatorio_mensal', id=id, mes=mes, ano=ano))
        
        # GET - mostrar formulário de seleção
        hoje = datetime.now()
        return render_template('clientes/selecionar_mes_relatorio.html', 
                             cliente=cliente, 
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
        # Obter mês e ano dos parâmetros da URL
        mes = request.args.get('mes', type=int)
        ano = request.args.get('ano', type=int)
        
        if not mes or not ano:
            flash('Mês e ano são obrigatórios!', 'danger')
            return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Buscar dados do cliente
        cursor.execute('SELECT * FROM clientes WHERE id = %s', (id,))
        cliente = cursor.fetchone()
        
        if not cliente:
            flash('Cliente não encontrado!', 'danger')
            conn.close()
            return redirect(url_for('clientes.listar'))
        
        # Buscar todas as ordens do cliente no mês selecionado
        primeiro_dia_mes = datetime(ano, mes, 1).date()
        # Calcular último dia do mês
        if mes == 12:
            ultimo_dia_mes = datetime(ano + 1, 1, 1).date() - timedelta(days=1)
        else:
            ultimo_dia_mes = datetime(ano, mes + 1, 1).date() - timedelta(days=1)
        
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
            flash(f'Nenhuma ordem de serviço encontrada para este cliente em {mes:02d}/{ano}!', 'warning')
            conn.close()
            return redirect(url_for('clientes.selecionar_mes_relatorio', id=id))
        
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
        
        conn.close()
        
        # Preparar dados para o PDF
        mes_ano_str = f"{mes:02d}/{ano}"
        report_data = {
            'cliente': {
                'id': cliente['id'],
                'nome': cliente['nome'],
                'cnpj_cpf': cliente.get('cnpj_cpf'),
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
                'geral': total_geral
            }
        }
        
        # Gerar PDF
        pdf_generator = OrderPDFGenerator()
        output_path = pdf_generator.generate_relatorio_mensal_cliente(report_data)
        
        return send_file(output_path, as_attachment=True, download_name=f'Relatorio_Mensal_{cliente["nome"]}_{mes:02d}_{ano}.pdf')
        
    except Exception as e:
        flash(f'Erro ao gerar relatório: {e}', 'danger')
        print(f"[ERROR] Erro ao gerar relatório mensal: {e}")
        return redirect(url_for('clientes.listar'))
