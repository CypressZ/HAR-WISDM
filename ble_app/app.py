import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import asyncio
import json
import time
from datetime import datetime
import numpy as np
from collections import deque
from bleak import BleakClient
import threading
import queue

# Configure Streamlit page
st.set_page_config(
    page_title="Activity Monitor",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Arduino Configuration
ARDUINO_ADDRESS = "64609202-37DA-83AF-1A6A-87D95E127B3F"
SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHARACTERISTIC_UUID = "87654321-4321-4321-4321-cba987654321"

# Initialize session state
if 'connected' not in st.session_state:
    st.session_state.connected = False
if 'data_queue' not in st.session_state:
    st.session_state.data_queue = deque(maxlen=100)
if 'ble_thread' not in st.session_state:
    st.session_state.ble_thread = None
if 'stop_event' not in st.session_state:
    st.session_state.stop_event = threading.Event()
if 'message_queue' not in st.session_state:
    st.session_state.message_queue = queue.Queue()

class BLEManager:
    def __init__(self, data_queue, message_queue, stop_event):
        self.data_queue = data_queue
        self.message_queue = message_queue
        self.stop_event = stop_event
        self.client = None
        self.connected = False
    
    def data_handler(self, sender, data):
        """Handle incoming BLE data"""
        print("data", data)
        try:
            json_data = json.loads(data.decode('utf-8'))
            print(json_data)
            json_data['received_time'] = time.time()
            json_data['datetime'] = datetime.now()
            self.data_queue.append(json_data)
        except Exception as e:
            self.message_queue.put(('error', f"Data processing error: {e}"))
    
    async def connect_and_run(self):
        """Connect to Arduino and handle data collection"""
        try:
            self.client = BleakClient(ARDUINO_ADDRESS, timeout=15.0)
            await self.client.connect()
            
            # Verify service exists
            services = self.client.services
            service_found = any(SERVICE_UUID.lower() in str(service.uuid).lower() 
                              for service in services)
            
            if not service_found:
                await self.client.disconnect()
                self.message_queue.put(('error', 'Arduino service not found'))
                return
            
            # Start notifications
            await self.client.start_notify(CHARACTERISTIC_UUID, self.data_handler)
            self.connected = True
            self.message_queue.put(('success', 'Connected successfully'))
            
            # Keep connection alive until stop event
            while not self.stop_event.is_set():
                await asyncio.sleep(0.1)
            
            # Clean disconnect
            if self.client and self.client.is_connected:
                await self.client.stop_notify(CHARACTERISTIC_UUID)
                await self.client.disconnect()
            
            self.connected = False
            self.message_queue.put(('info', 'Disconnected'))
            
        except Exception as e:
            self.connected = False
            self.message_queue.put(('error', f'Connection failed: {e}'))

def ble_thread_function(data_queue, message_queue, stop_event):
    """Thread function to run BLE operations"""
    def run_ble():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        ble_manager = BLEManager(data_queue, message_queue, stop_event)
        
        try:
            loop.run_until_complete(ble_manager.connect_and_run())
        except Exception as e:
            message_queue.put(('error', f'BLE thread error: {e}'))
        finally:
            loop.close()
    
    thread = threading.Thread(target=run_ble, daemon=True)
    thread.start()
    return thread

def check_messages():
    """Check for messages from BLE thread"""
    messages = []
    try:
        while True:
            msg_type, msg = st.session_state.message_queue.get_nowait()
            messages.append((msg_type, msg))
    except queue.Empty:
        pass
    return messages

def main():
    st.title("🏃‍♂️ Real-time Activity Monitor")
    st.markdown("Monitor physical activities from Arduino Nano 33 BLE Sense")
    
    # Check for messages from BLE thread
    messages = check_messages()
    for msg_type, msg in messages:
        if msg_type == 'success':
            st.success(msg)
            if 'Connected successfully' in msg:
                st.session_state.connected = True
        elif msg_type == 'error':
            st.error(msg)
        elif msg_type == 'info':
            st.info(msg)
            if 'Disconnected' in msg:
                st.session_state.connected = False
    
    # Sidebar controls
    with st.sidebar:
        st.header("Arduino Connection")
        st.write("**Device**: BLESense-5454")
        st.write(f"**Address**: `{ARDUINO_ADDRESS}`")
        
        # Connection controls
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Connect", disabled=st.session_state.connected):
                if not st.session_state.ble_thread or not st.session_state.ble_thread.is_alive():
                    st.session_state.stop_event.clear()
                    st.session_state.ble_thread = ble_thread_function(
                        st.session_state.data_queue,
                        st.session_state.message_queue,
                        st.session_state.stop_event
                    )
                    st.info("Connecting to Arduino...")
                    time.sleep(0.5)  # Give thread time to start
                    st.rerun()
        
        with col2:
            if st.button("Disconnect", disabled=not st.session_state.connected):
                st.session_state.stop_event.set()
                st.session_state.connected = False
                st.info("Disconnecting...")
                time.sleep(0.5)
                st.rerun()
        
        # Connection status
        if st.session_state.connected:
            st.success("🟢 Connected")
        else:
            st.error("🔴 Disconnected")
        
        # Data controls
        st.header("Data Controls")
        if st.button("Clear Data"):
            st.session_state.data_queue.clear()
            st.success("Data cleared")
        
        # Stats
        if st.session_state.data_queue:
            st.header("Session Stats")
            st.metric("Data Points", len(st.session_state.data_queue))
            
            # Latest activity
            latest = list(st.session_state.data_queue)[-1]
            st.metric("Current Activity", latest.get('act', 'unknown').title())
    
    # Main content
    if st.session_state.connected and st.session_state.data_queue:
        display_real_time_data()
    elif st.session_state.connected:
        st.info("Connected! Waiting for data from Arduino...")
        # Auto-refresh while waiting for data
        time.sleep(1)
        st.rerun()
    else:
        st.info("Please connect to your Arduino to start monitoring activities.")

def display_real_time_data():
    """Display real-time data from Arduino"""
    data_list = list(st.session_state.data_queue)
    latest_data = data_list[-1]
    print(latest_data)
    
    # Current activity display - full width
    activity_emoji = {
        'Walking': '🚶🏼‍♀️',
        'Jogging': '🏃‍♀️', 
        'Sitting': '🧘',
        'Standing': '🧍',
        'Upstairs': '⬆️',
        'Downstairs': '⬇️'
    }
    
    activity = latest_data.get('act', 'unknown')
    st.metric(
        label="Current Activity",
        value=f"{activity_emoji.get(activity, '❓')} {activity.title()}"
    )
    
    # Second row: Model confidence + Accelerometer data
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if 'confidence' in latest_data:
            st.metric("Model Confidence", f"{latest_data.get('confidence', 0):.1%}")
        else:
            st.metric("Model Confidence", "N/A")
    
    with col2:
        st.metric("Accel X", f"{latest_data.get('ax', 0):.3f} g")
    
    with col3:
        st.metric("Accel Y", f"{latest_data.get('ay', 0):.3f} g")
    
    with col4:
        st.metric("Accel Z", f"{latest_data.get('az', 0):.3f} g")
    
    if len(data_list) > 1:
        # Convert to DataFrame
        df = pd.DataFrame(data_list)
        df['datetime'] = pd.to_datetime([d['datetime'] for d in data_list])
        
        # Activity timeline
        st.subheader("📈 Activity Timeline")
        
        # Consistent color mapping for all charts
        activity_colors = {
            'Standing': '#1f77b4',
            'Walking': '#ff7f0e', 
            'Jogging': '#d62728',
            'Upstairs': '#2ca02c',
            'Downstairs': '#9467bd',
            'Sitting': '#8c564b'  # Changed to brown to avoid blue conflict
        }
        
        fig_timeline = px.scatter(
            df, x='datetime', y='act', color='act',
            title="Activity Over Time",
            color_discrete_map=activity_colors,
            category_orders={'act': list(activity_colors.keys())}  # Force consistent ordering
        )
        fig_timeline.update_traces(marker_size=10)
        st.plotly_chart(fig_timeline, use_container_width=True)
        
        # Accelerometer data chart (no tabs needed)
        st.subheader("📊 Accelerometer Data")
        fig_accel = go.Figure()
        fig_accel.add_trace(go.Scatter(x=df['datetime'], y=df['ax'], name='X', line=dict(color='red')))
        fig_accel.add_trace(go.Scatter(x=df['datetime'], y=df['ay'], name='Y', line=dict(color='green')))
        fig_accel.add_trace(go.Scatter(x=df['datetime'], y=df['az'], name='Z', line=dict(color='blue')))
        fig_accel.update_layout(title="Accelerometer Data (g)", yaxis_title="Acceleration (g)")
        st.plotly_chart(fig_accel, use_container_width=True)
        
        # Activity analysis
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Activity Distribution")
            activity_counts = df['act'].value_counts()
            
            # Ensure the pie chart uses the same order and colors
            fig_pie = px.pie(
                values=activity_counts.values,
                names=activity_counts.index,
                title="Time Spent in Each Activity",
                color_discrete_map=activity_colors,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            st.subheader("📋 Recent Data")
            display_df = df.tail(10)[['datetime', 'act', 'ax', 'ay', 'az']].copy()
            if 'confidence' in df.columns:
                display_df = df.tail(10)[['datetime', 'act', 'confidence', 'ax', 'ay', 'az']].copy()
            display_df['datetime'] = display_df['datetime'].dt.strftime('%H:%M:%S')
            display_df = display_df.round(3)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Auto-refresh every 1 second
    time.sleep(1)
    st.rerun()

if __name__ == "__main__":
    main()