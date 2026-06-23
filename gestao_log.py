import streamlit as st
import pandas as pd
from google import genai
import io
import hashlib
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LogiStock Secure Pro", page_icon="📦", layout="wide")
st.title("📦 LogiStock: WMS Pro com Controle de Acesso")

# --- CONEXÃO COM O GEMINI VIA SECRETS ---
try:
    ai_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=ai_key)
except Exception:
    st.error("⚠️ Erro: A chave 'GEMINI_API_KEY' não foi encontrada nos Secrets do Streamlit Cloud.")
    st.stop()

# --- FUNÇÃO PARA CRIPTOGRAFAR PALAVRAS-PASSE ---
def codificar_senha(senha):
    return hashlib.sha256(str.encode(senha)).hexdigest()

# --- SIDEBAR: CARREGAMENTO DA PLANILHA LOCAL ---
with st.sidebar:
    st.header("📂 Arquivo Local da Máquina")
    st.write("Suba a planilha do seu computador para ativar o sistema.")
    arquivo_up = st.file_uploader("Selecione a planilha insumos.xlsx:", type=["xlsx"])

# --- ESTRUTURA PADRÃO DE COLUNAS ---
colunas_matriz = ["Código", "Descrição", "Métrica", "Quantidade", "Rua_Endereco"]
colunas_mov = ["Data_Hora", "Código", "Descrição", "Tipo", "Quantidade", "Métrica", "Rua_Endereco", "Operador"]
colunas_usuarios = ["Usuario", "Senha"]

df_insumos = pd.DataFrame(columns=colunas_matriz)
df_movimentos = pd.DataFrame(columns=colunas_mov)
df_usuarios = pd.DataFrame(columns=colunas_usuarios)
pronto_para_rodar = False

# --- CONTROLE DE SESSÃO E CARREGAMENTO DAS ABAS DO EXCEL ---
if arquivo_up is not None:
    try:
        if 'df_insumos_local' not in st.session_state:
            # Tenta ler as abas existentes no Excel de forma independente
            excel_file = pd.ExcelFile(arquivo_up)
            
            # Aba de Insumos (Obrigatória)
            if "Insumos" in excel_file.sheet_names:
                df_carregado = pd.read_excel(arquivo_up, sheet_name="Insumos")
                if all(col in df_carregado.columns for col in colunas_matriz):
                    st.session_state['df_insumos_local'] = df_carregado
                else:
                    st.error(f"A aba 'Insumos' precisa conter exatamente as colunas: {colunas_matriz}")
                    st.stop()
            else:
                st.error("O arquivo precisa conter uma aba chamada 'Insumos'.")
                st.stop()
                
            # Aba de Histórico (Opcional - cria se não existir)
            if "Historico" in excel_file.sheet_names:
                st.session_state['df_movimentos_local'] = pd.read_excel(arquivo_up, sheet_name="Historico")
            else:
                st.session_state['df_movimentos_local'] = pd.DataFrame(columns=colunas_mov)
                
            # Aba de Usuários (Opcional - cria se não existir)
            if "Usuarios" in excel_file.sheet_names:
                st.session_state['df_usuarios_local'] = pd.read_excel(arquivo_up, sheet_name="Usuarios")
            else:
                st.session_state['df_usuarios_local'] = pd.DataFrame(columns=colunas_usuarios)

        df_insumos = st.session_state['df_insumos_local']
        df_movimentos = st.session_state['df_movimentos_local']
        df_usuarios = st.session_state['df_usuarios_local']
        pronto_para_rodar = True
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

# --- SISTEMA DE AUTENTICAÇÃO ---
if pronto_para_rodar:
    if 'usuario_logado' not in st.session_state:
        st.session_state['usuario_logado'] = None

    # Se o usuário não está logado, exibe tela de login/cadastro
        st.subheader("🔒 Controle de Acesso Necessário")
        aba_login, aba_cadastro = st.tabs(["🔑 Realizar Login", "📝 Cadastrar Usuário"])
        
        with aba_login:
            with st.form(key="form_login"):
                user_login = st.text_input("Usuário:")
                pass_login = st.text_input("Senha:", type="password")
                botao_login = st.form_submit_button("Entrar no Sistema")
                
                if botao_login:
                    senha_hash = codificar_senha(pass_login)
                    # Verifica se o usuário e senha batem com a planilha
                    usuario_valido = df_usuarios[(df_usuarios["Usuario"] == user_login) & (df_usuarios["Senha"] == senha_hash)]
                    
                    if not usuario_valido.empty:
                        st.session_state['usuario_logado'] = user_login
                        st.success(f"Bem-vindo, {user_login}!")
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
                        
        with aba_cadastro:
            st.write("Crie credenciais para novos operadores do armazém.")
            with st.form(key="form_cadastro"):
                user_novo = st.text_input("Defina o Usuário:")
                pass_novo = st.text_input("Defina a Senha:", type="password")
                botao_cadastrar = st.form_submit_button("Gravar Novo Usuário")
                
                if botao_cadastrar:
                    if user_novo in df_usuarios["Usuario"].values:
                        st.error("Este nome de usuário já está cadastrado.")
                    elif user_novo == "" or pass_novo == "":
                        st.error("Usuário e senha não podem ficar em branco.")
                    else:
                        senha_hash_nova = codificar_senha(pass_novo)
                        novo_user_df = pd.DataFrame([{"Usuario": user_novo, "Senha": senha_hash_nova}])
                        st.session_state['df_usuarios_local'] = pd.concat([st.session_state['df_usuarios_local'], novo_user_df], ignore_index=True)
                        st.success(f"Usuário '{user_novo}' cadastrado com sucesso! Faça login na aba ao lado.")
                        st.rerun()
        st.stop()  # Bloqueia o app caso não esteja logado

    # --- SE USUÁRIO ESTIVER LOGADO, LIBERA O SISTEMA ---
    operador_atual = st.session_state['usuario_logado']
    st.sidebar.success(f"👤 Operador: {operador_atual}")
    if st.sidebar.button("🚪 Sair (Logoff)"):
        del st.session_state['usuario_logado']
        st.rerun()

    # --- DEFINIÇÃO DAS ABAS PRINCIPAIS ---
    aba_mapa, aba_movimentar, aba_enderecar, aba_ia = st.tabs([
        "🛣️ Estrutura de Ruas", 
        "🔄 Movimentação & Rotatividade", 
        "📍 Inserir/Mudar Endereço", 
        "🤖 Analista IA"
    ])
    
    # --- ABA 1: MAPA POR RUAS ---
    with aba_mapa:
        st.subheader("📌 Filtro e Ocupação do Porta-Paletes")
        ruas_disponiveis = sorted(df_insumos["Rua_Endereco"].dropna().astype(str).unique())
        rua_selecionada = st.selectbox("Filtrar Porta-Paletes por Rua:", ["Todas"] + ruas_disponiveis)
        
        df_filtrado = df_insumos if rua_selecionada == "Todas" else df_insumos[df_insumos["Rua_Endereco"] == rua_selecionada]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
        
        st.subheader("📊 Volume de Insumos por Rua")
        grafico_data = df_insumos.groupby("Rua_Endereco")["Quantidade"].sum()
        st.bar_chart(grafico_data)

    # --- ABA 2: MOVIMENTAÇÃO (CARDS E HISTÓRICO AUTOMÁTICO) ---
    with aba_movimentar:
        st.subheader("📊 Painel de Rotatividade e Fluxo de Estoque")
        df_saidas = df_movimentos[df_movimentos["Tipo"] == "SAÍDA"]
        
        total_movimentado = len(df_movimentos)
        total_pecas_saida = df_saidas["Quantidade"].sum() if not df_saidas.empty else 0
        item_mais_rodado = df_saidas.groupby("Descrição")["Quantidade"].sum().idxmax() if not df_saidas.empty else "Nenhum"
        qtd_mais_rodado = df_saidas.groupby("Descrição")["Quantidade"].sum().max() if not df_saidas.empty else 0
            
        card1, card2, card3 = st.columns(3)
        card1.metric(label="Total de Operações Realizadas", value=total_movimentado)
        card2.metric(label="Total de Insumos Despachados", value=f"{total_pecas_saida} un/cx")
        card3.metric(label="Insumo de Maior Rotatividade", value=str(item_mais_rodado), delta=f"{qtd_mais_rodado} saídas")
        
        if not df_saidas.empty:
            st.subheader("🔥 Ranking de Rotatividade (Insumos Mais Retirados)")
            dados_ranking = df_saidas.groupby("Descrição")["Quantidade"].sum().sort_values(ascending=False)
            st.bar_chart(dados_ranking)
            
        st.write("---")
        st.subheader("🔄 Registrar Nova Movimentação")
        
        item_selecionado = st.selectbox("Escolha o Insumo para Movimentar:", df_insumos["Descrição"].unique(), key="mov_item")
        idx = df_insumos[df_insumos["Descrição"] == item_selecionado].index[0]
        
        cod = df_insumos.loc[idx, "Código"]
        met = df_insumos.loc[idx, "Métrica"]
        qtd = df_insumos.loc[idx, "Quantidade"]
        rua = df_insumos.loc[idx, "Rua_Endereco"]
        
        st.warning(f"ℹ️ Código: {cod} | Tipo: {met} | Saldo Atual: {qtd} | Endereço Atual: {rua}")
        
        tipo_op = st.radio("Operação:", ["ENTRADA", "SAÍDA"])
        quantidade_op = st.number_input("Quantidade:", min_value=1, step=1)
            
        if st.button("Confirmar Movimentação"):
            if tipo_op == "SAÍDA" and qtd < quantidade_op:
                st.error("Operação negada! Saldo em estoque insuficiente.")
            else:
                if tipo_op == "ENTRADA":
                    st.session_state['df_insumos_local'].loc[idx, "Quantidade"] = qtd + quantidade_op
                else:
                    st.session_state['df_insumos_local'].loc[idx, "Quantidade"] = qtd - quantidade_op
                
                novo_reg = {
                    "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Código": cod,
                    "Descrição": item_selecionado,
                    "Tipo": tipo_op,
                    "Quantidade": quantidade_op,
                    "Métrica": met,
                    "Rua_Endereco": rua,
                    "Operador": operador_atual  # Puxa o nome logado automaticamente
                }
                st.session_state['df_movimentos_local'] = pd.concat([st.session_state['df_movimentos_local'], pd.DataFrame([novo_reg])], ignore_index=True)
                st.success("Movimentação registrada com sucesso!")
                st.rerun()

    # --- ABA 3: INSERÇÃO E ATUALIZAÇÃO DE ENDEREÇO VIA SISTEMA ---
    with aba_enderecar:
        st.subheader("📍 Atribuição de Endereço no Porta-Paletes")
        item_selecionado_end = st.selectbox("Selecione o Insumo para Endereçar:", df_insumos["Descrição"].unique(), key="end_item")
        idx_end = df_insumos[df_insumos["Descrição"] == item_selecionado_end].index[0]
        
        rua_atual_end = df_insumos.loc[idx_end, "Rua_Endereco"]
        st.info(f"O item **{item_selecionado_end}** está atualmente localizado na: `{rua_atual_end}`")
        
        rua_nova = st.text_input("Nova Rua/Posição:", value=str(rua_atual_end))
            
        if st.button("Gravar Novo Endereço via Sistema"):
            st.session_state['df_insumos_local'].loc[idx_end, "Rua_Endereco"] = rua_nova
            
            novo_reg_end = {
                "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Código": df_insumos.loc[idx_end, "Código"],
                "Descrição": item_selecionado_end,
                "Tipo": "ALTERAÇÃO ENDEREÇO",
                "Quantidade": df_insumos.loc[idx_end, "Quantidade"],
                "Métrica": df_insumos.loc[idx_end, "Métrica"],
                "Rua_Endereco": rua_nova,
                "Operador": operador_atual  # Puxa o nome logado automaticamente
            }
            st.session_state['df_movimentos_local'] = pd.concat([st.session_state['df_movimentos_local'], pd.DataFrame([novo_reg_end])], ignore_index=True)
            st.success(f"📍 Novo endereço gravado!")
            st.rerun()

    # --- SEÇÃO DE SALVAMENTO MULTI-ABAS PARA DOWNLOAD ---
    st.write("---")
    st.subheader("💾 Salvar Alterações na Máquina Local")
    
    buffer_download = io.BytesIO()
    # Cria o arquivo unificado com 3 abas internas
    with pd.ExcelWriter(buffer_download, engine='openpyxl') as writer:
        st.session_state['df_insumos_local'].to_excel(writer, sheet_name="Insumos", index=False)
        st.session_state['df_movimentos_local'].to_excel(writer, sheet_name="Historico", index=False)
        st.session_state['df_usuarios_local'].to_excel(writer, sheet_name="Usuarios", index=False)
    
    st.download_button(
        label="📥 Baixar Planilha Atualizada (.xlsx)",
        data=buffer_download.getvalue(),
        file_name="insumos_atualizado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- ABA 4: INTELIGÊNCIA ARTIFICIAL ---
    with aba_ia:
        st.subheader("🤖 Analista IA / Perguntas por texto")
        with st.form(key="formulario_ia", clear_on_submit=False):
            pergunta = st.text_input("Faça perguntas sobre as ruas, saldos ou histórico de movimentação:")
            botao_enviar = st.form_submit_button(label="Consultar Gemini")
        
        if botao_enviar and pergunta:
            with st.spinner("Analisando os seus dados locais..."):
                try:
                    prompt = f"""
                    Você é o assistente virtual exclusivo do nosso armazém logístico.
                    A sua função é responder a perguntas de forma clara, natural e profissional sobre o inventário e a localização nas estruturas porta-paletes.

                    REGRAS ABSOLUTAS DE RESPOSTA:
                    1. Responda APENAS em texto legível e corrido para o utilizador.
                    2. NUNCA exiba código Python, blocos markdown de programação, variáveis, scripts ou sintaxes de dados.
                    3. NUNCA mencione caminhos de ficheiros, variáveis internas como 'df_insumos_local', 'st.session_state' ou termos de programação.
                    4. Seja direto e focado no negócio logístico.

                    DADOS DE ESTOQUE ATUAL:
                    {df_insumos.to_string(index=False)}

                    HISTÓRICO RECENTE DE MOVIMENTAÇÕES E QUEM AS FEZ:
                    {df_movimentos.to_string(index=False)}

                    Dúvida do operador: {pergunta}
                    """
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    st.info("🤖 Retorno do Analista IA:")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"Erro na IA: {e}")
else:
    st.info("👋 Por favor, faça o upload da planilha Excel (`insumos.xlsx`) na barra lateral para ativar o sistema e a IA.")
