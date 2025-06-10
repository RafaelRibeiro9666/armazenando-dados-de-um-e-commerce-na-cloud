import streamlit as st
from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv
import pymssql
import uuid # Para gerar IDs únicos para as imagens

# --- 1. Carregar Variáveis de Ambiente ---
# É fundamental ter um arquivo .env na mesma pasta do main.py
# com as seguintes variáveis:
# BLOB_CONTAINER_NAME="nome_do_seu_container"
# BLOB_ACCOUNT_NAME="nome_da_sua_conta_de_storage"
# BLOB_CONNECTION_STRING="sua_connection_string_do_blob_storage"
# SQL_SERVER="seu_server_sql.database.windows.net"
# SQL_DATABASE="seu_database_sql"
# SQL_USER="seu_usuario_sql"
# SQL_PASSWORD="sua_senha_sql"

load_dotenv()

BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME")
BLOB_ACCOUNT_NAME = os.getenv("BLOB_ACCOUNT_NAME")
BLOB_CONNECTION_STRING = os.getenv("BLOB_CONNECTION_STRING")

SQL_SERVER = os.getenv("SQL_SERVER")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_USER = os.getenv("SQL_USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")

                #DEPURAÇÃO
print(f"DEBUG: BLOB_CONTAINER_NAME lido: '{BLOB_CONTAINER_NAME}'")
print(f"DEBUG: BLOB_ACCOUNT_NAME lido: '{BLOB_ACCOUNT_NAME}'")
print(f"DEBUG: BLOB_CONNECTION_STRING lida (parte inicial): '{BLOB_CONNECTION_STRING[:80]}...'")
print(f"DEBUG: SQL_SERVER lido: '{SQL_SERVER}'")
# --- FIM DAS LINHAS DE DEPURACAO ---

# --- 2. Funções de Conexão e Interação com Azure Services ---

def get_blob_service_client():
    """Retorna um cliente para interagir com o Blob Storage."""
    if not BLOB_CONNECTION_STRING:
        st.error("🚫 Erro: BLOB_CONNECTION_STRING não configurada no seu arquivo .env.")
        print("Erro: BLOB_CONNECTION_STRING não configurada no .env") # Para depuração no terminal
        return None
    return BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)

def upload_image_to_blob(image_file):
    """
    Faz upload de um arquivo de imagem para o Azure Blob Storage
    e retorna a URL da imagem.
    """
    if not image_file:
        return None

    blob_service_client = get_blob_service_client()
    if not blob_service_client:
        return None

    container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)

    try:
        # Garante que o container existe. Se já existir, não fará nada.
        # As permissões de acesso público (Blob) devem ser configuradas no portal Azure.
        container_client.create_container()
    except Exception as e:
        # Ignora o erro se o container já existe, mas exibe outros erros.
        if "ContainerAlreadyExists" not in str(e):
            st.error(f"🚫 Erro ao criar/verificar container no Blob Storage: {e}")
            print(f"Erro detalhado ao criar/verificar container: {e}")

    # Gera um nome único para o blob para evitar conflitos (UUID + nome original do arquivo)
    unique_filename = str(uuid.uuid4()) + "_" + image_file.name
    blob_client = container_client.get_blob_client(unique_filename)

    try:
        # Faz upload do arquivo, sobrescrevendo se já existir um com o mesmo nome (improvável com UUID)
        blob_client.upload_blob(image_file.read(), overwrite=True)
        # Monta a URL pública da imagem. O BLOB_ACCOUNT_NAME é crucial aqui.
        image_url = f"https://{BLOB_ACCOUNT_NAME}.blob.core.windows.net/{BLOB_CONTAINER_NAME}/{unique_filename}"
        return image_url
    except Exception as e:
        st.error(f"🚫 Erro ao fazer upload da imagem para o Blob Storage: {e}")
        print(f"Erro detalhado ao fazer upload da imagem: {e}")
        return None

def get_sql_connection():
    """Retorna uma conexão com o Azure SQL Database usando pymssql."""
    # Verifica se todas as variáveis de conexão SQL estão configuradas
    if not all([SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD]):
        st.error("🚫 Erro: Variáveis de conexão do Azure SQL Database (SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD) não estão todas configuradas no seu arquivo .env.")
        print("Erro: Variáveis SQL não configuradas no .env. Verifique SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD.")
        return None

    try:
        # pymssql se conecta passando os parâmetros diretamente
        # A porta padrão do SQL Server é 1433
        # as_dict=True faz com que o cursor retorne dicionários em vez de tuplas,
        # o que simplifica o acesso aos dados posteriormente.
        conn = pymssql.connect(
            server=SQL_SERVER,
            user=SQL_USER,
            password=SQL_PASSWORD,
            database=SQL_DATABASE,
            port=1433, # Porta padrão do SQL Server
            as_dict=True # Retorna as linhas como dicionários
        )
        print("Conexão com Azure SQL Database (pymssql) bem-sucedida.")
        return conn
    except pymssql.Error as ex:
        # pymssql levanta pymssql.Error para problemas de conexão/query
        st.error(f"🚫 Erro ao conectar ao banco de dados com pymssql: {ex}. Verifique suas credenciais e o firewall do Azure.")
        print(f"Erro detalhado de conexão com o banco de dados (pymssql.Error): {ex}")
        return None
    except Exception as e:
        # Para capturar qualquer outro erro inesperado na conexão
        st.error(f"🚫 Erro inesperado ao conectar ao banco de dados: {e}")
        print(f"Erro inesperado de conexão com o banco de dados: {e}")
        return None

def insert_product(name, description, price, image_url):
    """Insere um novo produto no Azure SQL Database."""
    conn = get_sql_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        # pymssql usa %s como placeholder para os parâmetros na query
        insert_sql = """
        INSERT INTO DBO.Produtos (NomeProduto, Descricao, Preco, ImageURL)
        VALUES (%s, %s, %s, %s);
        """
        cursor.execute(insert_sql, (name, description, price, image_url))
        conn.commit() # Confirma as alterações no banco de dados
        cursor.close()
        conn.close()
        return True
    except pymssql.Error as ex:
        st.error(f"🚫 Erro ao inserir produto com pymssql: {ex}. Verifique a estrutura da tabela ou os dados.")
        print(f"Erro detalhado ao inserir produto (pymssql.Error): {ex}")
        if conn: # Garante que a conexão seja fechada mesmo em caso de erro
            conn.close()
        return False
    except Exception as e:
        st.error(f"🚫 Erro inesperado ao inserir produto: {e}")
        print(f"Erro inesperado ao inserir produto: {e}")
        if conn:
            conn.close()
        return False

def list_products():
    """Lista todos os produtos do Azure SQL Database."""
    conn = get_sql_connection()
    if conn is None:
        return []

    try:
        cursor = conn.cursor()
        # Seleciona todos os produtos da tabela DBO.Produtos
        select_sql = "SELECT ProductID, NomeProduto, Descricao, Preco, ImageURL FROM DBO.Produtos;"
        cursor.execute(select_sql)
        
        # Como usamos as_dict=True na conexão do pymssql, fetchall já retorna uma lista de dicionários
        products = cursor.fetchall() 
            
        cursor.close()
        conn.close()
        return products
    except pymssql.Error as ex:
        st.error(f"🚫 Erro ao listar produtos com pymssql: {ex}.")
        print(f"Erro detalhado ao listar produtos (pymssql.Error): {ex}")
        if conn:
            conn.close()
        return []
    except Exception as e:
        st.error(f"🚫 Erro inesperado ao listar produtos: {e}")
        print(f"Erro inesperado ao listar produtos: {e}")
        if conn:
            conn.close()
        return []

# --- 3. UI com Streamlit ---

# Configurações iniciais da página Streamlit
st.set_page_config(layout="wide", page_title="Cadastro de Produtos E-Commerce")

st.title("Cadastro de Produtos para E-Commerce")
st.write("Olá! Cadastre produtos e veja-os listados aqui!")

# --- Região de Cadastro de Produtos ---
st.header("Cadastrar Novo Produto")
# Usando st.form com clear_on_submit=True para limpar os campos após o envio
with st.form("product_form", clear_on_submit=True):
    product_name = st.text_input("Nome do Produto", max_chars=100, help="Nome do item que será exibido no e-commerce.")
    product_description = st.text_area("Descrição do Produto", max_chars=500, help="Detalhes sobre o produto.")
    product_price = st.number_input("Preço do Produto (R$)", min_value=0.01, format="%.2f", help="Valor do produto em reais.")
    uploaded_image = st.file_uploader("Upload da Imagem do Produto (.jpg, .jpeg, .png)", type=["jpg", "jpeg", "png"], help="Selecione uma imagem para o seu produto.")

    submitted = st.form_submit_button("💾 Salvar Produto")

    if submitted:
        if not product_name or not product_description or product_price is None:
            st.error("⚠️ Por favor, preencha todos os campos obrigatórios (Nome, Descrição, Preço).")
        elif uploaded_image is None:
            st.error("⚠️ Por favor, faça o upload de uma imagem para o produto.")
        else:
            with st.spinner("⏳ Fazendo upload da imagem e salvando produto..."):
                image_url = upload_image_to_blob(uploaded_image)
                if image_url:
                    if insert_product(product_name, product_description, product_price, image_url):
                        st.success("✅ Produto cadastrado com sucesso!")
                        # Atualiza a lista de produtos na sessão após o cadastro
                        if 'products' in st.session_state:
                            st.session_state.products = list_products()
                    else:
                        st.error("❌ Falha ao cadastrar o produto no banco de dados. Verifique os logs.")
                else:
                    st.error("❌ Falha ao fazer upload da imagem. O produto não foi cadastrado.")

st.markdown("---") # Separador visual para organizar o layout

# --- Região de Listagem de Produtos ---
st.header("📦 Produtos Cadastrados")

# Usar st.session_state para armazenar a lista de produtos e evitar recarregamentos desnecessários
# Inicializa a lista de produtos se ainda não estiver no estado da sessão
if 'products' not in st.session_state:
    st.session_state.products = []

# Botão para listar (ou recarregar) os produtos manualmente
if st.button("🔄 Recarregar Lista de Produtos"):
    with st.spinner("⏳ Carregando produtos..."):
        st.session_state.products = list_products()
        if not st.session_state.products:
            st.info("Nenhum produto cadastrado ainda. Use o formulário acima para adicionar um novo produto.")

# Carrega os produtos na primeira execução ou se não houver produtos carregados ainda
if not st.session_state.products:
    with st.spinner("⏳ Carregando produtos iniciais..."):
        st.session_state.products = list_products()
        if not st.session_state.products:
            st.info("Nenhum produto cadastrado ainda. Comece adicionando um novo produto no formulário acima!")

# Exibe os produtos em formato de cards, distribuídos em colunas
if st.session_state.products:
    num_columns = 3 # Define o número de colunas para exibir os cards
    columns = st.columns(num_columns) # Cria as colunas
    
    for i, product in enumerate(st.session_state.products):
        # Distribui cada produto para uma coluna diferente de forma cíclica
        with columns[i % num_columns]:
            st.subheader(product.get("NomeProduto", "Nome Indisponível"))
            if product.get("ImageURL"):
                # Garante que a URL da imagem não esteja vazia antes de tentar exibir
                if product["ImageURL"]:
                    st.image(product["ImageURL"], caption=f"Imagem de {product.get('NomeProduto')}", use_container_width="always")
                else:
                    st.write("*(Imagem não disponível)*")
            st.write(f"**Preço:** R$ {product.get('Preco', 0.0):.2f}")
            st.write(f"**Descrição:** {product.get('Descricao', 'Sem descrição')}")
            st.markdown("---") # Separador visual para cada card