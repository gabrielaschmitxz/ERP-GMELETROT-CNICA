import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do banco de dados WEB (separado do desktop)
# Usa um banco diferente para não conflitar com o sistema desktop
# Se o banco neondb_web não existir, o sistema tentará criar automaticamente
# Ou você pode usar o banco padrão (neondb) com um schema diferente
DATABASE_URL_WEB = os.getenv('DATABASE_URL_WEB', 
    'postgresql://neondb_owner:npg_Uuz1QgFncm7j@ep-delicate-salad-ad4ui52h-pooler.c-2.us-east-1.aws.neon.tech/neondbsslmode=require&channel_binding=require')

# Se quiser usar um banco separado, descomente e ajuste:
# DATABASE_URL_WEB = os.getenv('DATABASE_URL_WEB', 
#     'postgresql://neondb_owner:npg_Uuz1QgFncm7j@ep-delicate-salad-ad4ui52h-pooler.c-2.us-east-1.aws.neon.tech/neondb_websslmode=require&channel_binding=require')

# Se não especificado, usa o mesmo servidor mas com nome de banco diferente
# Para desenvolvimento local, você pode criar um arquivo .env com:
# DATABASE_URL_WEB=postgresql://usuario:senha@localhost:5432/erp_eletrotecnica_web

# Configurações da aplicação web
SECRET_KEY = os.getenv('SECRET_KEY', 'sua-chave-secreta-aqui-altere-em-producao')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

# Configurações de upload
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

