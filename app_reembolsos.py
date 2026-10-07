import streamlit as st
import pandas as pd
from datetime import datetime
import telebot
import threading
import re
import speech_recognition as sr
import soundfile as sf
import os
import math
from io import BytesIO
from supabase import create_client, Client

# ==========================================
# CONFIGURAÇÃO DO SITE E LOGIN
# ==========================================
st.set_page_config(page_title="Reembolsos Pro", page_icon="💼", layout="wide")

# NOVOS PERFIS DE ACESSO (Hierarquia)
USUARIOS = {
    "admin": {"senha": "1234", "perfil": "admin"},
    "diretoria": {"senha": "senha123", "perfil": "admin"},
    "joao": {"senha": "111", "perfil": "funcionario"},
    "maria": {"senha": "222", "perfil": "funcionario"}
}

TOKEN_TELEGRAM = "8757149338:AAFfMQWLBeskQIJ5NjS4684yMw7XO86B5Hk"

# ==========================================
# LIGAÇÃO À NUVEM (SUPABASE)
# ==========================================
SUPABASE_URL = "https://mzifdgzwqgdnsnghpnnd.supabase.co"
SUPABASE_KEY = "sb_publishable_BHRYDfhc38whSvbdpUzhXA_at6W0nhQ"

@st.cache_resource
def iniciar_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = iniciar_supabase()

# ==========================================
# ROBÔ DO TELEGRAM
# ==========================================
@st.cache_resource
def iniciar_robo():
    bot = telebot.TeleBot(TOKEN_TELEGRAM)

    def processar_telegram(texto, message):
        match = re.search(r'\d+(?:[.,]\d+)?', texto)
        if match:
            valor = float(match.group().replace(',', '.'))
            desc = texto.replace(match.group(), "")
            for p in ["gastei", "comprei", "com", "no", "na", "de", "reais", "r$", "deu"]:
                desc = desc.replace(f" {p} ", " ").replace(f"^{p} ", "").strip()
            
            desc_final = desc.strip().capitalize() or "Despesa via Telegram"
            
            if any(x in desc for x in ['estadia', 'hotel', 'hospedagem']): cat = "Hospedagem"
            elif any(x in desc for x in ['refeição', 'mercado', 'almoço', 'jantar', 'ifood']): cat = "Alimentação"
            elif any(x in desc for x in ['uber', 'taxi', 'táxi', 'ônibus', 'pedágio']): cat = "Transporte"
            else: cat = "Outros"
            
            data_hoje = datetime.now().strftime("%d/%m/%Y")
            
            supabase.table("despesas").insert({
                "data": data_hoje, "valor": valor, "categoria": cat, 
                "descricao": desc_final, "anexo": "Via Telegram", 
                "status": "Pendente", "tipo_gasto": "Pessoal",
                "usuario": "admin" # Padrão do Telegram vai para a conta admin
            }).execute()
            
            bot.reply_to(message, f"✅ Anotado!\nR$ {valor:.2f} com '{desc_final}' salvo.")
        else:
            bot.reply_to(message, "🤔 Não encontrei um valor. Ex: 'Gastei 150 com mercado'")

    @bot.message_handler(content_types=['text'])
    def receber_msg(message):
        processar_telegram(message.text.lower(), message)

    @bot.message_handler(content_types=['voice', 'audio'])
    def receber_audio(message):
        try:
            bot.reply_to(message, "🎧 A ouvir...")
            file_id = message.voice.file_id if message.content_type == 'voice' else message.audio.file_id
            file_info = bot.get_file(file_id)
            downloaded = bot.download_file(file_info.file_path)
            
            with open("temp_voz.ogg", 'wb') as f: f.write(downloaded)
            data, samplerate = sf.read("temp_voz.ogg")
            sf.write("temp_voz.wav", data, samplerate)
            
            r = sr.Recognizer()
            with sr.AudioFile("temp_voz.wav") as source:
                audio_data = r.record(source)
                texto = r.recognize_google(audio_data, language="pt-BR")
                
            bot.reply_to(message, f"🗣️ Ouvi: '{texto}'")
            processar_telegram(texto.lower(), message)
        except Exception as e:
            bot.reply_to(message, "❌ Erro ao ler áudio.")
        finally:
            if os.path.exists("temp_voz.ogg"): os.remove("temp_voz.ogg")
            if os.path.exists("temp_voz.wav"): os.remove("temp_voz.wav")

    def run_bot():
        try: bot.infinity_polling()
        except: pass

    threading.Thread(target=run_bot, daemon=True).start()
    return bot

iniciar_robo() 

# ==========================================
# VERIFICAÇÃO DE LOGIN E PERFIL
# ==========================================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario_atual = ""
    st.session_state.perfil = ""

if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>💼 Reembolsos Pro</h1>", unsafe_allow_html=True)
        st.markdown("<h4 style='text-align: center; color: gray;'>Acesso ao Sistema</h4>", unsafe_allow_html=True)
        st.write("")
        
        with st.form("form_login"):
            usuario = st.text_input("Utilizador", placeholder="Digite o seu utilizador")
            senha = st.text_input("Palavra-passe", type="password", placeholder="Digite a sua palavra-passe")
            submit = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if submit:
                if usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha:
                    st.session_state.logado = True
                    st.session_state.usuario_atual = usuario
                    st.session_state.perfil = USUARIOS[usuario]["perfil"]
                    st.rerun() 
                else:
                    st.error("❌ Utilizador ou palavra-passe incorretos!")
                    
else:
    # ==========================================
    # INTERFACE DO SITE
    # ==========================================
    st.sidebar.title("💼 Reembolsos Pro")
    st.sidebar.markdown(f"**👤 Utilizador:** `{st.session_state.usuario_atual}` ({st.session_state.perfil.upper()})")
    
    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state.logado = False
        st.session_state.usuario_atual = ""
        st.session_state.perfil = ""
        st.rerun()
        
    st.sidebar.markdown("---")
    
    # Bloquear menu de configurações para funcionários
    opcoes_menu = ["➕ Novo Registo", "📊 Histórico e Painel"]
    if st.session_state.perfil == "admin":
        opcoes_menu.append("⚙️ Configurações")
        
    menu = st.sidebar.radio("Navegação", opcoes_menu)

    if menu == "➕ Novo Registo":
        st.header("Registar Nova Despesa")
        
        # Funcionário não escolhe onde guardar, vai direto para a sua conta
        if st.session_state.perfil == "admin":
            tipo_bd = st.radio("Onde guardar?", ["👤 Gastos de Funcionários", "🏢 Gasto da Empresa"])
            tipo_bd_str = "Pessoal" if "Funcionários" in tipo_bd else "Empresa"
        else:
            st.info(f"A registar na conta pessoal de {st.session_state.usuario_atual.capitalize()}")
            tipo_bd_str = "Pessoal"
        
        with st.form("form_cadastro", clear_on_submit=True):
            col1, col2 = st.columns(2)
            data_input = col1.date_input("Data da Despesa", format="DD/MM/YYYY")
            valor_input = col2.number_input("Valor (R$)", min_value=0.01, format="%.2f")
            
            col3, col4 = st.columns(2)
            cat_input = col3.selectbox("Categoria", ["Alimentação", "Transporte", "Hospedagem", "Equipamento", "Moradia", "Outros"])
            anexo_input = col4.file_uploader("Comprovativo (Opcional)", type=['png', 'jpg', 'pdf'])
            
            desc_input = st.text_input("Descrição Breve", placeholder="Ex: Almoço com cliente...")
            
            submit = st.form_submit_button("✔ Guardar Despesa", use_container_width=True)
            
            if submit:
                data_str = data_input.strftime("%d/%m/%Y")
                nome_anexo = anexo_input.name if anexo_input else "Sem anexo"
                
                supabase.table("despesas").insert({
                    "data": data_str, "valor": valor_input, "categoria": cat_input, 
                    "descricao": desc_input, "anexo": nome_anexo, 
                    "status": "Pendente", "tipo_gasto": tipo_bd_str,
                    "usuario": st.session_state.usuario_atual
                }).execute()
                st.success("✅ Gasto registado com sucesso!")

    elif menu == "📊 Histórico e Painel":
        st.header("Painel de Controlo")
        
        if st.session_state.perfil == "admin":
            aba_pessoal, aba_empresa = st.tabs(["👤 Gastos dos Funcionários", "🏢 Gastos da Empresa"])
            abas = [(aba_pessoal, "Pessoal"), (aba_empresa, "Empresa")]
        else:
            aba_unica, = st.tabs(["👤 Os Meus Gastos"])
            abas = [(aba_unica, "Pessoal")]
        
        for aba, tipo_filtro in abas:
            with aba:
                # O funcionário só carrega os seus próprios dados
                query = supabase.table("despesas").select("id, data, categoria, descricao, valor, status, usuario").eq("tipo_gasto", tipo_filtro)
                if st.session_state.perfil == "funcionario":
                    query = query.eq("usuario", st.session_state.usuario_atual)
                    
                resposta = query.execute()
                df = pd.DataFrame(resposta.data)
                
                if not df.empty:
                    df['valor'] = pd.to_numeric(df['valor'])
                    df['data_ordem'] = pd.to_datetime(df['data'], format='%d/%m/%Y', errors='coerce')
                    df['mes_ano'] = df['data_ordem'].dt.strftime('%m/%Y').fillna("Sem Data")
                    
                    lista_meses = sorted([m for m in df['mes_ano'].unique() if m != "Sem Data"], reverse=True)
                    opcoes_filtro = ["Todos os Meses"] + lista_meses
                    
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        mes_selecionado = st.selectbox(f"📅 Filtrar por Mês", opcoes_filtro, key=f"mes_{tipo_filtro}")
                    
                    df_filtrado = df.copy()
                    
                    # Filtro extra exclusivo para os Admins procurarem por um funcionário específico
                    if st.session_state.perfil == "admin" and tipo_filtro == "Pessoal":
                        with col_f2:
                            lista_usuarios = ["Todos"] + list(df['usuario'].dropna().unique())
                            usr_selecionado = st.selectbox(f"👤 Filtrar por Funcionário", lista_usuarios, key=f"usr_{tipo_filtro}")
                            if usr_selecionado != "Todos":
                                df_filtrado = df_filtrado[df_filtrado['usuario'] == usr_selecionado]
                    
                    if mes_selecionado != "Todos os Meses":
                        df_filtrado = df_filtrado[df_filtrado['mes_ano'] == mes_selecionado]
                    
                    if not df_filtrado.empty:
                        total = df_filtrado['valor'].sum()
                        tot_alim = df_filtrado[df_filtrado['categoria'] == 'Alimentação']['valor'].sum()
                        tot_hosp = df_filtrado[df_filtrado['categoria'] == 'Hospedagem']['valor'].sum()
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Gasto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        c2.metric("Alimentação", f"R$ {tot_alim:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        c3.metric("Hospedagem", f"R$ {tot_hosp:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        
                        st.markdown("---")
                        st.subheader("📈 Análise de Gastos")
                        col_graf1, col_graf2 = st.columns(2)
                        
                        with col_graf1:
                            st.markdown("**Despesas por Categoria**")
                            df_cat = df_filtrado.groupby("categoria")["valor"].sum().reset_index()
                            st.bar_chart(df_cat.set_index("categoria"))
                            
                        with col_graf2:
                            st.markdown("**Evolução Diária**")
                            df_data = df_filtrado.groupby("data")["valor"].sum().reset_index()
                            df_data['data_dt'] = pd.to_datetime(df_data['data'], format='%d/%m/%Y', errors='coerce')
                            df_data = df_data.dropna(subset=['data_dt']).sort_values('data_dt')
                            st.line_chart(df_data.set_index("data")["valor"])
                            
                        st.markdown("---")
                        
                        # Esconder colunas técnicas
                        df_exibicao = df_filtrado.drop(columns=['data_ordem', 'mes_ano'], errors='ignore')
                        if st.session_state.perfil == "funcionario" and 'status' in df_exibicao.columns:
                            df_exibicao = df_exibicao.drop(columns=['status'])
                            
                        # Colocar a coluna do utilizador em primeiro lugar
                        if 'usuario' in df_exibicao.columns:
                            cols = ['usuario'] + [c for c in df_exibicao.columns if c != 'usuario']
                            df_exibicao = df_exibicao[cols]
                        
                        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
                        
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_exibicao.to_excel(writer, index=False, sheet_name=tipo_filtro)
                        planilha_pronta = output.getvalue()
                        nome_excel = f"Relatorio_{tipo_filtro}_{mes_selecionado.replace('/', '-')}.xlsx"
                        st.download_button(label=f"📊 Descarregar Planilha Excel", data=planilha_pronta, file_name=nome_excel, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    else:
                        st.info("Sem dados para os filtros selecionados.")
                else:
                    st.info("Nenhuma despesa registada nesta categoria.")

    elif menu == "⚙️ Configurações" and st.session_state.perfil == "admin":
        st.header("Gestão do Sistema")
        
        st.subheader("📥 Importar Planilha da Empresa")
        arquivo_up = st.file_uploader("Selecione a planilha Excel", type=['xlsx', 'xls'])
        if arquivo_up:
            if st.button("Importar Dados"):
                try:
                    df_imp = pd.read_excel(arquivo_up, header=None)
                    resposta_existentes = supabase.table("despesas").select("data, valor, descricao").eq("tipo_gasto", "Empresa").execute()
                    existentes = set()
                    for r in resposta_existentes.data:
                        try: existentes.add((str(r['data']), float(r['valor']), str(r['descricao']).strip()))
                        except: pass

                    novos_registos = []
                    duplicados = 0
                    
                    for i, row in df_imp.iterrows():
                        vals = [str(x).upper().strip() for x in row.values]
                        if "DATA" in vals and "VALORES" in vals:
                            c_data = vals.index("DATA")
                            c_tipo = vals.index("TIPO") if "TIPO" in vals else 3
                            c_desc = vals.index("DESCRIÇÃO") if "DESCRIÇÃO" in vals else 5
                            c_val = vals.index("VALORES")
                            
                            for _, linha in df_imp.iloc[i+1:].iterrows():
                                try:
                                    v = float(linha.iloc[c_val])
                                    if math.isnan(v) or v <= 0: continue
                                    d = linha.iloc[c_data]
                                    data_str = d.strftime("%d/%m/%Y") if hasattr(d, 'strftime') else str(d)[:10]
                                    desc = str(linha.iloc[c_desc]) if not pd.isna(linha.iloc[c_desc]) else ""
                                    cat = str(linha.iloc[c_tipo]) if not pd.isna(linha.iloc[c_tipo]) else "Outros"
                                    
                                    if (data_str, v, desc.strip()) in existentes:
                                        duplicados += 1
                                        continue
                                        
                                    novos_registos.append({
                                        "data": data_str, "valor": v, "categoria": cat, 
                                        "descricao": desc, "anexo": "Planilha", 
                                        "status": "Pendente", "tipo_gasto": "Empresa",
                                        "usuario": "admin"
                                    })
                                    existentes.add((data_str, v, desc.strip()))
                                except: continue
                            break
                            
                    if novos_registos:
                        supabase.table("despesas").insert(novos_registos).execute()
                    
                    msg = f"✅ {len(novos_registos)} registos importados para a Empresa!"
                    if duplicados > 0: msg += f" ({duplicados} repetidos ignorados)."
                    st.success(msg)
                except Exception as e:
                    st.error(f"Erro ao importar: {e}")

        st.markdown("---")
        st.subheader("🗑️ Apagar Registo Específico")
        id_apagar = st.number_input("Digite o ID do registo para apagar:", min_value=0, step=1)
        if st.button("Apagar ID"):
            supabase.table("despesas").delete().eq("id", id_apagar).execute()
            st.warning(f"Registo {id_apagar} apagado.")

        st.markdown("---")
        st.subheader("🧹 Limpeza Geral")
        aba_limpar = st.selectbox("Qual base de dados deseja ZERAR?", ["Nenhuma", "👤 Pessoal (Funcionários)", "🏢 Empresa"])
        if aba_limpar != "Nenhuma":
            st.error("⚠️ Atenção: Isto não pode ser desfeito!")
            if st.button(f"🗑️ SIM, APAGAR TUDO DE {aba_limpar}"):
                filtro_db = "Pessoal" if "Pessoal" in aba_limpar else "Empresa"
                supabase.table("despesas").delete().eq("tipo_gasto", filtro_db).execute()
                st.success(f"Base '{filtro_db}' zerada com sucesso!")
