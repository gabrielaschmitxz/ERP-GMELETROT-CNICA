import psycopg2
import psycopg2.extras
import os
from config_web import DATABASE_URL_WEB

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados PostgreSQL WEB"""
    # Validar URL antes de tentar conectar
    if not DATABASE_URL_WEB or not isinstance(DATABASE_URL_WEB, str):
        raise ValueError("DATABASE_URL_WEB não está definido ou é inválido")
    
    if not DATABASE_URL_WEB.startswith('postgresql://'):
        raise ValueError(f"URL do banco inválida. Deve começar com 'postgresql://'. URL recebida: {DATABASE_URL_WEB[:50]}...")
    
    try:
        conn = psycopg2.connect(DATABASE_URL_WEB)
        return conn
    except psycopg2.OperationalError as e:
        error_msg = str(e)
        # Se o banco não existir, tenta criar
        if "does not exist" in error_msg:
            create_database_if_not_exists()
            conn = psycopg2.connect(DATABASE_URL_WEB)
            return conn
        # Se for erro de DNS/hostname
        elif "could not translate host name" in error_msg or "Name or service not known" in error_msg:
            print(f"\n❌ ERRO: URL do banco de dados está malformada!")
            print(f"📝 URL recebida: {DATABASE_URL_WEB}")
            print(f"\n💡 SOLUÇÃO:")
            print(f"   1. Execute: python corrigir_url_banco.py")
            print(f"   2. Ou edite o arquivo .env manualmente")
            print(f"   3. A URL deve estar no formato:")
            print(f"      postgresql://usuario:senha@host:porta/banco?parametros")
            print(f"\n📝 Exemplo correto:")
            print(f"   DATABASE_URL_WEB=postgresql://neondb_owner:npg_Uuz1QgFncm7j@ep-delicate-salad-ad4ui52h-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
        raise

def create_database_if_not_exists():
    """Cria o banco de dados se não existir"""
    try:
        # Extrair informações da URL de conexão
        # Formato: postgresql://user:pass@host:port/dbname
        from urllib.parse import urlparse
        parsed = urlparse(DATABASE_URL_WEB)
        
        # Conectar ao banco 'postgres' padrão para criar o novo banco
        admin_url = DATABASE_URL_WEB.rsplit('/', 1)[0] + '/postgres'
        
        try:
            admin_conn = psycopg2.connect(admin_url)
            admin_conn.autocommit = True
            admin_cursor = admin_conn.cursor()
            
            # Nome do banco que queremos criar
            db_name = parsed.path.lstrip('/').split('?')[0]  # Remove / e query params
            
            # Verificar se o banco já existe
            admin_cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = admin_cursor.fetchone()
            
            if not exists:
                # Criar o banco
                admin_cursor.execute(f'CREATE DATABASE "{db_name}"')
                print(f"✅ Banco de dados '{db_name}' criado com sucesso!")
            
            admin_cursor.close()
            admin_conn.close()
        except Exception as admin_error:
            # Se não conseguir conectar ao postgres, tenta usar o banco padrão
            print(f"⚠️ Não foi possível criar o banco automaticamente: {admin_error}")
            print(f"💡 Tente criar o banco '{db_name}' manualmente no servidor PostgreSQL")
            # Tenta usar o banco padrão (neondb) como fallback
            fallback_url = DATABASE_URL_WEB.replace('/neondb_web', '/neondb')
            print(f"💡 Ou altere DATABASE_URL_WEB no .env para: {fallback_url}")
    except Exception as e:
        print(f"⚠️ Erro ao criar banco: {e}")

def init_database():
    """Inicializa o banco de dados WEB criando todas as tabelas necessárias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco de dados: {e}")
        print("💡 Verifique se o DATABASE_URL_WEB no arquivo .env está correto")
        raise
    
    # Tabela de clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            cnpj_cpf VARCHAR(20) UNIQUE,
            endereco TEXT,
            telefone VARCHAR(20),
            email VARCHAR(255)
        )
    ''')
    
    # Tabela de materiais
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materiais (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            marca VARCHAR(100),
            quantidade INTEGER DEFAULT 0,
            preco_unit DECIMAL(10,2) DEFAULT 0.0,
            data DATE
        )
    ''')
    
    # Migração: adicionar coluna 'data' se não existir
    cursor.execute('''
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'materiais' AND column_name = 'data'
            ) THEN
                ALTER TABLE materiais ADD COLUMN data DATE;
            END IF;
        END $$;
    ''')
    
    # Tabela de serviços
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servicos (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            preco_unit DECIMAL(10,2) DEFAULT 0.0,
            tempo_h DECIMAL(5,2) DEFAULT 0.0
        )
    ''')
    
    # Tabela de formas de pagamento
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS formas_pagamento (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(100) NOT NULL,
            tipo VARCHAR(50) NOT NULL,
            parcelas_max INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de impostos e BDI
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS impostos_bdi (
            id SERIAL PRIMARY KEY,
            tipo VARCHAR(50) NOT NULL,
            descricao VARCHAR(255) NOT NULL,
            valor DECIMAL(10,2) DEFAULT 0.0
        )
    ''')
    
    # Tabela de assinaturas (criar antes de ordens_servico para foreign key)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assinaturas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL UNIQUE, -- Adicionado UNIQUE
            cargo VARCHAR(255) DEFAULT 'Técnico Eletricista Industrial/Residencial',
            caminho_imagem TEXT, -- Alterado para TEXT (não necessariamente NOT NULL se for opcional)
            ativo BOOLEAN DEFAULT true,
            padrao BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Adicionar coluna cargo se não existir (para bancos já existentes)
    cursor.execute('''
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='assinaturas' AND column_name='cargo'
            ) THEN
                ALTER TABLE assinaturas ADD COLUMN cargo VARCHAR(255) DEFAULT 'Técnico Eletricista Industrial/Residencial';
            END IF;
        END $$;
    ''')
    
    # Adicionar a restrição UNIQUE à coluna 'nome' na tabela 'assinaturas' se ela não existir
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'assinaturas'::regclass AND contype = 'u' AND conname = 'assinaturas_nome_key'
            ) THEN
                ALTER TABLE assinaturas ADD CONSTRAINT assinaturas_nome_key UNIQUE (nome);
            END IF;
        END $$;
    ''')
    
    # Garantir que caminho_imagem permite NULL (remover NOT NULL se existir)
    cursor.execute('''
        DO $$
        BEGIN
            -- Verificar se a coluna existe
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'assinaturas' AND column_name = 'caminho_imagem'
            ) THEN
                -- Remover NOT NULL se existir (isso não causa erro se não existir)
                BEGIN
                    ALTER TABLE assinaturas ALTER COLUMN caminho_imagem DROP NOT NULL;
                EXCEPTION WHEN OTHERS THEN
                    -- Se já não tiver NOT NULL, ignora o erro
                    NULL;
                END;
            END IF;
        END $$;
    ''')
    
    
    
    # Tabela principal de ordens de serviço
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            data DATE NOT NULL,
            endereco_origem TEXT,
            endereco_destino TEXT,
            km DECIMAL(10,2) DEFAULT 0.0,
            valor_deslocamento DECIMAL(10,2) DEFAULT 0.0,
            forma_pagamento_id INTEGER,
            assinatura_id INTEGER,
            total DECIMAL(10,2) DEFAULT 0.0,
            status VARCHAR(50) DEFAULT 'Nova',
            parcelas INTEGER DEFAULT 1,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (forma_pagamento_id) REFERENCES formas_pagamento (id),
            FOREIGN KEY (assinatura_id) REFERENCES assinaturas (id)
        )
    ''')
    
    # Tabela de itens de serviço
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS itens_servico (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER NOT NULL,
            servico_id INTEGER,
            descricao TEXT NOT NULL,
            qtd INTEGER DEFAULT 1,
            valor_unit DECIMAL(10,2) DEFAULT 0.0,
            valor_total DECIMAL(10,2) DEFAULT 0.0,
            FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id),
            FOREIGN KEY (servico_id) REFERENCES servicos (id)
        )
    ''')
    
    # Tabela de itens de material
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS itens_material (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER NOT NULL,
            material_id INTEGER,
            descricao TEXT NOT NULL,
            qtd INTEGER DEFAULT 1,
            valor_unit DECIMAL(10,2) DEFAULT 0.0,
            valor_total DECIMAL(10,2) DEFAULT 0.0,
            data DATE,
            FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id),
            FOREIGN KEY (material_id) REFERENCES materiais (id)
        )
    ''')
    
    # Migração: adicionar coluna 'data' em itens_material se não existir
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
    
    # Tabela de adicionais (impostos, BDI, descontos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS adicionais (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER NOT NULL,
            tipo VARCHAR(50) NOT NULL,
            descricao TEXT,
            valor DECIMAL(10,2) DEFAULT 0.0,
            FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id)
        )
    ''')
    
    # Tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            senha VARCHAR(255) NOT NULL,
            nome VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            ativo BOOLEAN DEFAULT true,
            admin BOOLEAN DEFAULT false,
            perm_clientes BOOLEAN DEFAULT true,
            perm_materiais BOOLEAN DEFAULT true,
            perm_servicos BOOLEAN DEFAULT true,
            perm_ordens BOOLEAN DEFAULT true,
            perm_financeiro BOOLEAN DEFAULT true,
            perm_configuracoes BOOLEAN DEFAULT false,
            perm_assinaturas BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Adicionar colunas de permissões se não existirem (para bancos existentes)
    try:
        # Verificar e adicionar cada coluna individualmente
        for coluna in ['perm_clientes', 'perm_materiais', 'perm_servicos', 'perm_ordens', 
                      'perm_financeiro', 'perm_configuracoes', 'perm_assinaturas']:
            cursor.execute(f'''
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='usuarios' AND column_name='{coluna}'
                    ) THEN
                        ALTER TABLE usuarios ADD COLUMN {coluna} BOOLEAN DEFAULT true;
                    END IF;
                END $$;
            ''')
        # Configurações deve ser false por padrão
        cursor.execute('''
            UPDATE usuarios SET perm_configuracoes = false 
            WHERE perm_configuracoes IS NULL
        ''')
    except Exception as e:
        print(f"Aviso ao adicionar colunas de permissões: {e}")
    
    # Tabela de configurações do sistema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_sistema (
            id SERIAL PRIMARY KEY,
            chave VARCHAR(100) UNIQUE NOT NULL,
            valor TEXT,
            descricao TEXT
        )
    ''')
    
    # Tabela de custos das ordens de serviço
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custos_ordem (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER NOT NULL,
            custo_materiais DECIMAL(10,2) DEFAULT 0.0,
            custo_servicos DECIMAL(10,2) DEFAULT 0.0,
            custo_deslocamento DECIMAL(10,2) DEFAULT 0.0,
            custo_total DECIMAL(10,2) DEFAULT 0.0,
            lucro_bruto DECIMAL(10,2) DEFAULT 0.0,
            margem_lucro DECIMAL(5,2) DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id)
        )
    ''')
    
    # Criar índices únicos para PostgreSQL
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_formas_pagamento_nome 
        ON formas_pagamento (nome)
    ''')
    
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_impostos_bdi_tipo_descricao 
        ON impostos_bdi (tipo, descricao)
    ''')
    
    # Inserir dados iniciais
    insert_initial_data(cursor)
    
    # Inserir usuário admin padrão
    insert_initial_users(cursor)
    
    # Inserir configurações padrão
    insert_initial_config(cursor)
    
    # Tabela de configurações do sistema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            id SERIAL PRIMARY KEY,
            chave VARCHAR(255) NOT NULL UNIQUE,
            valor TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ Banco de dados inicializado com sucesso!")

def insert_initial_data(cursor):
    """Insere dados iniciais no banco"""
    
    # Formas de pagamento padrão
    formas_pagamento = [
        ('PIX', 'PIX', 1),
        ('Boleto', 'Boleto', 1),
        ('Dinheiro', 'Dinheiro', 1),
        ('Parcelado', 'Parcelado', 12)
    ]
    
    for forma in formas_pagamento:
        cursor.execute('''
            INSERT INTO formas_pagamento (nome, tipo, parcelas_max)
            VALUES (%s, %s, %s)
            ON CONFLICT (nome) DO NOTHING
        ''', forma)
    
    # Impostos e BDI padrão
    impostos_bdi = [
        ('imposto', 'ICMS', 0.0),
        ('imposto', 'PIS', 0.0),
        ('imposto', 'COFINS', 0.0),
        ('bdi', 'Administração', 0.0),
        ('bdi', 'Lucro', 0.0),
        ('bdi', 'Imprevistos', 0.0)
    ]
    
    for imposto in impostos_bdi:
        cursor.execute('''
            INSERT INTO impostos_bdi (tipo, descricao, valor)
            VALUES (%s, %s, %s)
            ON CONFLICT (tipo, descricao) DO NOTHING
        ''', imposto)

def insert_initial_users(cursor):
    """Insere usuário admin padrão"""
    import hashlib
    
    # Senha padrão: admin123 (hash MD5)
    senha_hash = hashlib.md5('admin123'.encode()).hexdigest()
    
    cursor.execute('''
        INSERT INTO usuarios (username, senha, nome, email, admin)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
    ''', ('admin', senha_hash, 'Administrador', 'admin@erp.com', True))

def insert_initial_config(cursor):
    """Insere configurações padrão do sistema"""
    configs = [
        ('taxa_por_km', '5.00', 'Taxa cobrada por quilômetro de deslocamento'),
        ('mapbox_token', 'pk.eyJ1Ijoia3Jpc3RpYW5iZXJuYXJkIiwiYSI6ImNtZ3B2YTYwZDBiaTIybXB3Z3I2YzNxbW0ifQ.4WXS8ckDpkZp_6LFFyTeGA', 'Token de acesso da API Mapbox'),
        ('empresa_nome', 'ERP Eletrotécnica', 'Nome da empresa'),
        ('empresa_cnpj', '', 'CNPJ da empresa')
    ]
    
    for chave, valor, descricao in configs:
        cursor.execute('''
            INSERT INTO config_sistema (chave, valor, descricao)
            VALUES (%s, %s, %s)
            ON CONFLICT (chave) DO NOTHING
        ''', (chave, valor, descricao))
    
    # Não criar assinatura padrão automaticamente - usuário deve criar manualmente
