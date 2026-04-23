import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import json
import os
import pytz
import gspread
from google.oauth2.service_account import Credentials

# --- 0. TIMEZONE SETUP ---
TZ = pytz.timezone('Asia/Jakarta')

def get_now_jkt():
    return datetime.now(TZ).replace(tzinfo=None)

st.set_page_config(page_title="Factory Scheduler V15 - GSheets Cloud", layout="wide")

# --- 1. GOOGLE SHEETS SETUP ---
SHEET_NAME = "Factory_Scheduler_DB"

def get_gspread_client():
    path = os.path.join(os.path.dirname(__file__), "service_account.json")
    if os.path.exists(path):
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return gspread.authorize(Credentials.from_service_account_file(path, scopes=scopes))
    try:
        if "gcp_service_account" in st.secrets:
            return gspread.authorize(Credentials.from_service_account_info(st.secrets["gcp_service_account"]))
    except: pass
    st.error("❌ Credentials tidak ditemukan!")
    st.stop()

def get_worksheet(name):
    try:
        client = get_gspread_client()
        sh = client.open(SHEET_NAME)
        try:
            return sh.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            return sh.add_worksheet(title=name, rows="100", cols="20")
    except Exception as e:
        if "PERMISSION_DENIED" in str(e):
            st.error("❌ Akses Ditolak! Share GSheet ke email Service Account.")
        elif "API_DISABLED" in str(e):
            st.error("❌ API Belum Aktif di Google Cloud.")
        else:
            st.error(f"⚠️ Error Koneksi: {e}")
        st.stop()

def save_to_db(data):
    try:
        ws = get_worksheet("ProductionData")
        ws.clear()
        headers = ["Batch Name", "Plan Start Pre-heat", "End Post-heat", "Dur. Pre-heat", "Cast Duration", "Dur. Post-heat", "Mode JIT", "Status Locked", "Padding", "Technical_Data_JSON"]
        rows = [headers]
        for item in data:
            p_start = item['plan_start_pre'].isoformat() if isinstance(item['plan_start_pre'], datetime) else str(item['plan_start_pre'])
            end_post_str = "-"
            if item.get('fixed_data'):
                end_dt = item['fixed_data'][2]['Finish']
                end_post_str = end_dt.strftime("%H:%M (%d/%m)")
            def handler(x): return x.isoformat() if isinstance(x, datetime) else None
            fixed_json = json.dumps(item.get('fixed_data'), default=handler)
            rows.append([item.get('batch', ''), p_start, end_post_str, item.get('d_pre', 12), item.get('cast', 0), item.get('d_post', 33), str(item.get('jit', True)), str(item.get('locked', False)), item.get('padding', 1), fixed_json])
        ws.update('A1', rows)
        ws.format("A:J", {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"})
        ws.format("A1:J1", {"textFormat": {"bold": True}})
        try: ws.columns_auto_resize(0, 9)
        except: pass
    except Exception as e: st.error(f"Gagal simpan ke GSheets: {e}")

def save_settings(settings):
    try:
        ws = get_worksheet("Settings")
        ws.clear()
        rows = [["Setting Name", "Value"]]
        for k, v in settings.items():
            val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            rows.append([k, val])
        ws.update('A1', rows)
        ws.format("A:B", {"horizontalAlignment": "CENTER"})
        ws.format("A1:B1", {"textFormat": {"bold": True}})
        try: ws.columns_auto_resize(0, 1)
        except: pass
    except Exception as e: st.error(f"Gagal simpan settings: {e}")

def save_finished_batches(data):
    try:
        ws = get_worksheet("FinishedBatches")
        ws.clear()
        headers = ["Nama Batch", "Status Batch", "Status Proses"]
        rows = [headers]
        for item in data:
            rows.append([item.get("Nama Batch", ""), item.get("Status Batch", ""), item.get("Status Proses", "")])
        ws.update('A1', rows)
        ws.format("A:C", {"horizontalAlignment": "CENTER"})
        ws.format("A1:C1", {"textFormat": {"bold": True}})
        try: ws.columns_auto_resize(0, 2)
        except: pass
    except: pass

def load_from_db():
    try:
        ws = get_worksheet("ProductionData")
        rows = ws.get_all_values()
        if len(rows) <= 1: return []
        data = []
        for r in rows[1:]:
            item = {
                'batch': r[0], 'plan_start_pre': datetime.fromisoformat(r[1]) if r[1] else None,
                'd_pre': float(r[3]) if r[3] else 12, 'cast': float(r[4]) if r[4] else 0,
                'd_post': float(r[5]) if r[5] else 33, 'jit': r[6].upper() == 'TRUE',
                'locked': r[7].upper() == 'TRUE', 'padding': float(r[8]) if r[8] else 1,
            }
            if len(r) > 9 and r[9] and r[9] != 'null':
                f_data = json.loads(r[9])
                if f_data:
                    for job in f_data:
                        job['Start'] = datetime.fromisoformat(job['Start'])
                        job['Finish'] = datetime.fromisoformat(job['Finish'])
                    item['fixed_data'] = f_data
            else: item['fixed_data'] = None
            data.append(item)
        return data
    except: return []

def load_settings():
    try:
        ws = get_worksheet("Settings")
        rows = ws.get_all_values()
        if len(rows) <= 1: return {}
        settings = {}
        for r in rows[1:]:
            key = r[0]
            try: val = json.loads(r[1])
            except:
                val = r[1]
                if val.isdigit(): val = int(val)
                elif val.lower() == 'true': val = True
                elif val.lower() == 'false': val = False
            settings[key] = val
        return settings
    except: return {}

def load_finished_batches():
    try:
        ws = get_worksheet("FinishedBatches")
        rows = ws.get_all_values()
        if len(rows) <= 1: return []
        return [{"Nama Batch": r[0], "Status Batch": r[1], "Status Proses": r[2]} for r in rows[1:]]
    except: return []

# --- 2. SESSION STATE ---
if 'batch_list' not in st.session_state:
    st.session_state.batch_list = load_from_db()
if 'finished_list' not in st.session_state:
    st.session_state.finished_list = load_finished_batches()
if 'settings' not in st.session_state:
    db_set = load_settings()
    if not db_set:
        db_set = {
            'd_pre': 12, 'd_post': 33, 'padding': 1, 'd_cast': 9,
            'machines': {f"Bo{i}": True for i in range(1, 7)}
        }
    st.session_state.settings = db_set

# --- 3. SIDEBAR CONFIG ---
with st.sidebar:
    st.header("⚙️ Parameter Pabrik")
    def update_settings_cb():
        st.session_state.settings['d_pre'] = st.session_state.sb_pre
        st.session_state.settings['d_post'] = st.session_state.sb_post
        st.session_state.settings['padding'] = st.session_state.sb_pad
        st.session_state.settings['d_cast'] = st.session_state.sb_cast
        save_settings(st.session_state.settings)

    d_pre = st.number_input("Durasi Pre-heat (Jam)", value=st.session_state.settings.get('d_pre', 12), key="sb_pre", on_change=update_settings_cb)
    default_cast = st.number_input("Default Durasi Casting (Jam)", value=st.session_state.settings.get('d_cast', 9), key="sb_cast", on_change=update_settings_cb)
    d_post = st.number_input("Durasi Post-heat (Jam)", value=st.session_state.settings.get('d_post', 33), key="sb_post", on_change=update_settings_cb)
    padding_val = st.number_input("Padding (Jam)", value=st.session_state.settings.get('padding', 1), key="sb_pad", on_change=update_settings_cb)
    padding_time = timedelta(hours=padding_val)
    st.divider()
    mesin_sehat = []
    st.write("🔧 Status Mesin")
    for i in range(1, 7):
        m_id = f"Bo{i}"
        m_val = st.session_state.settings['machines'].get(m_id, True)
        if st.checkbox(f"{m_id} OK", value=m_val, key=f"check_{m_id}"):
            mesin_sehat.append(m_id)
            if not m_val:
                st.session_state.settings['machines'][m_id] = True
                save_settings(st.session_state.settings)
        else:
            if m_val:
                st.session_state.settings['machines'][m_id] = False
                save_settings(st.session_state.settings)
    
    st.divider()
    if st.button("🔍 Cek Koneksi GSheets"):
        try:
            client = get_gspread_client()
            sh = client.open(SHEET_NAME)
            st.success(f"✅ Koneksi Berhasil ke {sh.title}")
        except Exception as e: st.error(f"❌ Gagal: {e}")

    with st.expander("☁️ Migrasi ke Cloud"):
        if st.button("🚀 Mulai Migrasi"):
            OLD_DB = os.path.join(os.path.dirname(__file__), "scheduler_data.db")
            if os.path.exists(OLD_DB):
                import sqlite3
                try:
                    conn = sqlite3.connect(OLD_DB)
                    c = conn.cursor()
                    c.execute("SELECT content FROM production_data"); row_p = c.fetchone()
                    c.execute("SELECT content FROM factory_settings"); row_s = c.fetchone()
                    conn.close()
                    if row_p: save_to_db(json.loads(row_p[0]))
                    if row_s: save_settings(json.loads(row_s[0]))
                    st.success("✅ Berhasil! Refresh halaman.")
                except Exception as e: st.error(f"Gagal: {e}")
            else: st.warning("DB lokal tidak ada.")

    if st.button("🗑️ Reset GSheets DB", type="primary", use_container_width=True):
        st.session_state.batch_list = []
        save_to_db([])
        st.rerun()

# --- 4. INPUT BATCH ---
st.subheader("📝 Tambah Batch Produksi")
with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    with c1: name = st.text_input("Nama Batch")
    with c5:
        st.write("Mode JIT")
        jit_on = st.toggle("Autopilot", value=True)
    with c2: p_tgl = st.date_input("Rencana Tgl Start", get_now_jkt(), disabled=jit_on)
    with c3: p_jam = st.time_input("Rencana Jam Start", get_now_jkt(), disabled=jit_on)
    with c4: b_cast = st.number_input("Durasi Cast", value=default_cast)
    plan_start_pre = datetime.combine(p_tgl, p_jam)
    if st.button("➕ Tambah Batch", use_container_width=True):
        if name:
            st.session_state.batch_list.append({'batch': name, 'cast': b_cast, 'plan_start_pre': plan_start_pre, 'jit': jit_on, 'locked': False, 'fixed_data': None, 'd_pre': d_pre, 'd_post': d_post, 'padding': padding_val})
            save_to_db(st.session_state.batch_list)
            st.rerun()

# --- 5. LOGIKA PERHITUNGAN ---
if st.session_state.batch_list and mesin_sehat:
    waktu_skrg = get_now_jkt()
    p_starts = [item['plan_start_pre'] for item in st.session_state.batch_list if not item.get('jit')]
    waktu_awal_simulasi = min(p_starts + [waktu_skrg]) if p_starts else waktu_skrg
    ketersediaan = {m: waktu_awal_simulasi for m in mesin_sehat}
    casting_bebas = waktu_awal_simulasi
    data_gantt, data_tabel = [], []

    for idx, item in enumerate(st.session_state.batch_list):
        if 'd_pre' not in item:
            item['d_pre'], item['d_post'], item['padding'] = d_pre, d_post, padding_val
            save_to_db(st.session_state.batch_list)
        c_pre, c_post, c_pad = item['d_pre'], item['d_post'], timedelta(hours=item['padding'])

        if item.get('locked') and item.get('fixed_data'):
            actual_job = item['fixed_data']
        else:
            if item.get('jit'):
                saran_oven = sorted(ketersediaan.items(), key=lambda x: x[1])[0]
                start_pre, nama_bo_pre = max(waktu_awal_simulasi, saran_oven[1]), saran_oven[0]
            else:
                start_pre = item['plan_start_pre']
                oven_ok = [m for m, t in ketersediaan.items() if t <= start_pre]
                if not oven_ok: continue
                nama_bo_pre = oven_ok[0]

            end_pre = start_pre + timedelta(hours=c_pre)
            start_cast = max(end_pre + c_pad, casting_bebas)
            end_cast = start_cast + timedelta(hours=item['cast'])
            bo_post_pool = {k: v for k, v in ketersediaan.items() if k in ['Bo1', 'Bo2', 'Bo3', 'Bo4']}
            start_post_req = end_cast + c_pad
            oven_post_ready = [m for m, t in bo_post_pool.items() if t <= start_post_req]
            if not oven_post_ready:
                saran_p = sorted(bo_post_pool.items(), key=lambda x: x[1])[0]
                start_post, nama_bo_post = saran_p[1], saran_p[0]
                end_cast = start_post - c_pad
                start_cast = end_cast - timedelta(hours=item['cast'])
                end_pre, start_pre = start_cast - c_pad, (start_cast - c_pad) - timedelta(hours=c_pre)
            else: start_post, nama_bo_post = start_post_req, oven_post_ready[0]
            end_post = start_post + timedelta(hours=c_post)
            actual_job = [dict(Batch=item['batch'], Proses='1. Pre-Heat', Mesin=nama_bo_pre, Start=start_pre, Finish=end_pre), dict(Batch=item['batch'], Proses='2. Casting', Mesin='Casting Unit', Start=start_cast, Finish=end_cast), dict(Batch=item['batch'], Proses='3. Post-Heat', Mesin=nama_bo_post, Start=start_post, Finish=end_post)]

        if item.get('locked') and item['fixed_data'] is None:
            item['fixed_data'] = actual_job
            save_to_db(st.session_state.batch_list)
        
        data_gantt.extend(actual_job)
        for j in actual_job:
            if j['Mesin'] in ketersediaan: ketersediaan[j['Mesin']] = j['Finish']
            if j['Mesin'] == 'Casting Unit': casting_bebas = j['Finish']
        
        now = get_now_jkt()
        j_pre, j_cast, j_post = actual_job[0], actual_job[1], actual_job[2]
        if now < j_pre['Start']: status_kerja = "⏳ Menunggu"
        elif j_pre['Start'] <= now < j_pre['Finish']: status_kerja = f"🔥 Pre-Heating ({j_pre['Mesin']})"
        elif j_pre['Finish'] <= now < j_cast['Start']: status_kerja = "🕒 Transisi ke Casting"
        elif j_cast['Start'] <= now < j_cast['Finish']: status_kerja = "🏗️ Casting Unit"
        elif j_cast['Finish'] <= now < j_post['Start']: status_kerja = "🕒 Transisi ke Post-Heat"
        elif j_post['Start'] <= now < j_post['Finish']: status_kerja = f"♨️ Post-Heating ({j_post['Mesin']})"
        else: status_kerja = "✅ Selesai"

        if status_kerja == "✅ Selesai":
            if not any(f['Nama Batch'] == item['batch'] for f in st.session_state.finished_list):
                st.session_state.finished_list.append({"Nama Batch": item['batch'], "Status Batch": "", "Status Proses": ""})
                save_finished_batches(st.session_state.finished_list)

        fmt = "%H:%M (%d/%m)"
        data_tabel.append({"Batch": item['batch'], "Status": status_kerja, "1. Pre-Heat (S|E|M)": f"{j_pre['Start'].strftime(fmt)} - {j_pre['Finish'].strftime(fmt)} [{j_pre['Mesin']}]", "2. Casting (S|E)": f"{j_cast['Start'].strftime(fmt)} - {j_cast['Finish'].strftime(fmt)}", "3. Post-Heat (S|E|M)": f"{j_post['Start'].strftime(fmt)} - {j_post['Finish'].strftime(fmt)} [{j_post['Mesin']}]", "Mode": "🚀 Auto" if item.get('jit') else "📝 Manual"})

    if data_gantt:
        st.divider()
        df_plot = pd.DataFrame(data_gantt)
        fig = px.timeline(df_plot, x_start="Start", x_end="Finish", y="Mesin", color="Proses", text="Batch")
        fig.update_yaxes(autorange="reversed")
        fig.update_traces(textposition='inside', insidetextanchor='middle', textfont=dict(color="white"))
        fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide', height=450)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(pd.DataFrame(data_tabel), use_container_width=True, hide_index=True)

if st.session_state.batch_list:
    st.subheader("📋 Kontrol Antrean")
    for idx, item in enumerate(st.session_state.batch_list):
        is_locked = item.get('locked', False)
        status = "🔒 Terkunci" if is_locked else "🔓 Draft"
        label = f"{item['batch']} | {status} | {'🚀 Autopilot' if item.get('jit') else '📝 Manual'}"
        with st.expander(label):
            c1, c2 = st.columns([2, 1])
            with c1: edit_name = st.text_input("Nama Batch", value=item['batch'], key=f"edit_n_{idx}")
            with c2: edit_jit = st.toggle("Autopilot", value=item.get('jit', True), key=f"edit_j_{idx}")
            c3, c4, c5 = st.columns([1.5, 1.5, 1])
            with c3: edit_tgl = st.date_input("Rencana Tgl Pre-heat", value=item['plan_start_pre'].date(), key=f"edit_d_{idx}", disabled=edit_jit)
            with c4: edit_jam = st.time_input("Rencana Jam Pre-heat", value=item['plan_start_pre'].time(), key=f"edit_t_{idx}", disabled=edit_jit)
            with c5: edit_cast = st.number_input("Durasi Cast", value=item.get('cast', 9), key=f"edit_c_{idx}")
            with st.container(border=True):
                st.caption("⚙️ Parameter Tersemat (Snapshot)")
                e_c1, e_c2, e_c3 = st.columns(3)
                with e_c1: edit_pre = st.number_input("Durasi Pre-heat", value=item.get('d_pre', 12), key=f"epre_{idx}")
                with e_c2: edit_post = st.number_input("Durasi Post-heat", value=item.get('d_post', 33), key=f"epost_{idx}")
                with e_c3: edit_pad = st.number_input("Padding (Jam)", value=item.get('padding', 1), key=f"epad_{idx}")
            st.divider()
            b1, b2, b3 = st.columns([1, 1, 1])
            with b1:
                if st.button("💾 Simpan Perubahan", key=f"btn_s_{idx}", use_container_width=True):
                    item.update({'batch': edit_name, 'jit': edit_jit, 'plan_start_pre': datetime.combine(edit_tgl, edit_jam), 'cast': edit_cast, 'd_pre': edit_pre, 'd_post': edit_post, 'padding': edit_pad, 'locked': False, 'fixed_data': None})
                    save_to_db(st.session_state.batch_list); st.rerun()
            with b2:
                if not is_locked:
                    if st.button("🔒 Lock Jadwal", key=f"btn_l_{idx}", type="primary", use_container_width=True):
                        item['locked'] = True; save_to_db(st.session_state.batch_list); st.rerun()
                else:
                    if st.button("🔓 Buka Kunci", key=f"btn_u_{idx}", use_container_width=True):
                        item.update({'locked': False, 'fixed_data': None}); save_to_db(st.session_state.batch_list); st.rerun()
            with b3:
                if st.button("🗑️ Hapus Batch", key=f"btn_d_{idx}", use_container_width=True):
                    st.session_state.batch_list.pop(idx); save_to_db(st.session_state.batch_list); st.rerun()

st.divider()
st.subheader("🏁 Riwayat Batch Selesai")
if st.session_state.finished_list:
    edited_df = st.data_editor(pd.DataFrame(st.session_state.finished_list), use_container_width=True, hide_index=True, num_rows="dynamic", key="finished_editor")
    if st.button("💾 Simpan Perubahan Riwayat"):
        st.session_state.finished_list = edited_df.to_dict('records')
        save_finished_batches(st.session_state.finished_list); st.success("Riwayat disimpan!")
else: st.info("Belum ada batch yang selesai.")