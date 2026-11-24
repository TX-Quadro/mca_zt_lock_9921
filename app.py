import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

st.set_page_config(page_title="Zero-Trust Smart Lock", page_icon="🔐", layout="centered")

# Unique MQTT Topic Prefix (Change "mca_zt_lock_9921" to any secret word of your choice!)
TOPIC_PREFIX = "mca_zt_lock_9921"
BROKER = "broker.hivemq.com"

# Initialize Cloud Memory (Users, Telemetry, Logs)
if "users" not in st.session_state:
    st.session_state.users = {
        "MCA-Admin": {"role": "Admin", "active": True},
        "Prof-Evaluator": {"role": "Faculty", "active": True}
    }
if "telemetry" not in st.session_state:
    st.session_state.telemetry = {
        "code": "------",
        "door_closed": False,
        "locked": True,
        "intrusion": False,
        "last_seen": 0
    }
if "logs" not in st.session_state:
    st.session_state.logs = []

def log_event(user, status, detail, latency_ms=None):
    ts = datetime.now().strftime("%H:%M:%S")
    lat_str = f" | RTT: {latency_ms}ms" if latency_ms else ""
    st.session_state.logs.insert(0, f"`[{ts}]` **{user}** → **{status}**: {detail}{lat_str}")

# Fetch latest telemetry from ESP8266 via MQTT
def sync_mqtt():
    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            st.session_state.telemetry.update(data)
            st.session_state.telemetry["last_seen"] = time.time()
        except Exception:
            pass

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    client.subscribe(f"{TOPIC_PREFIX}/telemetry")
    client.loop_start()
    time.sleep(0.4)  # Brief listen for retained edge state
    client.loop_stop()
    client.disconnect()

def send_unlock_command():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, 1883, 60)
    client.publish(f"{TOPIC_PREFIX}/command", json.dumps({"action": "UNLOCK"}))
    client.disconnect()

sync_mqtt()
tel = st.session_state.telemetry
is_online = (time.time() - tel["last_seen"]) < 15

# --- UI HEADER ---
st.title("🔐 Zero-Trust Cyber-Physical Smart Lock")
st.caption("Cloud Policy Engine (Streamlit Cloud) + Edge Telemetry (NodeMCU ESP8266 via MQTT)")

# --- LIVE EDGE TELEMETRY ---
col1, col2, col3 = st.columns(3)
col1.metric("Edge Node", "🟢 ONLINE" if is_online else "🔴 OFFLINE")
col2.metric("IR Door Sensor", "🚪 CLOSED" if tel["door_closed"] else "⚠️ OPEN")
col3.metric("Bolt State", "🔒 LOCKED" if tel["locked"] else "🔓 UNLOCKED")

if tel.get("intrusion"):
    st.error("🚨 CRITICAL ALERT: Forced-entry intrusion detected while bolt was locked!")

st.divider()

# --- ZERO-TRUST UNLOCK PORTAL ---
st.subheader("1. Zero-Trust Physical Presence Verification")
selected_user = st.selectbox("Select Identity", list(st.session_state.users.keys()))
entered_code = st.text_input("Enter 6-Digit Rolling Code from OLED Display", max_chars=6, placeholder="e.g. 482910")

if st.button("Verify Policy & Unlock Door", type="primary", use_container_width=True):
    start_t = time.time()
    user_info = st.session_state.users.get(selected_user)

    # Zero-Trust Check 1: Identity & Revocation
    if not user_info or not user_info["active"]:
        log_event(selected_user, "DENIED", "User access suspended/revoked by Admin")
        st.error("❌ ACCESS DENIED: Your account is suspended by Zero-Trust Policy.")

    # Zero-Trust Check 2: Edge Device Health
    elif not is_online:
        log_event(selected_user, "DENIED", "Edge lock offline / failed heartbeat")
        st.error("❌ ACCESS DENIED: Smart lock edge node is offline.")

    # Zero-Trust Check 3: Physical Door State (IR Sensor)
    elif not tel["door_closed"]:
        log_event(selected_user, "DENIED", "Door physically open (IR check failed)")
        st.warning("⚠️ ACCESS DENIED: Close the door completely before unlocking.")

    # Zero-Trust Check 4: Cryptographic Rolling Presence Token
    elif entered_code.strip() != str(tel["code"]):
        log_event(selected_user, "DENIED", f"Invalid/expired rolling code ({entered_code})")
        st.error("❌ ACCESS DENIED: Wrong or expired 6-digit OLED code.")

    # ALL ZERO-TRUST CHECKS PASSED!
    else:
        send_unlock_command()
        rtt = int((time.time() - start_t) * 1000)
        log_event(selected_user, "GRANTED", f"Verified {user_info['role']} + OLED token", rtt)
        st.success(f"✅ ZERO-TRUST VERIFIED! Unlock signal dispatched in {rtt} ms.")

st.divider()

# --- ADMIN IAM & REVOCATION PANEL ---
st.subheader("2. Cloud IAM: User Creation & Real-Time Revocation")
c1, c2, c3 = st.columns([2, 1.5, 1])
new_user = c1.text_input("New Username", placeholder="e.g. Student-01", label_visibility="collapsed")
new_role = c2.selectbox("Role", ["Student", "Faculty", "Guest"], label_visibility="collapsed")
if c3.button("Add User", use_container_width=True) and new_user.strip():
    st.session_state.users[new_user.strip()] = {"role": new_role, "active": True}
    log_event("ADMIN", "IAM_CREATE", f"Added {new_user.strip()} ({new_role})")
    st.rerun()

for uname, info in st.session_state.users.items():
    ucol1, ucol2, ucol3 = st.columns([2.5, 1.5, 1.2])
    ucol1.write(f"**{uname}** (`{info['role']}`)")
    ucol2.write("🟢 Active" if info["active"] else "🔴 Suspended")
    btn_label = "Revoke" if info["active"] else "Restore"
    if ucol3.button(btn_label, key=f"btn_{uname}", use_container_width=True):
        st.session_state.users[uname]["active"] = not info["active"]
        state_txt = "RESTORED" if st.session_state.users[uname]["active"] else "REVOKED"
        log_event("ADMIN", f"IAM_{state_txt}", f"Changed {uname} access")
        st.rerun()

st.divider()

# --- AUDIT LOGS & REFRESH ---
col_log, col_ref = st.columns([3, 1])
col_log.subheader("3. Zero-Trust Audit Trail")
if col_ref.button("🔄 Refresh Telemetry", use_container_width=True):
    st.rerun()

if st.session_state.logs:
    for entry in st.session_state.logs[:12]:
        st.markdown(entry)
else:
    st.info("No access attempts recorded yet.")