import streamlit as st
import pandas as pd
from google import genai
import io
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="LogiStock Local Pro", page_icon="📦", layout="wide")
st.title("📦 LogiStock: Gestão de Insumos & Endereçamento Local")

# --- CONEXÃO COM O GEMINI VIA SECRETS ---
try:
    ai_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=ai_key)
except Exception:
    st.error("⚠️ Erro: A chave 'GEMINI_API_KEY' não foi encontrada nos Secrets do Streamlit Cloud.")
    st.stop()

# --- SIDEBAR: CARREGAMENTO DA PLANILHA LOCAL ---
with st.sidebar:
    st.header("📂 Arquivo Local da Máquina")
    st.write("Suba a planilha do seu computador para começar. Ao final das operações, você poderá baixá-la atualizada.")
    
    arquivo_up = st.file_uploader("Selecione a planilha insumos.xlsx de sua máquina:", type=["xlsx"])

# --- ESTRUTURA PADRÃO DE COLUNAS ---
colunas_matriz = ["Código", "Descrição", "Métrica", "Quantidade", "Rua_Endereco"]
colunas_mov = ["Data_Hora", "Código", "Descrição", "Tipo", "Quantidade", "Métrica", "Rua_Endereco", "Operador"]

df_insumos = pd.DataFrame(columns=colunas_matriz)
df_movimentos = pd.DataFrame(columns=colunas_mov)
pronto_para_rodar = False

# --- CONTROLE DE SESSÃO PARA MANTER OS DADOS NA MEMÓRIA ---
if arquivo_up is not None:
    try:
        if 'df_insumos_local' not in st.session_state:
            df_carregado = pd.read_excel(arquivo_up)
            if all(col in df_carregado.columns for col in colunas_matriz):
                st.session_state['df_insumos_local'] = df_carregado
            else:
                st.error(f"A planilha precisa conter exatamente as colunas: {colunas_matriz}")
                st.stop()
        
        if 'df_movimentos_local' not in st.session_state:
            st.session_state['df_movimentos_local'] = pd.DataFrame(columns=colunas_mov)
            
        df_insumos = st.session_state['df_insumos_local']
        df_movimentos = st.session_state['df_movimentos_local']
        pronto_para_rodar = True
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")

# --- EXECUÇÃO DO APLICATIVO ---
if pronto_para_rodar:
    
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

    # --- ABA 2: MOVIMENTAÇÃO (AGORA COM CARDS E GRÁFICO DE ROTATIVIDADE) ---
    with aba_movimentar:
        st.subheader("📊 Painel de Rotatividade e Fluxo de Estoque")
        
        # Filtrar apenas as saídas para calcular a rotatividade real (Giro de Estoque)
        df_saidas = df_movimentos[df_movimentos["Tipo"] == "SAÍDA"]
        
        # Cálculo dos indicadores para os Cards
        total_movimentado = len(df_movimentos)
        total_pecas_saida = df_saidas["Quantidade"].sum() if not df_saidas.empty else 0
        
        if not df_saidas.empty:
            # Encontra o item com maior quantidade acumulada de saídas
            mais_rodado_serie = df_saidas.groupby("Descrição")["Quantidade"].sum()
            item_mais_rodado = mais_rodado_serie.idxmax()
            qtd_mais_rodado = mais_rodado_serie.max()
        else:
            item_mais_rodado = "Nenhum"
            qtd_mais_rodado = 0
            
        # Exibição dos Cards Gerenciais
        card1, card2, card3 = st.columns(3)
        card1.metric(label="Total de Operações Realizadas", value=total_movimentado)
        card2.metric(label="Total de Insumos Despachados (Saídas)", value=f"{total_pecas_saida} un/cx")
        card3.metric(label="Insumo de Maior Rotatividade", value=str(item_mais_rodado), delta=f"{qtd_mais_rodado} saídas")
        
        st.write("---")
        
        # Gráfico de Rotatividade (Ranking de Saídas)
        if not df_saidas.empty:
            st.subheader("🔥 Ranking de Rotatividade (Insumos Mais Retirados)")
            # Agrupa por item, soma as saídas e ordena do maior para o menor
            dados_ranking = df_saidas.groupby("Descrição")["Quantidade"].sum().sort_values(ascending=False)
            st.bar_chart(dados_ranking)
        else:
            st.info("💡 O gráfico de rotatividade aparecerá aqui assim que a primeira 'SAÍDA' for registrada nesta sessão.")
            
        st.write("---")
        st.subheader("🔄 Registrar Nova Movimentação")
        
        item_selecionado = st.selectbox("Escolha o Insumo para Movimentar:", df_insumos["Descrição"].unique(), key="mov_item")
        idx = df_insumos[df_insumos["Descrição"] == item_selecionado].index[0]
        
        cod = df_insumos.loc[idx, "Código"]
        met = df_insumos.loc[idx, "Métrica"]
        qtd = df_insumos.loc[idx, "Quantidade"]
        rua = df_insumos.loc[idx, "Rua_Endereco"]
        
        st.warning(f"ℹ️ Código: {cod} | Tipo: {met} | Saldo Atual: {qtd} | Endereço Atual: {rua}")
        
        col1, col2 = st.columns(2)
        with col1:
            tipo_op = st.radio("Operação:", ["ENTRADA", "SAÍDA"])
            quantidade_op = st.number_input("Quantidade:", min_value=1, step=1)
        with col2:
            operador = st.text_input("Nome do Operador:", value="Almoxarife", key="mov_op")
            
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
                    "Operador": operador
                }
                st.session_state['df_movimentos_local'] = pd.concat([st.session_state['df_movimentos_local'], pd.DataFrame([novo_reg])], ignore_index=True)
                st.success("Movimentação registrada com sucesso na memória do app!")
                st.rerun()

    # --- ABA 3: INSERÇÃO E ATUALIZAÇÃO DE ENDEREÇO VIA SISTEMA ---
    with aba_enderecar:
        st.subheader("📍 Atribuição de Endereço no Porta-Paletes")
        st.write("Utilize esta ferramenta para organizar ou mudar a rua/posição de um item no estoque.")
        
        item_selecionado_end = st.selectbox("Selecione o Insumo para Endereçar:", df_insumos["Descrição"].unique(), key="end_item")
        idx_end = df_insumos[df_insumos["Descrição"] == item_selecionado_end].index[0]
        
        rua_atual_end = df_insumos.loc[idx_end, "Rua_Endereco"]
        st.info(f"O item **{item_selecionado_end}** está atualmente localizado na: `{rua_atual_end}`")
        
        col_end1, col_end2 = st.columns(2)
        with col_end1:
            rua_nova = st.text_input("Rua (Ex: Rua A, Rua B):", value=str(rua_atual_end))
        with col_end2:
            operador_end = st.text_input("Nome do Operador:", value="Almoxarife", key="end_op")
            
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
                "Operador": operador_end
            }
            st.session_state['df_movimentos_local'] = pd.concat([st.session_state['df_movimentos_local'], pd.DataFrame([novo_reg_end])], ignore_index=True)
            st.success(f"📍 Sucesso! Novo endereço de '{item_selecionado_end}' definido para '{rua_nova}'.")
            st.rerun()

    # --- SEÇÃO DE SALVAMENTO PARA DOWNLOAD ---
    st.write("---")
    st.subheader("💾 Salvar Alterações na Máquina Local")
    
    buffer_download = io.BytesIO()
    with pd.ExcelWriter(buffer_download, engine='openpyxl') as writer:
        st.session_state['df_insumos_local'].to_excel(writer, index=False)
    
    st.download_button(
        label="📥 Baixar Planilha Atualizada (.xlsx)",
        data=buffer_download.getvalue(),
        file_name="insumos_atualizado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- ABA 4: INTELIGÊNCIA ARTIFICIAL (ENVIO COM ENTER E APENAS TEXTO) ---
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

                    HISTÓRICO RECENTE:
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
