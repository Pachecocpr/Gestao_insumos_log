import streamlit as st
import pandas as pd
from github import Github
from google import genai
import io
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LogiStock WMS Pro", page_icon="📦", layout="wide")
st.title("📦 LogiStock: Gestão de Insumos & Porta-Paletes")

# --- CONEXÃO AUTOMÁTICA COM O GEMINI VIA SECRETS ---
try:
    # Captura a API Key oculta configurada no Streamlit Cloud
    ai_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=ai_key)
except Exception:
    st.error("⚠️ Erro: A chave 'GEMINI_API_KEY' não foi encontrada nos Secrets do Streamlit Cloud.")
    st.stop()

# --- SIDEBAR: ESCOLHA DA FONTE DE DADOS ---
with st.sidebar:
    st.header("⚙️ Configuração do Banco de Dados")
    
    # Permite ao usuário escolher como quer alimentar o app
    origem_dados = st.radio(
        "Como deseja carregar o estoque?",
        ["Buscar na pasta do GitHub", "Fazer upload de planilha local (.xlsx)"]
    )
    
    st.write("---")
    if origem_dados == "Buscar na pasta do GitHub":
        st.subheader("🔗 Dados do Repositório")
        github_token = st.text_input("GitHub Token", type="password")
        repo_name = st.text_input("Repositório (usuario/repo)")
        pasta_input = st.text_input("Pasta no GitHub (Ex: dados)", value="dados")
        
        # Formatação dos caminhos do GitHub
        caminho_base = f"{pasta_input}/" if pasta_input and not pasta_input.endswith("/") else pasta_input
        caminho_matriz = f"{caminho_base}insumos.xlsx"
        caminho_movimentacao = f"{caminho_base}controle_movimentacao.xlsx"
    else:
        st.subheader("📤 Upload do Arquivo")
        arquivo_up = st.file_uploader("Selecione a planilha insumos.xlsx", type=["xlsx"])

# --- FUNÇÕES PARA O GITHUB ---
def carregar_excel_github(token, repo_target, path_target, colunas):
    try:
        g = Github(token)
        repo = g.get_repo(repo_target)
        file_content = repo.get_contents(path_target)
        df = pd.read_excel(io.BytesIO(file_content.decoded_content))
        return df, file_content.sha
    except Exception:
        return pd.DataFrame(columns=colunas), None

def salvar_excel_github(token, repo_target, path_target, df, sha, msg):
    try:
        g = Github(token)
        repo = g.get_repo(repo_target)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        if sha:
            repo.update_file(path_target, msg, output.getvalue(), sha)
        else:
            repo.create_file(path_target, msg, output.getvalue())
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no GitHub: {e}")
        return False

# --- CONTROLE DE INICIALIZAÇÃO DE DADOS ---
colunas_matriz = ["Código", "Descrição", "Métrica", "Quantidade", "Rua_Endereco"]
colunas_mov = ["Data_Hora", "Código", "Descrição", "Tipo", "Quantidade", "Métrica", "Rua_Endereco", "Operador"]

df_insumos = pd.DataFrame(columns=colunas_matriz)
df_movimentos = pd.DataFrame(columns=colunas_mov)
sha_matriz, sha_movimentos = None, None
pronto_para_rodar = False

# --- LOGICA DE CARREGAMENTO SELECIONADO ---
if origem_dados == "Buscar na pasta do GitHub":
    if github_token and repo_name:
        df_insumos, sha_matriz = carregar_excel_github(github_token, repo_name, caminho_matriz, colunas_matriz)
        df_movimentos, sha_movimentos = carregar_excel_github(github_token, repo_name, caminho_movimentacao, colunas_mov)
        if not df_insumos.empty:
            pronto_para_rodar = True
        else:
            st.warning(f"⚠️ Não encontramos dados em '{caminho_matriz}'. Certifique-se de que a planilha existe no GitHub.")
else:
    if arquivo_up is not None:
        try:
            df_insumos = pd.read_excel(arquivo_up)
            # Verifica se as colunas estão corretas
            if all(col in df_insumos.columns for col in colunas_matriz):
                pronto_para_rodar = True
                # Cria histórico temporário em memória se não houver
                if 'historico_local' not in st.session_state:
                    st.session_state['historico_local'] = pd.DataFrame(columns=colunas_mov)
                df_movimentos = st.session_state['historico_local']
            else:
                st.error(f"A planilha precisa conter exatamente as colunas: {colunas_matriz}")
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

# --- EXECUÇÃO DO APLICATIVO ---
if pronto_para_rodar:
    
    aba_mapa, aba_movimentar, aba_ia = st.tabs(["🛣️ Estrutura de Ruas", "🔄 Movimentação (Entradas/Saídas)", "🤖 Analista IA"])
    
    # --- ABA 1: MAPA POR RUAS ---
    with aba_mapa:
        st.subheader("📍 Filtro e Visualização de Ocupação")
        
        ruas_disponiveis = sorted(df_insumos["Rua_Endereco"].dropna().astype(str).unique())
        rua_selecionada = st.selectbox("Filtrar Porta-Paletes por Rua:", ["Todas"] + ruas_disponiveis)
        
        df_filtrado = df_insumos if rua_selecionada == "Todas" else df_insumos[df_insumos["Rua_Endereco"] == rua_selecionada]
        st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
        
        if not df_insumos.empty:
            st.subheader("📊 Volume Acumulado de Insumos por Rua")
            grafico_data = df_insumos.groupby("Rua_Endereco")["Quantidade"].sum()
            st.bar_chart(grafico_data)

    # --- ABA 2: MOVIMENTAÇÃO ---
    with aba_movimentar:
        st.subheader("Registrar Lançamento no Fluxo")
        
        item_selecionado = st.selectbox("Escolha o Insumo:", df_insumos["Descrição"].unique())
        idx = df_insumos[df_insumos["Descrição"] == item_selecionado].index[0]
        
        # Coleta os dados do registro atual
        cod = df_insumos.loc[idx, "Código"]
        met = df_insumos.loc[idx, "Métrica"]
        qtd = df_insumos.loc[idx, "Quantidade"]
        rua = df_insumos.loc[idx, "Rua_Endereco"]
        
        st.info(f"📋 Código: {cod} | Tipo: {met} | Saldo Atual: {qtd} | Endereço: {rua}")
        
        col1, col2 = st.columns(2)
        with col1:
            tipo_op = st.radio("Operação:", ["ENTRADA", "SAÍDA"])
            quantidade_op = st.number_input("Quantidade:", min_value=1, step=1)
        with col2:
            operador = st.text_input("Nome do Operador:", value="Almoxarife")
            nova_rua = st.text_input("Posição no Porta-Paletes (Rua/Módulo):", value=str(rua))
            
        if st.button("Confirmar Operação"):
            if tipo_op == "SAÍDA" and qtd < quantidade_op:
                st.error("Operação negada! Saldo em estoque insuficiente.")
            else:
                # Atualiza os dados locais na memória
                if tipo_op == "ENTRADA":
                    df_insumos.loc[idx, "Quantidade"] = qtd + quantidade_op
                else:
                    df_insumos.loc[idx, "Quantidade"] = qtd - quantidade_op
                
                df_insumos.loc[idx, "Rua_Endereco"] = nova_rua
                
                novo_reg = {
                    "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Código": cod,
                    "Descrição": item_selecionado,
                    "Tipo": tipo_op,
                    "Quantidade": quantidade_op,
                    "Métrica": met,
                    "Rua_Endereco": nova_rua,
                    "Operador": operador
                }
                
                # Salva os dados com base na escolha do usuário
                if origem_dados == "Buscar na pasta do GitHub":
                    df_movimentos = pd.concat([df_movimentos, pd.DataFrame([novo_reg])], ignore_index=True)
                    if salvar_excel_github(github_token, repo_name, caminho_matriz, df_insumos, sha_matriz, f"Ajuste {item_selecionado}") and \
                       salvar_excel_github(github_token, repo_name, caminho_movimentacao, df_movimentos, sha_movimentos, f"Registro {tipo_op}"):
                        st.success("Dados sincronizados no GitHub com sucesso!")
                        st.rerun()
                else:
                    # Modo Local: Salva no estado da sessão do navegador e disponibiliza para download
                    st.session_state['historico_local'] = pd.concat([st.session_state['historico_local'], pd.DataFrame([novo_reg])], ignore_index=True)
                    st.success("Atualizado localmente na memória do app!")
                    
                    # Cria botões para baixar os arquivos atualizados
                    out_matriz = io.BytesIO()
                    with pd.ExcelWriter(out_matriz, engine='openpyxl') as w: df_insumos.to_excel(w, index=False)
                    st.download_button("📥 Baixar Planilha de Insumos Atualizada", data=out_matriz.getvalue(), file_name="insumos_atualizado.xlsx")

    # --- ABA 3: INTELIGÊNCIA ARTIFICIAL ---
    with aba_ia:
        st.subheader("🤖 Consultas com IA (Gemini)")
        pergunta = st.text_input("Faça perguntas sobre as ruas, quantidades ou rotatividade:")
        
        if st.button("Analisar com Gemini") and pergunta:
            with st.spinner("A IA está interpretando os dados logísticos..."):
                try:
                    prompt = f"""
                    Você gerencia o controle de insumos logísticos armazenados em estruturas porta-paletes distribuídas por ruas.
                    Considere as informações abaixo para responder de forma técnica e direta.

                    ESTOQUE E ENDEREÇO ATUAL:
                    {df_insumos.to_string(index=False)}

                    HISTÓRICO RECENTE DE ENTRADAS/SAÍDAS:
                    {df_movimentos.to_string(index=False)}

                    Dúvida do operador: {pergunta}
                    """
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    st.info("🤖 Retorno do Analista IA:")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"Erro na comunicação com a API do Gemini: {e}")
else:
    if origem_dados == "Buscar na pasta do GitHub":
        st.info("👋 Para iniciar, informe seu Token do GitHub, Nome do Repositório e a pasta na barra lateral.")
    else:
        st.info("👋 Para iniciar, faça o upload da sua planilha Excel contendo os dados do estoque na barra lateral.")
