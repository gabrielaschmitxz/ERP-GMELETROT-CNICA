from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
import hashlib
from datetime import datetime
import os
from config_web import SECRET_KEY, DEBUG, UPLOAD_FOLDER
from database_web import get_db_connection, init_database
import psycopg2.extras
from decorators import login_required, admin_required

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['DEBUG'] = DEBUG
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Criar pasta de uploads se não existir
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Inicializar banco de dados na primeira execução
try:
    init_database()
except Exception as e:
    print(f"⚠️ Erro ao inicializar banco de dados: {e}")
    print("💡 Verifique o arquivo .env e a conexão com o banco de dados")
    # Não interrompe a execução, permite que o servidor inicie mesmo com erro

@app.route('/')
def index():
    """Página inicial - redireciona para login ou dashboard"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/health')
@app.route('/ping')
def health_check():
    """Endpoint de health check para manter a instância ativa"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Por favor, preencha todos os campos!', 'danger')
            return render_template('login.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Hash da senha
            password_hash = hashlib.md5(password.encode()).hexdigest()
            
            # Verificar usuário e senha
            cursor.execute('''
                SELECT id, username, nome, admin, ativo FROM usuarios 
                WHERE username = %s AND senha = %s AND ativo = true
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            conn.close()
            
            if user:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['nome'] = user[2]
                session['admin'] = user[3]
                flash(f'Bem-vindo, {user[2]}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Usuário ou senha inválidos!', 'danger')
                
        except Exception as e:
            flash(f'Erro ao conectar com o banco: {e}', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout do usuário"""
    session.clear()
    flash('Você foi desconectado com sucesso.', 'info')
    return redirect(url_for('login'))

@app.route('/alterar_senha', methods=['GET', 'POST'])
@login_required
def alterar_senha():
    """Alterar senha do usuário logado"""
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual', '').strip()
        senha_nova = request.form.get('senha_nova', '').strip()
        senha_confirmar = request.form.get('senha_confirmar', '').strip()
        
        if not senha_atual or not senha_nova or not senha_confirmar:
            flash('Todos os campos são obrigatórios!', 'danger')
            return render_template('alterar_senha.html')
        
        if senha_nova != senha_confirmar:
            flash('As senhas não coincidem!', 'danger')
            return render_template('alterar_senha.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Verificar senha atual
            senha_atual_hash = hashlib.md5(senha_atual.encode()).hexdigest()
            cursor.execute('''
                SELECT id FROM usuarios 
                WHERE id = %s AND senha = %s
            ''', (session.get('user_id'), senha_atual_hash))
            
            if not cursor.fetchone():
                conn.close()
                flash('Senha atual incorreta!', 'danger')
                return render_template('alterar_senha.html')
            
            # Atualizar senha
            senha_nova_hash = hashlib.md5(senha_nova.encode()).hexdigest()
            cursor.execute('''
                UPDATE usuarios SET senha = %s WHERE id = %s
            ''', (senha_nova_hash, session.get('user_id')))
            
            conn.commit()
            conn.close()
            
            flash('Senha alterada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Erro ao alterar senha: {e}', 'danger')
    
    return render_template('alterar_senha.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Usar DictCursor
        
        # Estatísticas (sem filtro de período por padrão)
        stats = get_dashboard_stats(cursor, None)
        
        conn.close()
        
        return render_template('dashboard.html', stats=stats)
        
    except Exception as e:
        flash(f'Erro ao carregar dashboard: {e}', 'danger')
        print(f"[ERROR] Erro ao carregar dashboard: {e}") # Adicionar log de erro
        return render_template('dashboard.html', stats={'clientes': 0, 'ordens_servico': 0, 'total_faturado': 0,
                                                          'total_frete_deslocamento': 0, 'pagamentos_em_aberto': 0,
                                                          'ticket_medio': 0, 'status_counts': {}})

def get_dashboard_stats(cursor, periodo_dias=None):
    """Função auxiliar para buscar estatísticas do dashboard com filtro opcional de período"""
    from datetime import datetime, timedelta
    
    # Clientes sempre sem filtro de período
    cursor.execute("SELECT COUNT(*) FROM clientes")
    total_clientes = cursor.fetchone()[0]
    
    # Construir filtro de data se período for especificado
    date_filter = ""
    params = []
    if periodo_dias:
        if periodo_dias == 'ano_vigente':
            # Ano vigente (ano atual)
            date_filter = " AND data >= DATE_TRUNC('year', CURRENT_DATE)"
        else:
            # Dias específicos
            try:
                dias = int(periodo_dias)
                data_inicio = (datetime.now() - timedelta(days=dias)).date()
                date_filter = " AND data >= %s"
                params = [data_inicio]
            except:
                pass
    
    # Ordens de serviço com filtro de período
    cursor.execute(f"SELECT COUNT(*) FROM ordens_servico WHERE 1=1 {date_filter}", params)
    total_os = cursor.fetchone()[0]
    
    # Total faturado com filtro de período
    cursor.execute(f"SELECT COALESCE(SUM(total), 0) FROM ordens_servico WHERE status = 'Paga' {date_filter}", params)
    total_faturado = cursor.fetchone()[0] or 0
    
    # Total em Frete/Deslocamento com filtro de período
    cursor.execute(f"SELECT COALESCE(SUM(valor_deslocamento), 0) FROM ordens_servico WHERE 1=1 {date_filter}", params)
    total_frete_deslocamento = cursor.fetchone()[0] or 0
    
    # Pagamentos em Aberto com filtro de período
    cursor.execute(f"SELECT COALESCE(SUM(total), 0) FROM ordens_servico WHERE status = 'Aguardando Pagamento' {date_filter}", params)
    pagamentos_em_aberto = cursor.fetchone()[0] or 0
    
    # Ticket médio por O.S
    if total_os > 0:
        ticket_medio = total_faturado / total_os
    else:
        ticket_medio = 0
    
    # Status de Operação com filtro de período
    cursor.execute(f"SELECT status, COUNT(*) FROM ordens_servico WHERE 1=1 {date_filter} GROUP BY status", params)
    status_counts_raw = cursor.fetchall()
    status_counts = {row[0]: row[1] for row in status_counts_raw} if status_counts_raw else {}
    
    return {
        'clientes': total_clientes,
        'ordens_servico': total_os,
        'total_faturado': float(total_faturado),
        'total_frete_deslocamento': float(total_frete_deslocamento),
        'pagamentos_em_aberto': float(pagamentos_em_aberto),
        'ticket_medio': float(ticket_medio),
        'status_counts': status_counts
    }

@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    """API para buscar estatísticas do dashboard com filtro de período"""
    try:
        periodo = request.args.get('periodo', None)
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        stats = get_dashboard_stats(cursor, periodo)
        
        conn.close()
        
        return jsonify(stats)
        
    except Exception as e:
        print(f"[ERROR] Erro ao buscar estatísticas: {e}")
        return jsonify({'error': str(e)}), 500

# Rota para servir arquivos de upload
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve arquivos de upload"""
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Rota para servir arquivos da pasta assinaturas (legado)
@app.route('/assinaturas/<path:filename>')
def assinatura_file(filename):
    """Serve arquivos da pasta assinaturas"""
    from flask import send_from_directory
    return send_from_directory('assinaturas', filename)

# Rota para servir arquivos da pasta img
@app.route('/img/<path:filename>')
def img_file(filename):
    """Serve arquivos da pasta img"""
    from flask import send_from_directory
    return send_from_directory('img', filename)

# Importar rotas de outros módulos
from routes import clientes, materiais, servicos, ordens, financeiro, usuarios, configuracoes, assinaturas, relatorios

# Registrar blueprints
app.register_blueprint(clientes.bp)
app.register_blueprint(materiais.bp)
app.register_blueprint(servicos.bp)
app.register_blueprint(ordens.bp)
app.register_blueprint(financeiro.bp)
app.register_blueprint(usuarios.bp)
app.register_blueprint(configuracoes.bp)
app.register_blueprint(assinaturas.bp)
app.register_blueprint(relatorios.bp)

if __name__ == '__main__':
    # Para produção no Render, usar a porta da variável de ambiente
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG)
