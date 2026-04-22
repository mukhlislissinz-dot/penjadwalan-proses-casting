import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import sqlite3
import json
import os
import pytz

# --- 0. TIMEZONE SETUP ---
TZ = pytz.timezone('Asia/Jakarta')

def get_now_jkt():
    # Mengambil waktu sekarang di Jakarta dan dikonversi ke naive (tanpa tzinfo) 
    # agar kompatibel dengan input dari Streamlit (date_input/time_input)
    return datetime.now(TZ).replace(tzinfo=None)

st.set_page_config(page_title="Factory Scheduler V14.1 - Fix Autopilot", layout="wide")

# --- 1. DATABASE SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "scheduler_data.db")

def save_to_db(data):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS production_data (content TEXT)")
    def handler(x): return x.isoformat() if isinstance(x, datetime) else None
    json_data = json.dumps(data, default=handler)
    c.execute("DELETE FROM production_data")
    c.execute("INSERT INTO production_data (content) VALUES (?)", (json_data,))
    conn.commit()
    conn.close()

def save_settings(settings):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS factory_settings (content TEXT)")
    c.execute("DELETE FROM factory_settings")
    c.execute("INSERT INTO factory_settings (content) VALUES (?)", (json.dumps(settings),))
    conn.commit()
    conn.close()

def load_from_db():
    if not os.path.exists(DB_NAME): return []
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS production_data (content TEXT)")
        c.execute("SELECT content FROM production_data")
        row = c.fetchone()
        conn.close()
        if row:
            raw = json.loads(row[0])
            for item in raw:
                if item.get('fixed_data'):
                    for job in item['fixed_data']:
                        job['Start'] = datetime.fromisoformat(job['Start'])
                        job['Finish'] = datetime.fromisoformat(job['Finish'])
                if item.get('plan_start_pre'):
                    item['plan_start_pre'] = datetime.fromisoformat(item['plan_start_pre'])
            return raw
    except: return []
    return []

def load_settings():
    if not os.path.exists(DB_NAME): return {}
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS factory_settings (content TEXT)")
        c.execute("SELECT content FROM factory_settings")
        row = c.fetchone()
        conn.close()
        return json.loads(row[0]) if row else {}
    except: return {}

if 'batch_list' not in st.session_state:
    st.session_state.batch_list = load_from_db()

if 'settings' not in st.session_state:
    db_set = load_settings()
    # Default jika DB kosong
    if not db_set:
        db_set = {
            'd_pre': 12, 'd_post': 33, 'padding': 1, 'd_cast': 9,
            'machines': {f"Bo{i}": True for i in range(1, 7)}
        }
    st.session_state.settings = db_set

# --- 2. SIDEBAR CONFIG ---
with st.sidebar:
    st.header("⚙️ Parameter Pabrik")
    
    # Fungsi Callback untuk Simpan Settings Otomatis menggunakan Session State Key
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
    
    # Checkbox Mesin dengan database
    mesin_sehat = []
    st.write("🔧 Status Mesin")
    for i in range(1, 7):
        m_id = f"Bo{i}"
        # Ambil status dari session state
        m_val = st.session_state.settings['machines'].get(m_id, True)
        if st.checkbox(f"{m_id} OK", value=m_val, key=f"check_{m_id}"):
            mesin_sehat.append(m_id)
            if not m_val: # Jika berubah jadi True
                st.session_state.settings['machines'][m_id] = True
                save_settings(st.session_state.settings)
        else:
            if m_val: # Jika berubah jadi False
                st.session_state.settings['machines'][m_id] = False
                save_settings(st.session_state.settings)
    
    if st.button("🗑️ Reset Database", type="primary", use_container_width=True):
        st.session_state.batch_list = []
        save_to_db([])
        st.rerun()

# --- 3. INPUT BATCH ---
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
            st.session_state.batch_list.append({
                'batch': name, 'cast': b_cast, 'plan_start_pre': plan_start_pre,
                'jit': jit_on, 'locked': False, 'fixed_data': None,
                # Snapshot parameter saat ini agar tidak terpengaruh perubahan sidebar nantinya
                'd_pre': d_pre, 'd_post': d_post, 'padding': padding_val
            })
            save_to_db(st.session_state.batch_list)
            st.rerun()

# --- 4. LOGIKA PERHITUNGAN ---
if st.session_state.batch_list and mesin_sehat:
    # Tentukan titik awal simulasi: Ambil yang terkecil antara waktu sekarang atau rencana mulai manual terkecil
    waktu_skrg = get_now_jkt()
    p_starts = [item['plan_start_pre'] for item in st.session_state.batch_list if not item.get('jit')]
    waktu_awal_simulasi = min(p_starts + [waktu_skrg]) if p_starts else waktu_skrg
    
    ketersediaan = {m: waktu_awal_simulasi for m in mesin_sehat}
    casting_bebas = waktu_awal_simulasi
    data_gantt = []
    data_tabel = []

    for idx, item in enumerate(st.session_state.batch_list):
        # PERBAIKAN: Jika batch lama belum punya snapshot, berikan snapshot standar sekarang
        # agar ke depannya tidak lagi mengikuti pergerakan sidebar.
        if 'd_pre' not in item:
            item['d_pre'] = d_pre
            item['d_post'] = d_post
            item['padding'] = padding_val
            save_to_db(st.session_state.batch_list)
        
        c_pre = item['d_pre']
        c_post = item['d_post']
        c_pad = timedelta(hours=item['padding'])

        if item.get('locked') and item.get('fixed_data'):
            actual_job = item['fixed_data']
        else:
            # Penentuan Start Pre-heat
            if item.get('jit'):
                # Cari slot oven tercepat yang bisa mengakomodasi Pre-heat secepatnya
                saran_oven = sorted(ketersediaan.items(), key=lambda x: x[1])[0]
                start_pre = max(waktu_awal_simulasi, saran_oven[1])
                nama_bo_pre = saran_oven[0]
            else:
                start_pre = item['plan_start_pre']
                oven_ok = [m for m, t in ketersediaan.items() if t <= start_pre]
                if not oven_ok:
                    # Cari info oven mana yang akan bebas paling cepat untuk membantu user
                    next_free = sorted(ketersediaan.items(), key=lambda x: x[1])[0]
                    st.error(f"❌ {item['batch']} GAGAL: Oven Penuh di jam tersebut. Tersedia paling cepat jam {next_free[1].strftime('%H:%M (%d/%m)')} di {next_free[0]}")
                    continue
                nama_bo_pre = oven_ok[0]

            end_pre = start_pre + timedelta(hours=c_pre)
            start_cast = max(end_pre + c_pad, casting_bebas)
            end_cast = start_cast + timedelta(hours=item['cast'])
            
            # Post-heat (Bo1-Bo4)
            bo_post_pool = {k: v for k, v in ketersediaan.items() if k in ['Bo1', 'Bo2', 'Bo3', 'Bo4']}
            start_post_req = end_cast + c_pad
            oven_post_ready = [m for m, t in bo_post_pool.items() if t <= start_post_req]
            
            if not oven_post_ready:
                saran_p = sorted(bo_post_pool.items(), key=lambda x: x[1])[0]
                start_post = saran_p[1]
                # Geser semua ke belakang agar JIT
                end_cast = start_post - c_pad
                start_cast = end_cast - timedelta(hours=item['cast'])
                end_pre = start_cast - c_pad
                start_pre = end_pre - timedelta(hours=c_pre)
                nama_bo_post = saran_p[0]
            else:
                nama_bo_post = oven_post_ready[0]
                start_post = start_post_req
            
            end_post = start_post + timedelta(hours=c_post)
            
            actual_job = [
                dict(Batch=item['batch'], Proses='1. Pre-Heat', Mesin=nama_bo_pre, Start=start_pre, Finish=end_pre),
                dict(Batch=item['batch'], Proses='2. Casting', Mesin='Casting Unit', Start=start_cast, Finish=end_cast),
                dict(Batch=item['batch'], Proses='3. Post-Heat', Mesin=nama_bo_post, Start=start_post, Finish=end_post)
            ]

        # Simpan jika baru di-lock
        if item.get('locked') and item['fixed_data'] is None:
            item['fixed_data'] = actual_job
            save_to_db(st.session_state.batch_list)
        
        data_gantt.extend(actual_job)
        for j in actual_job:
            if j['Mesin'] in ketersediaan: ketersediaan[j['Mesin']] = j['Finish']
            if j['Mesin'] == 'Casting Unit': casting_bebas = j['Finish']
        
        # --- Logika Status Progress ---
        now = get_now_jkt()
        j_pre, j_cast, j_post = actual_job[0], actual_job[1], actual_job[2]
        
        if now < j_pre['Start']:
            status_kerja = "⏳ Menunggu"
        elif j_pre['Start'] <= now < j_pre['Finish']:
            status_kerja = f"🔥 Pre-Heating ({j_pre['Mesin']})"
        elif j_pre['Finish'] <= now < j_cast['Start']:
            status_kerja = "🕒 Transisi ke Casting"
        elif j_cast['Start'] <= now < j_cast['Finish']:
            status_kerja = "🏗️ Casting Unit"
        elif j_cast['Finish'] <= now < j_post['Start']:
            status_kerja = "🕒 Transisi ke Post-Heat"
        elif j_post['Start'] <= now < j_post['Finish']:
            status_kerja = f"♨️ Post-Heating ({j_post['Mesin']})"
        else:
            status_kerja = "✅ Selesai"

        fmt = "%H:%M (%d/%m)"
        data_tabel.append({
            "Batch": item['batch'],
            "Status": status_kerja,
            "1. Pre-Heat (S|E|M)": f"{j_pre['Start'].strftime(fmt)} - {j_pre['Finish'].strftime(fmt)} [{j_pre['Mesin']}]",
            "2. Casting (S|E)": f"{j_cast['Start'].strftime(fmt)} - {j_cast['Finish'].strftime(fmt)}",
            "3. Post-Heat (S|E|M)": f"{j_post['Start'].strftime(fmt)} - {j_post['Finish'].strftime(fmt)} [{j_post['Mesin']}]",
            "Mode": "🚀 Auto" if item.get('jit') else "📝 Manual"
        })

    # --- 7. OUTPUT DENGAN PENGAMAN DATA ---
    if data_gantt:
        st.divider()
        df_plot = pd.DataFrame(data_gantt)
        # Proteksi: Pastikan kolom yang dibutuhkan ada sebelum gambar chart
        if not df_plot.empty and 'Start' in df_plot.columns:
            fig = px.timeline(df_plot, x_start="Start", x_end="Finish", y="Mesin", color="Proses", text="Batch")
            fig.update_yaxes(autorange="reversed")
            
            # PERBAIKAN: Memaksa teks masuk ke dalam kotak dan rapi
            fig.update_traces(
                textposition='inside', 
                insidetextanchor='middle',
                textfont=dict(color="white")
            )
            fig.update_layout(
                uniformtext_minsize=8, 
                uniformtext_mode='hide', # Sembunyikan teks jika kotak terlalu sempit (biar tidak tertimpa)
                height=450
            )
            
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pd.DataFrame(data_tabel), use_container_width=True, hide_index=True)
    else:
        st.info("Tambahkan batch untuk melihat jadwal.")

# --- 5. MANAGEMENT ---
if st.session_state.batch_list:
    st.subheader("📋 Kontrol Antrean")
    # Gunakan copy list untuk menghindari error saat mutasi dalam loop
    for idx, item in enumerate(st.session_state.batch_list):
        is_locked = item.get('locked', False)
        status = "🔒 Terkunci" if is_locked else "🔓 Draft"
        label = f"{item['batch']} | {status} | {'🚀 Autopilot' if item.get('jit') else '📝 Manual'}"
        
        with st.expander(label):
            # --- Form Edit ---
            c1, c2 = st.columns([2, 1])
            with c1:
                edit_name = st.text_input("Nama Batch", value=item['batch'], key=f"edit_n_{idx}")
            with c2:
                edit_jit = st.toggle("Autopilot", value=item.get('jit', True), key=f"edit_j_{idx}")
            
            c3, c4, c5 = st.columns([1.5, 1.5, 1])
            with c3:
                edit_tgl = st.date_input("Rencana Tgl Pre-heat", value=item['plan_start_pre'].date(), key=f"edit_d_{idx}", disabled=edit_jit)
            with c4:
                edit_jam = st.time_input("Rencana Jam Pre-heat", value=item['plan_start_pre'].time(), key=f"edit_t_{idx}", disabled=edit_jit)
            with c5:
                edit_cast = st.number_input("Durasi Cast", value=item.get('cast', 9), key=f"edit_c_{idx}")
            
            # Tambahan Parameter Per-Batch
            with st.container(border=True):
                st.caption("⚙️ Parameter Tersemat (Snapshot)")
                e_c1, e_c2, e_c3 = st.columns(3)
                with e_c1: edit_pre = st.number_input("Durasi Pre-heat", value=item.get('d_pre', 12), key=f"epre_{idx}")
                with e_c2: edit_post = st.number_input("Durasi Post-heat", value=item.get('d_post', 33), key=f"epost_{idx}")
                with e_c3: edit_pad = st.number_input("Padding (Jam)", value=item.get('padding', 1), key=f"epad_{idx}")

            # --- Tombol Aksi ---
            st.divider()
            b1, b2, b3 = st.columns([1, 1, 1])
            with b1:
                if st.button("💾 Simpan Perubahan", key=f"btn_s_{idx}", use_container_width=True):
                    item['batch'] = edit_name
                    item['jit'] = edit_jit
                    item['plan_start_pre'] = datetime.combine(edit_tgl, edit_jam)
                    item['cast'] = edit_cast
                    # Simpan juga parameter snapshot yang diedit
                    item['d_pre'] = edit_pre
                    item['d_post'] = edit_post
                    item['padding'] = edit_pad
                    # Jika diedit, buka kunci agar sistem menghitung ulang posisi terbaiknya
                    item['locked'] = False
                    item['fixed_data'] = None
                    save_to_db(st.session_state.batch_list)
                    st.success("Perubahan disimpan!")
                    st.rerun()
            
            with b2:
                if not is_locked:
                    if st.button("🔒 Lock Jadwal", key=f"btn_l_{idx}", type="primary", use_container_width=True):
                        item['locked'] = True
                        # fixed_data akan diisi oleh logika perhitungan di rerun berikutnya
                        save_to_db(st.session_state.batch_list)
                        st.rerun()
                else:
                    if st.button("🔓 Buka Kunci", key=f"btn_u_{idx}", use_container_width=True):
                        item['locked'] = False
                        item['fixed_data'] = None
                        save_to_db(st.session_state.batch_list)
                        st.rerun()
            
            with b3:
                if st.button("🗑️ Hapus Batch", key=f"btn_d_{idx}", use_container_width=True):
                    st.session_state.batch_list.pop(idx)
                    save_to_db(st.session_state.batch_list)
                    st.rerun()