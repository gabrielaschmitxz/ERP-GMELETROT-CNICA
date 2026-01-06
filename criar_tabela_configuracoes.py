"""
Script para criar a tabela configuracoes no banco de dados
Execute este script uma vez para adicionar a tabela de configurações
"""
from database_web import get_db_connection

def criar_tabela_configuracoes():
    """Cria a tabela configuracoes se não existir"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Criar tabela de configurações
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
        print("✅ Tabela 'configuracoes' criada com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro ao criar tabela: {e}")
        raise

if __name__ == '__main__':
    criar_tabela_configuracoes()

