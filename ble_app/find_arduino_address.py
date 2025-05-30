#!/usr/bin/env python3
"""
Enhanced Arduino Nano 33 BLE Sense scanner with multiple methods
"""

import asyncio
import platform
from bleak import BleakScanner, BleakClient

async def scan_method_1():
    """Standard BLE scan"""
    print("Method 1: Standard BLE scan...")
    devices = await BleakScanner.discover(timeout=10.0)
    return devices

async def scan_method_2():
    """Scan with detection callback"""
    print("Method 2: Real-time detection scan...")
    devices = []
    
    def detection_callback(device, advertisement_data):
        devices.append(device)
        print(f"  Found: {device.name or 'Unknown'} - {device.address}")
    
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    await asyncio.sleep(10.0)
    await scanner.stop()
    
    return devices

async def scan_method_3():
    """Scan for specific service UUID"""
    print("Method 3: Scanning for Arduino service UUID...")
    arduino_service_uuid = "12345678-1234-1234-1234-123456789abc"
    
    devices = await BleakScanner.discover(
        timeout=15.0,
        service_uuids=[arduino_service_uuid]
    )
    return devices

async def detailed_device_check(device):
    """Get detailed info about a device"""
    try:
        print(f"\n🔍 Detailed check for: {device.name or 'Unknown'}")
        print(f"   Address: {device.address}")
        
        async with BleakClient(device.address, timeout=10.0) as client:
            if await client.is_connected():
                print("   ✓ Successfully connected")
                
                services = client.services
                print(f"   Found {len(services)} services:")
                
                arduino_service_found = False
                for service in services:
                    print(f"     Service: {service.uuid}")
                    
                    if "12345678-1234-1234-1234-123456789abc" in str(service.uuid):
                        print("     ⭐⭐⭐ ARDUINO SERVICE FOUND! ⭐⭐⭐")
                        arduino_service_found = True
                        
                        # Check characteristics
                        for char in service.characteristics:
                            print(f"       Characteristic: {char.uuid}")
                            if "87654321-4321-4321-4321-cba987654321" in str(char.uuid):
                                print("       ⭐ Arduino activity characteristic found!")
                
                if arduino_service_found:
                    print(f"\n🎉 THIS IS YOUR ARDUINO: {device.address}")
                    return True
                else:
                    print("   ❌ No Arduino service found")
            else:
                print("   ❌ Could not connect")
                
    except Exception as e:
        print(f"   ❌ Error checking device: {e}")
    
    return False

async def main():
    print("=" * 60)
    print("Arduino Nano 33 BLE Sense Scanner")
    print("=" * 60)
    print(f"Running on: {platform.system()} {platform.release()}")
    print()
    
    all_devices = []
    
    # Try multiple scanning methods
    # for scan_method in [scan_method_1, scan_method_2, scan_method_3]:
    for scan_method in [scan_method_1]:

        try:
            print("-" * 50)
            devices = await scan_method()
            
            if devices:
                print(f"Found {len(devices)} devices with this method")
                all_devices.extend(devices)
                
                for device in devices:
                    name = device.name or "Unknown"
                    print(f"  {name}: {device.address}")
            else:
                print("No devices found with this method")
                
        except Exception as e:
            # print(f"Error with scanning method: {e}")
            print()
            
        print()
    
    # Remove duplicates
    unique_devices = []
    seen_addresses = set()
    for device in all_devices:
        if device.address not in seen_addresses:
            unique_devices.append(device)
            seen_addresses.add(device.address)
    
    print("=" * 60)
    print(f"SUMMARY: Found {len(unique_devices)} unique devices")
    print("=" * 60)
    
    if not unique_devices:
        print("❌ No BLE devices found at all!")
        print("\nTroubleshooting steps:")
        print("1. Make sure Bluetooth is enabled on your Mac")
        print("2. Try moving closer to the Arduino")
        print("3. Press the reset button on Arduino and try again")
        print("4. Check if another app is using the Arduino")
        print("5. Try running with sudo: sudo python find_arduino_address.py")
        return
    
    # Check each device in detail
    arduino_found = False
    for device in unique_devices:
        name = device.name or "Unknown"
        
        # name check first
        if any(keyword in name.lower() for keyword in ['arduino', 'activity', 'blesense']):
            print(f"⭐ Potential Arduino by name: {name} - {device.address}")
            if await detailed_device_check(device):
                arduino_found = True
                break
        
        # Check unknown devices
        # elif name == "Unknown" or name is None:
        #     print(f"🤔 Checking unknown device: {device.address}")
        #     if await detailed_device_check(device):
        #         arduino_found = True
        #         break


if __name__ == "__main__":
    asyncio.run(main())