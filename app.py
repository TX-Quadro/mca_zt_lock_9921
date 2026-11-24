import streamlit as st
import time
from datetime import datetime

st.set_page_config(page_title="Zero-Trust Smart Lock", page_icon="🔐", layout="centered")

# 1. SHARED CLOUD MEMORY (Persists across all phone & ESP8266 requests)
@st.cache_resource
def get_cloud_state():
    return {
        "users": {
            "MCA-Admin": {"role": "Admin", "active": True},
            "Prof-Evaluator": {"role": "Faculty", "active": True}
        },
        "telemetry": {
            "code": "------",
            "door_closed": False,
            "locked": True,
            "intrusion": False,
            "last_seen": 0
        },
        "unlock_command": False,
        "logs": []
    }

STATE = get_cloud_state()

def log_event(user, status, detail, latency_ms=None):
    ts = datetime.now().strftime("%H:%M:%S")
    lat_str = f" | RTT: {latency_ms}ms" if latency_ms else ""
    STATE["logs"].insert(0, f"`[{ts}]` **{user}** → **{status}**: {detail}{lat_str}")
    STATE["logs"] = STATE["logs"][:15]

# 2. EDGE TELEMETRY SYNC ENDPOINT (Called by ESP8266 via HTTPS GET)
params = st.query_params
if params.get("sync") == "1":
    STATE["telemetry"]["code"] = str(params.get("code", "------"))
    STATE["telemetry"]["door_closed"] = (params.get("door") == "1")
    STATE["telemetry"]["locked"] = (params.get("locked") == "1")
    STATE["telemetry"]["intrusion"] = (params.get("intrusion") == "1")
    STATE["telemetry"]["last_seen"] = time.time()

    if STATE["unlock_command"]:
        STATE["unlock_command"] = False
        st.write("CMD:UNLOCK")
    else:
        st.write("CMD:WAIT")
    st.stop()

# 3. STREAMLIT CLOUD DASHBOARD UI
tel = STATE["telemetry"]
is_online = (time.time() - tel["last_seen"]) < 10

st.title("🔐 Zero-Trust Cyber-Physical Smart Lock")
st.caption("Standalone Pure-Python Cloud Policy Engine (Streamlit Cloud) + NodeMCU ESP8266")

col1, col2, col3 = st.columns(3)
col1.metric("Edge Node", "🟢 ONLINE" if is_online else "🔴 OFFLINE")
col2.metric("IR Door Sensor", "🚪 CLOSED" if tel["door_closed"] else "⚠️ OPEN")
col3.metric("Bolt State", "🔒 LOCKED" if tel["locked"] else "🔓 UNLOCKED")

if tel["intrusion"]:
    st.error("🚨 CRITICAL ALERT: Forced-entry intrusion detected while bolt was locked!")

st.divider()

# --- ZERO-TRUST UNLOCK PORTAL ---
st.subheader("1. Zero-Trust Physical Presence Verification")
selected_user = st.selectbox("Select Identity", list(STATE["users"].keys()))
entered_code = st.text_input("Enter 6-Digit Rolling Code from OLED Display", max_chars=6, placeholder="e.g. 482910")

if st.button("Verify Policy & Unlock Door", type="primary", use_container_width=True):
    start_t = time.time()
    user_info = STATE["users"].get(selected_user)

    if not user_info or not user_info["active"]:
        log_event(selected_user, "DENIED", "User access suspended/revoked by Admin")
        st.error("❌ ACCESS DENIED: Your account is suspended by Zero-Trust Policy.")

    elif not is_online:
        log_event(selected_user, "DENIED", "Edge lock offline / failed heartbeat")
        st.error("❌ ACCESS DENIED: Smart lock edge node is offline.")

    elif not tel["door_closed"]:
        log_event(selected_user, "DENIED", "Door physically open (IR check failed)")
        st.warning("⚠️ ACCESS DENIED: Close the door completely before unlocking.")

    elif entered_code.strip() != str(tel["code"]):
        log_event(selected_user, "DENIED", f"Invalid/expired rolling code ({entered_code})")
        st.error("❌ ACCESS DENIED: Wrong or expired 6-digit OLED code.")

    else:
        STATE["unlock_command"] = True
        rtt = int((time.time() - start_t) * 1000)
        log_event(selected_user, "GRANTED", f"Verified {user_info['role']} + OLED token", rtt)
        st.success(f"✅ ZERO-TRUST VERIFIED! Unlock command queued ({rtt} ms).")

st.divider()

# --- CLOUD IAM PANEL ---
st.subheader("2. Cloud IAM: User Creation & Real-Time Revocation")
c1, c2, c3 = st.columns([2, 1.5, 1])
new_user = c1.text_input("New Username", placeholder="e.g. Student-01", label_visibility="collapsed")
new_role = c2.selectbox("Role", ["Student", "Faculty", "Guest"], label_visibility="collapsed")
if c3.button("Add User", use_container_width=True) and new_user.strip():
    STATE["users"][new_user.strip()] = {"role": new_role, "active": True}
    log_event("ADMIN", "IAM_CREATE", f"Added {new_user.strip()} ({new_role})")
    st.rerun()

for uname, info in STATE["users"].items():
    ucol1, ucol2, ucol3 = st.columns([2.5, 1.5, 1.2])
    ucol1.write(f"**{uname}** (`{info['role']}`)")
    ucol2.write("🟢 Active" if info["active"] else "🔴 Suspended")
    btn_label = "Revoke" if info["active"] else "Restore"
    if ucol3.button(btn_label, key=f"btn_{uname}", use_container_width=True):
        STATE["users"][uname]["active"] = not info["active"]
        state_txt = "RESTORED" if STATE["users"][uname]["active"] else "REVOKED"
        log_event("ADMIN", f"IAM_{state_txt}", f"Changed {uname} access")
        st.rerun()

st.divider()

# --- AUDIT LOGS ---
col_log, col_ref = st.columns([3, 1])
col_log.subheader("3. Zero-Trust Audit Trail")
if col_ref.button("🔄 Refresh Telemetry", use_container_width=True):
    st.rerun()

if STATE["logs"]:
    for entry in STATE["logs"]:
        st.markdown(entry)
else:
    st.info("No access attempts recorded yet.")
