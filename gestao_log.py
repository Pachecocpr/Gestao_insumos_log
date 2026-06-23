import streamlit as st
import pandas as pd
from github import Github
from google import genai
import io
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LogiStock WMS", page_icon="📦", layout="wide")
st.title("📦 LogiStock: Gestão de Insumos por Ruas")

# --- SIDEBAR: CONEXÕES ---
with st.sidebar:
    st.header("🔑 Credenciais")
    github_token = st.text_input("GitHub Token", type="password")
    ai_key = st.text_input("Gemini API Key", type="password")
    repo_name = st.text_input("Repositório (usuario/repo)")
    pasta_input = st.text_input("Pasta no GitHub (Ex: dados)", value="dados")

# Formatação dos caminhos
caminho_base = f"{pasta_input}/" if pasta_input and not pasta_input.endswith("/") else pasta_input
caminho_matriz = f"{caminho_base}insumos.xlsx"
caminho_movimentacao = f"{caminho_base}controle_movimentacao.xlsx"

# --- FUNÇÕES DE CARREGAMENTO ---
def carregar_excel(token, repo_target, path_target, colunas_padrao):
    try:
        g = Github(token)
        repo = g.get_repo(repo_target)
        file_content = repo.get_contents(path_target)
        df = pd.read_excel(io.BytesIO(file_content.decoded_content))
        return df, file_content.sha
    except Exception:
        # Se não encontrar, retorna um DataFrame vazio estruturado
        return pd.DataFrame(columns=colunas_padrao), None

def salvar_excel(token, repo_target, path_target, df, sha, msg):
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
        st.error(f"Erro ao salvar: {e}")
        return False

# --- FLUXO PRINCIPAL ---
if github_token and repo_name:
    
    # Estrutura exata solicitada pelo usuário
    colunas_matriz = ["Código", "Descrição", "Métrica", "Quantidade", "Rua_Endereco"]
    colunas_mov = ["Data_Hora", "Código", "Descrição", "Tipo", "Quantidade", "Métrica", "Rua_Endereco", "Operador"]
    
    df_insumos, sha_matriz = carregar_excel(github_token, repo_name, caminho_matriz, colunas_matriz)
    df_movimentos, sha_movimentos = carregar_excel(github_token, repo_name, caminho_movimentacao, colunas_mov)

    if not df_insumos.empty:
        
        aba_mapa, aba_movimentar, aba_ia = st.tabs(["🛣️ Mapa por Ruas (WMS)", "🔄 Entradas e Saídas", "🤖 Assistente IA"])
        
        # --- ABA 1: MAPA DE RUAS ---
        with aba_mapa:
            st.subheader("📍 Filtro de Ocupação por Estrutura")
            
            # Captura todas as ruas únicas cadastradas para criar um filtro dinâmico
            ruas_disponiveis = sorted(df_insumos["Rua_Endereco"].dropna().unique())
            rua_selecionada = st.selectbox("Selecione a Rua para inspecionar o Porta-Paletes:", ["Todas"] + ruas_disponiveis)
            
            if rua_selecionada == "Todas":
                df_filtrado = df_insumos
            else:
                df_filtrado = df_insumos[df_insumos["Rua_Endereco"] == rua_selecionada]
                
            st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
            
            # Mini Gráfico de Barras mostrando quantos itens tem em cada rua
            st.subheader("📊 Quantidade Total de Insumos por Rua")
            if "Rua_Endereco" in df_insumos.columns and not df_insumos.empty:
                grafico_data = df_insumos.groupby("Rua_Endereco")["Quantidade"].sum()
                st.bar_chart(grafico_data)

        # --- ABA 2: MOVIMENTAÇÃO ---
        with aba_movimentar:
            st.subheader("Registrar Fluxo de Insumos")
            
            item_selecionado = st.selectbox("Selecione o Item pela Descrição:", df_insumos["Descrição"].unique())
            idx = df_insumos[df_insumos["Descrição"] == item_selecionado].index[0]
            
            # Puxa os dados atuais do item selecionado
            codigo_item = df_insumos.loc[idx, "Código"]
            metrica_item = df_insumos.loc[idx, "Métrica"]
            qtd_atual = df_insumos.loc[idx, "Quantidade"]
            rua_atual = df_insumos.loc[idx, "Rua_Endereco"]
            
            # Mostra um card informativo pro operador não errar
            st.warning(f"ℹ️ Código: {codigo_item} | Unidade: {metrica_item} | Estoque Atual: {qtd_atual} | Posição: {rua_atual}")
            
            col1, col2 = st.columns(2)
            with col1:
                tipo_op = st.radio("Tipo de Movimentação:", ["ENTRADA", "SAÍDA"])
                quantidade_op = st.number_input("Quantidade:", min_value=1, step=1)
            with col2:
                operador = st.text_input("Nome do Operador:", value="Almoxarife")
                nova_rua = st.text_input("Atualizar Localização (Rua/Módulo/Nível):", value=str(rua_atual))
                
            if st.button("Confirmar Lançamento"):
                if tipo_op == "SAÍDA" and qtd_atual < quantidade_op:
                    st.error("Saldo insuficiente para realizar essa saída!")
                else:
                    # Atualiza valores
                    if tipo_op == "ENTRADA":
                        df_insumos.loc[idx, "Quantidade"] = qtd_atual + quantidade_op
                    else:
                        df_insumos.loc[idx, "Quantidade"] = qtd_atual - quantidade_op
                        
                    df_insumos.loc[idx, "Rua_Endereco"] = nova_rua
                    
                    # Salva histórico
                    novo_registro = {
                        "Data_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Código": codigo_item,
                        "Descrição": item_selecionado,
                        "Tipo": tipo_op,
                        "Quantidade": quantidade_op,
                        "Métrica": metrica_item,
                        "Rua_Endereco": nova_rua,
                        "Operador": operador
                    }
                    df_movimentos = pd.concat([df_movimentos, pd.DataFrame([novo_registro])], ignore_index=True)
                    
                    # Sincroniza com o GitHub
                    if salvar_excel(github_token, repo_name, caminho_matriz, df_insumos, sha_matriz, f"Ajuste {item_selecionado}") and \
                       salvar_excel(github_token, repo_name, caminho_movimentacao, df_movimentos, sha_movimentos, f"Reg {tipo_op}"):
                        st.success("Planilhas atualizadas com sucesso!")
                        st.rerun()

        # --- ABA 3: IA ---
        with aba_ia:
            st.subheader("🤖 Consultora de Logística IA")
            if ai_key:
                pergunta = st.text_input("Ex: Quais caixas estão guardadas na Rua A? / Faça um resumo das saídas de hoje.")
                if st.button("Perguntar à IA") and pergunta:
                    with st.spinner("Analisando as ruas e estruturas..."):
                        try:
                            client = genai.Client(api_key=api_key)
                            prompt = f"""
                            Você gerencia o estoque e endereçamento de um porta-paletes organizado por ruas.
                            Métrica indica o tipo de embalagem (unidade, caixa, pacote).
                            
                            ESTOQUE ATUAL:
                            {df_insumos.to_string(index=False)}
                            
                            HISTÓRICO:
                            {df_movimentos.to_string(index=False)}
                            
                            Responda com precisão logística à pergunta: {pergunta}
                            """
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                            st.info("Resposta:")
                            st.markdown(response.text)
                        except Exception as e:
                            st.error(f"Erro na IA: {e}")
            else:
                st.warning("Insira a Gemini API Key para habilitar a busca inteligente.")
    else:
        st.error(f"O arquivo 'insumos.xlsx' na pasta '{pasta_input}' está vazio ou não foi encontrado.")
        st.info("💡 Suba um arquivo Excel contendo exatamente os cabeçalhos: Código, Descrição, Métrica, Quantidade, Rua_Endereco")
else:
    st.info("👋 Forneça o token e o nome do repositório na barra lateral para carregar o seu WMS.")
