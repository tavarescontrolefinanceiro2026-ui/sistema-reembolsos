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

USUARIOS_PERMITIDOS = {
    "admin": "1234",
    "diretoria": "senha123"
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
            
            # Guardar na Supabase
            supabase.table("despesas").insert({
                "data": data_hoje, "valor": valor, "categoria": cat, 
                "descricao": desc_final, "anexo": "Via Telegram", 
                "status": "Pendente", "tipo_gasto": "Pessoal"
            }).execute()
            
            bot.reply_to(message, f"✅ Anotado!\nR$ {valor:.2f} com '{desc_final}' salvo no Pessoal.")
        else:
            bot.reply_to(message, "🤔 Não encontrei um valor. Ex: 'Gastei 150 com mercado'")

    @bot.message_handler(content_types=['text'])
    def receber_msg(message):
        processar_telegram(message.text.lower(), message)

    @bot.message_handler(content_types=['voice', 'audio'])
    def receber_audio(message):
        try:
            bot.reply_to(message, "🎧 Ouvindo...")
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
# VERIFICAÇÃO DE LOGIN
# ==========================================
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.usuario_atual = ""

if not st.session_state.logado:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>💼 Reembolsos Pro</h1>", unsafe_allow_html=True)
        st.markdown("<h4 style='text-align: center; color: gray;'>Acesso Restrito (Nuvem)</h4>", unsafe_allow_html=True)
        st.write("")
        
        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite o seu utilizador")
            senha = st.text_input("Palavra-passe", type="password", placeholder="Digite a sua palavra-passe")
            submit = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if submit:
                if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == senha:
                    st.session_state.logado = True
                    st.session_state.usuario_atual = usuario
                    st.rerun() 
                else:
                    st.error("❌ Utilizador ou palavra-passe incorretos!")
                    
else:
    # ==========================================
    # INTERFACE DO SITE
    # ==========================================
    st.sidebar.title("💼 Reembolsos Pro")
    st.sidebar.markdown(f"**👤 Utilizador:** `{st.session_state.usuario_atual}`")
    
    if st.sidebar.button("🚪 Sair do Sistema"):
        st.session_state.logado = False
        st.session_state.usuario_atual = ""
        st.rerun()
        
    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Navegação", ["➕ Novo Cadastro", "📊 Histórico e Painel", "⚙️ Configurações"])

    if menu == "➕ Novo Cadastro":
        st.header("Registar Nova Despesa")
        
        tipo_bd = st.radio("Onde guardar?", ["👤 O Meu Gasto (Pessoal)", "🏢 Gasto da Empresa"])
        tipo_bd_str = "Pessoal" if "Pessoal" in tipo_bd else "Empresa"
        
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
                    "status": "Pendente", "tipo_gasto": tipo_bd_str
                }).execute()
                st.success("✅ Gasto guardado na nuvem com sucesso!")

    elif menu == "📊 Histórico e Painel":
        st.header("Painel de Controlo")
        
        aba_pessoal, aba_empresa = st.tabs(["👤 Os Meus Gastos (Pessoal)", "🏢 Gastos da Empresa"])
        
        for aba, tipo_filtro in zip([aba_pessoal, aba_empresa], ["Pessoal", "Empresa"]):
            with aba:
                resposta = supabase.table("despesas").select("id, data, categoria, descricao, valor, status").eq("tipo_gasto", tipo_filtro).execute()
                df = pd.DataFrame(resposta.data)
                
                if not df.empty:
                    df['valor'] = pd.to_numeric(df['valor'])
                    
                    total = df['valor'].sum()
                    tot_alim = df[df['categoria'] == 'Alimentação']['valor'].sum()
                    tot_hosp = df[df['categoria'] == 'Hospedagem']['valor'].sum()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Gasto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    c2.metric("Alimentação", f"R$ {tot_alim:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    c3.metric("Hospedagem", f"R$ {tot_hosp:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    
                    st.markdown("---")
                    
                    st.subheader("📈 Análise de Gastos")
                    col_graf1, col_graf2 = st.columns(2)
                    
                    with col_graf1:
                        st.markdown("**Despesas por Categoria**")
                        df_cat = df.groupby("categoria")["valor"].sum().reset_index()
                        st.bar_chart(df_cat.set_index("categoria"))
                        
                    with col_graf2:
                        st.markdown("**Evolução Diária**")
                        df_data = df.groupby("data")["valor"].sum().reset_index()
                        df_data['data_ordem'] = pd.to_datetime(df_data['data'], format='%d/%m/%Y', errors='coerce')
                        df_data = df_data.dropna(subset=['data_ordem']).sort_values('data_ordem')
                        st.line_chart(df_data.set_index("data")["valor"])
                        
                    st.markdown("---")
                    
                    if tipo_filtro == "Pessoal":
                        df_exibicao = df.drop(columns=['status'], errors='ignore')
                    else:
                        df_exibicao = df.copy()
                    
                    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)
                    
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_exibicao.to_excel(writer, index=False, sheet_name=tipo_filtro)
                    planilha_pronta = output.getvalue()
                    
                    st.download_button(label=f"📊 Descarregar Planilha Excel ({tipo_filtro})", data=planilha_pronta, file_name=f"Relatorio_{tipo_filtro}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.info("Nenhuma despesa registada nesta categoria.")

    elif menu == "⚙️ Configurações":
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
                                        "status": "Pendente", "tipo_gasto": "Empresa"
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
        aba_limpar = st.selectbox("Qual base de dados deseja ZERAR?", ["Nenhuma", "👤 Pessoal", "🏢 Empresa"])
        if aba_limpar != "Nenhuma":
            st.error("⚠️ Atenção: Isto não pode ser desfeito!")
            if st.button(f"🗑️ SIM, APAGAR TUDO DE {aba_limpar}"):
                filtro_db = "Pessoal" if "Pessoal" in aba_limpar else "Empresa"
                supabase.table("despesas").delete().eq("tipo_gasto", filtro_db).execute()
                st.success(f"Base '{filtro_db}' zerada com sucesso!")