## Steps to run

1. ```pip install -r requirements.txt``` to install any required python libraries
2. Run ```find_arduino_address.py``` to find your arduino device address
3. Replace the found address (eg. 64609202-37DA-83AF-1A6A-87D95E127B3F) in ```app.py``` by searching for ```ARDUINO_ADDRESS = ```
4. Flash **nano_ble33_sense_accelerometer_custom** to board to start inference + BLE, launch Serial Monitor for logs
5. Run the app from ```/ble_app```
```
streamlit run app.py
```


## Notes

### Model Limitation & Bias Correction
- Activities "Upstairs," "Downstairs," and "Walking" are easily confused by the model as pointed out by the original paper (that contributed the WISDM dataset). When three activities show the same confidences, the model automatically favors "Downstairs" because of its alphabetical ordering. We made the change so that it favors "Walking" since flat-ground walking is statistically more common in daily activities.
- Our bias correction algorithm implements two strategies: close score correction (within 0.15) and three-way tie resolution (defaulting to walking).

### Real-time Performance
- Arduino runs inference every 2 seconds and sends data every 1 second, so the UI display shows the activity only after it had been performed for two seconds.
- Inference performs significantly better when activities are performed for extended periods (>10 seconds) rather than brief transitions.
- The WISDM dataset was collected with the phone placed in the front pants pocket, so we follow the same positioning for the Arduino board. However, since we are connecting a power source to the Arduino board and the power cable interferes with placing it in a pocket, and to make it more accurate, we strap the board to the pants pocket location instead of directly placing it in the pocket.
- Arduino Nano 33 BLE Sense positioned with the same orientation as smartphones in WISDM study: Y-axis captures vertical movement, Z-axis captures forward/backward motion, X-axis captures side-to-side movement.
