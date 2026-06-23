import streamlit as st
import pandas as pd
from github import Github
from google import genai
import io
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LogiStock WMS Pro", page_icon="📦", layout="wide")
st.title("📦 LogiStock: Controle de Insumos & Endereçamento (WMS)")

# --- SIDEBAR: CONFIGURAÇÕES ---
with st.sidebar:
    st.header("🔑 Conexões")
    github_token = st.text_input("GitHub Token", type="password")
    ai_key = st.text_input("Gemini API Key", type="password")
    repo_name = st.text_input("Repositório (usuario/repo)")
    
    st.header("📂 Caminho no GitHub")
    pasta_input = st.text_input("Pasta do Banco de Dados", value="dados")

# Formata os caminhos dos arquivos
if pasta_input.endswith("/") or pasta_input == "":
    caminho_matriz = f"{pasta_input}insumos.xlsx"
    caminho_movimentacao = f"{pasta_input}controle_movimentacao.xlsx"
else:
    caminho_matriz = f"{pasta_input}/insumos.xlsx"
    caminho_movimentacao = f"{pasta_input}/controle_movimentacao.xlsx"

# --- FUNÇÕES GITHUB ---
def carregar_excel_github(token, repo_target, path_target):
    try:
        g = Github(token)
        repo = g.get_repo(repo_target)
        file_content = repo.get_contents(path_target)
        excel_data = file_content.decoded_content
        df = pd.read_excel(io.BytesIO(excel_data))
        return df, file_content.sha
    except Exception:
        return None, None

def salvar_excel_github(token, repo_target, path_target, df, sha, mensagem_commit):
    try:
        g = Github(token)
        repo = g.get_repo(repo_target)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        excel_bytes = output.getvalue()
        
        if sha:
            repo.update_file(path_target, mensagem_commit, excel_bytes, sha)
        else:
            repo.create_file(path_target, mensagem_commit, excel_bytes)
        return True
    except Exception as e:
        st.error(f"Erro ao salvar arquivo no GitHub: {e}")
        return False

# --- FLUXO PRINCIPAL ---
if github_token and repo_name:
    
    df_insumos, sha_matriz = carregar_excel_github(github_token, repo_name, caminho_matriz)
    df_movimentos, sha_movimentos = carregar_excel_github(github_token, repo_name, caminho_movimentacao)
    
    if df_insumos is not None:
        
        # Garante que a coluna Endereco existe na tabela
        if "Endereco" not in df_insumos.columns:
            df_insumos["Endereco"] = "Não Endereçado"
            
        if df_movimentos is None:
            df_movimentos = pd.DataFrame(columns=["Data_Hora", "ID_Insumo", "Insumo", "Tipo_Operacao", "Quantidade", "Endereco", "Operador"])

        aba_painel, aba_movimentar, aba_ia = st.tabs(["📊 Mapa de Estoque (WMS)", "🔄 Movimentação (Entrada/Saída)", "🤖 Consulta Inteligente"])
        
        # --- ABA 1: PAINEL ---
        with aba_painel:
            st.subheader("📋 Inventário e Localização nos Porta-Paletes")
            st.write("Abaixo você confere o saldo atual e a posição exata de cada item na estrutura.")
            
            # Formatação visual para destacar a tabela
            st.dataframe(df_insumos, use_container_width=True)
            
            st.subheader("📜 Histórico Recente de Fluxo")
            st.dataframe(df_movimentos.sort_values(by="Data_Hora", ascending=False), use_container_width=True)

        # --- ABA 2: MOVIMENTAÇÃO ---
        with aba_movimentar:
            st.subheader("Lançar Movimentação de Estoque")
            
            insumo_escolhido = st.selectbox("Selecione o Insumo:", df_insumos["Insumo"].unique())
            
            # Busca o endereço atual do item escolhido para exibir ao operador
            idx_atual = df_insumos[df_insumos["Insumo"] == insumo_escolhido].index[0]
            endereco_atual = df_insumos.loc[idx_atual, "Endereco"]
            saldo_atual = df_insumos.loc[idx_atual, "Quantidade"]
            id_insumo = df_insumos.loc[idx_atual, "ID"]
            
            st.info(f"📍 **Endereço Atual no Porta-Paletes:** {endereco_atual} | 📦 **Saldo em Estoque:** {saldo_atual} unidades")
            
            col_a, col_b = st.columns(2)
            with col_a:
                tipo_op = st.radio("Operação:", ["ENTRADA", "SAÍDA"])
                quantidade = st.number_input("Quantidade de Itens:", min_value=1, step=1)
            
            with col_b:
                operador = st.text_input("Nome/ID do Operador:", value="Operador Padrão")
                # Permite atualizar o endereço caso o item mude de posição ou esteja sendo cadastrado agora
                novo_endereco = st.text_input("Confirmar/Alterar Endereço (Ex: Rua A-05-3):", value=str(endereco_atual))
            
            if st.button("Gravar Operação"):
                if tipo_op == "SAÍDA" and saldo_atual < quantidade:
                    st.error(f"Saldo insuficiente! Não é possível retirar {quantidade} unidades de um estoque que possui apenas {saldo_atual}.")
                else:
                    # Atualiza quantidade e endereço na Matriz
                    if tipo_op == "ENTRADA":
                        df_insumos.loc[idx_atual, "Quantidade"] = saldo_atual + quantidade
                    else:
                        df_insumos.loc[idx_atual, "Quantidade"] = saldo_atual - quantidade
                    
                    df_insumos.loc[idx_atual, "Endereco"] = novo_endereco
                    
                    # Cria histórico para a planilha de controle
                    nova_linha = {
                        "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ID_Insumo": id_insumo,
                        "Insumo": insumo_escolhido,
                        "Tipo_Operacao": tipo_op,
                        "Quantidade": quantidade,
                        "Endereco": novo_endereco,
                        "Operador": operador
                    }
                    df_movimentos = pd.concat([df_movimentos, pd.DataFrame([nova_linha])], ignore_index=True)
                    
                    # Salva arquivos no GitHub
                    suc_matriz = salvar_excel_github(github_token, repo_name, caminho_matriz, df_insumos, sha_matriz, f"Movimentação {insumo_escolhido}")
                    suc_mov = salvar_excel_github(github_token, repo_name, caminho_movimentacao, df_movimentos, sha_movimentos, f"Registro de {tipo_op}")
                    
                    if suc_matriz and suc_mov:
                        st.success("Estoque e endereço atualizados com sucesso!")
                        st.rerun()

        # --- ABA 3: IA ---
        with aba_ia:
            st.subheader("Pergunte à IA (Localização Espacial do Estoque)")
            st.write("A IA consegue mapear onde estão os itens com base nos dados geográficos do armazém fornecidos nas planilhas.")
            
            if ai_key:
                pergunta = st.text_input("Ex: Onde está guardado o Filme Stretch? / Quais insumos estão na Rua A?")
                if st.button("Buscar com IA") and pergunta:
                    try:
                        client = genai.Client(api_key=api_key)
                        prompt = f"""
                        Você é o assistente de WMS (Gestão de Armazém) de uma unidade logística. 
                        Sua função principal é ajudar a localizar insumos nas estruturas de porta-paletes (endereços).
                        
                        TABELA DE INSUMOS E ENDEREÇOS ATUAIS:
                        {df_insumos.to_string(index=False)}
                        
                        HISTÓRICO RECENTE:
                        {df_movimentos.to_string(index=False)}
                        
                        Responda à pergunta do operador de forma clara, indicando o endereço exato caso solicitado.
                        Pergunta: {pergunta}
                        """
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        st.info("🤖 Localizador IA:")
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"Erro na IA: {e}")
            else:
                st.warning("Insira sua Gemini API Key para ativar o Localizador com IA.")
    else:
        st.error(f"Não encontramos o arquivo 'insumos.xlsx' na pasta '{pasta_input}'.")
        st.info("💡 Certifique-se de que sua planilha matriz no Excel possua as colunas: ID, Insumo, Quantidade, Endereco.")
else:
    st.info("👋 Insira as credenciais do GitHub na barra lateral para carregar o sistema.")
