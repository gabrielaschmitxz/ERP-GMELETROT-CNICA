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
            print("\nERRO: URL do banco de dados esta malformada!")
            print(f"URL recebida: {DATABASE_URL_WEB}")
            print("\nSOLUCAO:")
            print(f"   1. Execute: python corrigir_url_banco.py")
            print(f"   2. Ou edite o arquivo .env manualmente")
            print(f"   3. A URL deve estar no formato:")
            print(f"      postgresql://usuario:senha@host:porta/banco?parametros")
            print("\nExemplo correto:")
            print("   DATABASE_URL_WEB=postgresql://usuario:senha@host:porta/banco?sslmode=require&channel_binding=require")
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
                print(f"Banco de dados '{db_name}' criado com sucesso!")
            
            admin_cursor.close()
            admin_conn.close()
        except Exception as admin_error:
            # Se não conseguir conectar ao postgres, tenta usar o banco padrão
            print(f"Aviso: nao foi possivel criar o banco automaticamente: {admin_error}")
            print(f"Tente criar o banco '{db_name}' manualmente no servidor PostgreSQL")
            # Tenta usar o banco padrão (neondb) como fallback
            fallback_url = DATABASE_URL_WEB.replace('/neondb_web', '/neondb')
            print(f"Ou altere DATABASE_URL_WEB no .env para: {fallback_url}")
    except Exception as e:
        print(f"Aviso: erro ao criar banco: {e}")

def init_database():
    """Inicializa o banco de dados WEB criando todas as tabelas necessárias"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        print("Verifique se o DATABASE_URL_WEB no arquivo .env esta correto")
        raise
    
    # Tabela de clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(255) NOT NULL,
            cnpj_cpf VARCHAR(20) UNIQUE,
            inscricao_estadual VARCHAR(50),
            endereco TEXT,
            telefone VARCHAR(20),
            email VARCHAR(255),
            cobranca_mensal BOOLEAN DEFAULT false
        )
    ''')

    # Migração: adicionar coluna cobranca_mensal se não existir
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'clientes' AND column_name = 'cobranca_mensal'
            ) THEN
                ALTER TABLE clientes ADD COLUMN cobranca_mensal BOOLEAN DEFAULT false;
            END IF;
        END $$;
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
            tipo_documento VARCHAR(20) DEFAULT 'OS',
            codigo_orcamento INTEGER,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (forma_pagamento_id) REFERENCES formas_pagamento (id),
            FOREIGN KEY (assinatura_id) REFERENCES assinaturas (id)
        )
    ''')

    # Migração: adicionar colunas de orçamento/OS se não existirem
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ordens_servico' AND column_name = 'tipo_documento'
            ) THEN
                ALTER TABLE ordens_servico ADD COLUMN tipo_documento VARCHAR(20) DEFAULT 'OS';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ordens_servico' AND column_name = 'codigo_orcamento'
            ) THEN
                ALTER TABLE ordens_servico ADD COLUMN codigo_orcamento INTEGER;
            END IF;
        END $$;
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
    
    # Tabela para controle de parcelas pagas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parcelas_pagas (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER NOT NULL,
            numero_parcela INTEGER NOT NULL,
            valor_parcela DECIMAL(10,2) NOT NULL,
            data_pagamento DATE NOT NULL DEFAULT CURRENT_DATE,
            data_vencimento DATE,
            FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id) ON DELETE CASCADE,
            UNIQUE(ordem_id, numero_parcela)
        )
    ''')
    
    # Migração: adicionar coluna data_vencimento se não existir
    cursor.execute('''
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'parcelas_pagas' AND column_name = 'data_vencimento'
            ) THEN
                ALTER TABLE parcelas_pagas ADD COLUMN data_vencimento DATE;
            END IF;
        END $$;
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
    
    # Migração: criar tabela parcelas_pagas se não existir
    cursor.execute('''
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'parcelas_pagas'
            ) THEN
                CREATE TABLE parcelas_pagas (
                    id SERIAL PRIMARY KEY,
                    ordem_id INTEGER NOT NULL,
                    numero_parcela INTEGER NOT NULL,
                    valor_parcela DECIMAL(10,2) NOT NULL,
                    data_pagamento DATE NOT NULL DEFAULT CURRENT_DATE,
                    FOREIGN KEY (ordem_id) REFERENCES ordens_servico (id) ON DELETE CASCADE,
                    UNIQUE(ordem_id, numero_parcela)
                );
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

    # Relatórios mensais do cliente (consolidação + forma de pagamento/parcelamento/desconto)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS relatorios_mensais (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            total_bruto DECIMAL(10,2) DEFAULT 0.0,
            desconto_tipo VARCHAR(20), -- 'fixo' ou 'percentual'
            desconto_valor DECIMAL(10,2) DEFAULT 0.0,
            desconto_percentual DECIMAL(10,2) DEFAULT 0.0,
            total_liquido DECIMAL(10,2) DEFAULT 0.0,
            forma_pagamento_id INTEGER,
            parcelas INTEGER DEFAULT 1,
            data_base DATE NOT NULL DEFAULT CURRENT_DATE,
            data_primeira_parcela DATE,
            data_pagamento DATE,
            status_pagamento_mensal VARCHAR(50) DEFAULT 'Aguardando Pagamento',
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (forma_pagamento_id) REFERENCES formas_pagamento (id),
            UNIQUE(cliente_id, mes, ano)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS relatorios_mensais_parcelas_pagas (
            id SERIAL PRIMARY KEY,
            relatorio_id INTEGER NOT NULL,
            numero_parcela INTEGER NOT NULL,
            valor_parcela DECIMAL(10,2) NOT NULL,
            data_pagamento DATE NOT NULL DEFAULT CURRENT_DATE,
            data_vencimento DATE,
            FOREIGN KEY (relatorio_id) REFERENCES relatorios_mensais (id) ON DELETE CASCADE,
            UNIQUE(relatorio_id, numero_parcela)
        )
    ''')

    # Cobrança mensal centralizada (novo fluxo no Painel de Atendimento)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cobrancas_mensais (
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'Aguardando Pagamento',
            total_bruto DECIMAL(10,2) DEFAULT 0.0,
            desconto_tipo VARCHAR(20), -- 'fixo' ou 'percentual'
            desconto_valor DECIMAL(10,2) DEFAULT 0.0,
            desconto_percentual DECIMAL(10,2) DEFAULT 0.0,
            total_liquido DECIMAL(10,2) DEFAULT 0.0,
            forma_pagamento_id INTEGER,
            parcelas INTEGER DEFAULT 1,
            data_pagamento DATE,
            data_primeira_parcela DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes (id),
            FOREIGN KEY (forma_pagamento_id) REFERENCES formas_pagamento (id),
            UNIQUE(cliente_id, mes, ano)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cobrancas_mensais_parcelas (
            id SERIAL PRIMARY KEY,
            cobranca_id INTEGER NOT NULL,
            numero_parcela INTEGER NOT NULL,
            valor_parcela DECIMAL(10,2) NOT NULL,
            data_vencimento DATE NOT NULL,
            data_pagamento DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cobranca_id) REFERENCES cobrancas_mensais (id) ON DELETE CASCADE,
            UNIQUE(cobranca_id, numero_parcela)
        )
    ''')

    # Migração: adicionar Inscrição Estadual em clientes
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'clientes' AND column_name = 'inscricao_estadual'
            ) THEN
                ALTER TABLE clientes ADD COLUMN inscricao_estadual VARCHAR(50);
            END IF;
        END $$;
    ''')

    # Migração: adicionar colunas de controle financeiro em relatorios_mensais
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'relatorios_mensais' AND column_name = 'data_primeira_parcela'
            ) THEN
                ALTER TABLE relatorios_mensais ADD COLUMN data_primeira_parcela DATE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'relatorios_mensais' AND column_name = 'data_pagamento'
            ) THEN
                ALTER TABLE relatorios_mensais ADD COLUMN data_pagamento DATE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'relatorios_mensais' AND column_name = 'status_pagamento_mensal'
            ) THEN
                ALTER TABLE relatorios_mensais ADD COLUMN status_pagamento_mensal VARCHAR(50) DEFAULT 'Aguardando Pagamento';
            END IF;
        END $$;
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

    # Índices de desempenho para consultas frequentes (painéis e relatórios)
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ordens_cliente_data
        ON ordens_servico (cliente_id, data)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ordens_status
        ON ordens_servico (status)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ordens_tipo_documento
        ON ordens_servico (tipo_documento)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_ordens_tipo_codigo_orcamento
        ON ordens_servico (tipo_documento, codigo_orcamento)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_parcelas_pagas_ordem
        ON parcelas_pagas (ordem_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_relatorios_mensais_cliente_mes_ano
        ON relatorios_mensais (cliente_id, mes, ano)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_relatorios_mensais_parcelas_relatorio
        ON relatorios_mensais_parcelas_pagas (relatorio_id)
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
    
    print("Banco de dados inicializado com sucesso!")

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
        ('mapbox_token', os.getenv('MAPBOX_TOKEN', ''), 'Token de acesso da API Mapbox'),
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
