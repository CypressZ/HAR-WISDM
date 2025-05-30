/* Edge Impulse + BLE Activity Monitor
 * Combines Edge Impulse inference with BLE data transmission
 * Copyright (c) 2022 EdgeImpulse Inc.
 */

/* Includes ---------------------------------------------------------------- */
#include <HAR_-_WISDM_inferencing.h>
#include <Arduino_LSM9DS1.h>
#include <ArduinoBLE.h>

/* Constant defines -------------------------------------------------------- */
#define CONVERT_G_TO_MS2    9.80665f
#define MAX_ACCEPTED_RANGE  2.0f

// Optional: Override sampling for WISDM-style data collection
// Uncomment these lines if you want to experiment with WISDM timing
// #define OVERRIDE_SAMPLING_RATE
// #ifdef OVERRIDE_SAMPLING_RATE
// #define WISDM_INTERVAL_MS 50  // 20 Hz like WISDM paper
// #endif

/* BLE Service and Characteristic UUIDs */
BLEService activityService("12345678-1234-1234-1234-123456789abc");
BLEStringCharacteristic activityCharacteristic("87654321-4321-4321-4321-cba987654321", BLERead | BLENotify, 200);

/* Private variables ------------------------------------------------------- */
static bool debug_nn = false; // Set this to true to see e.g. features generated from the raw signal

// Timing variables
unsigned long lastInference = 0;
unsigned long lastDataSend = 0;
const unsigned long INFERENCE_INTERVAL = 2000; // Run inference every 2 seconds
const unsigned long DATA_SEND_INTERVAL = 1000; // Send data every 1 second

// Current results - simplified
String currentActivity = "unknown";
float currentConfidence = 0.0;
ei_impulse_result_t lastResult = { 0 };
bool hasValidResult = false;

/**
* @brief      Arduino setup function
*/
void setup()
{
    Serial.begin(115200);
    while (!Serial);
    Serial.println("Edge Impulse + BLE Activity Monitor");

    // Initialize IMU
    if (!IMU.begin()) {
        Serial.println("Failed to initialize IMU!");
        while (1);
    } else {
        Serial.println("✓ IMU initialized");
    }

    // Initialize BLE
    if (!BLE.begin()) {
        Serial.println("Starting BLE failed!");
        while (1);
    }
    Serial.println("✓ BLE initialized");

    // Set BLE device name
    BLE.setLocalName("EdgeImpulseActivity");
    BLE.setDeviceName("EdgeImpulseActivity");
    BLE.setAdvertisedService(activityService);
    Serial.println("✓ Local name set");

    // Add characteristic to service
    activityService.addCharacteristic(activityCharacteristic);
    Serial.println("✓ Characteristic added to service");

    // Add service
    BLE.addService(activityService);
    Serial.println("✓ Service added");

    // Set initial value
    activityCharacteristic.writeValue("{}");
    Serial.println("✓ Initial characteristic value set");

    // Start advertising
    BLE.advertise();
    Serial.println("✓ BLE advertising started");

    // Validate Edge Impulse model
    if (EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME != 3) {
        Serial.println("ERR: EI_CLASSIFIER_RAW_SAMPLES_PER_FRAME should be equal to 3 (the 3 sensor axes)");
        return;
    }

    Serial.println("Edge Impulse + BLE Activity Monitor Ready!");
    Serial.println("Device name: EdgeImpulseActivity");
    Serial.println("Waiting for connections...");
}

/**
 * @brief Return the sign of the number
 */
float ei_get_sign(float number) {
    return (number >= 0.0) ? 1.0 : -1.0;
}

/**
* @brief      Main loop
*/
void loop()
{
    // Listen for BLE connections
    BLEDevice central = BLE.central();
    
    if (central) {
        Serial.print("Connected to central: ");
        Serial.println(central.address());
        
        while (central.connected()) {
            // Run inference periodically
            if (millis() - lastInference >= INFERENCE_INTERVAL) {
                runInference();
                lastInference = millis();
            }
            
            // Send data via BLE periodically
            if (millis() - lastDataSend >= DATA_SEND_INTERVAL && hasValidResult) {
                String jsonData = createJsonData();
                activityCharacteristic.writeValue(jsonData);
                Serial.println("Sent: " + jsonData);
                lastDataSend = millis();
            }
        }
        
        Serial.print("Disconnected from central: ");
        Serial.println(central.address());
    } else {
        // Run inference even when not connected (for debugging)
        if (millis() - lastInference >= INFERENCE_INTERVAL) {
            runInference();
            lastInference = millis();
        }
    }
}

/**
 * @brief Run Edge Impulse inference with walking bias correction
 */
void runInference() {
    Serial.println("Running inference...");

    // Allocate a buffer for the sensor values
    float buffer[EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE] = { 0 };

    // Collect sensor data
    for (size_t ix = 0; ix < EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE; ix += 3) {
        uint64_t next_tick = micros() + (EI_CLASSIFIER_INTERVAL_MS * 1000);

        // Read acceleration data
        IMU.readAcceleration(buffer[ix], buffer[ix + 1], buffer[ix + 2]);

        // Clamp values to acceptable range
        for (int i = 0; i < 3; i++) {
            if (fabs(buffer[ix + i]) > MAX_ACCEPTED_RANGE) {
                buffer[ix + i] = ei_get_sign(buffer[ix + i]) * MAX_ACCEPTED_RANGE;
            }
        }

        // Convert from G to m/s^2
        buffer[ix + 0] *= CONVERT_G_TO_MS2;
        buffer[ix + 1] *= CONVERT_G_TO_MS2;
        buffer[ix + 2] *= CONVERT_G_TO_MS2;

        delayMicroseconds(next_tick - micros());
    }

    // Create signal from buffer
    signal_t signal;
    int err = numpy::signal_from_buffer(buffer, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal);
    if (err != 0) {
        Serial.print("Failed to create signal from buffer: ");
        Serial.println(err);
        return;
    }

    // Run the classifier
    err = run_classifier(&signal, &lastResult, debug_nn);
    if (err != EI_IMPULSE_OK) {
        Serial.print("ERR: Failed to run classifier: ");
        Serial.println(err);
        return;
    }

    // Print the standard predictions for debugging
    Serial.println("Predictions:");
    for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
        Serial.print("    ");
        Serial.print(lastResult.classification[ix].label);
        Serial.print(": ");
        Serial.println(lastResult.classification[ix].value, 5);
    }

    // Enhanced logic to handle walking/stairs confusion
    float walkingConf = 0.0, upstairsConf = 0.0, downstairsConf = 0.0;
    float maxConfidence = 0.0;
    String detectedActivity = "unknown";
    
    // Extract confidence scores for the problematic activities
    for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
        String activity = String(lastResult.classification[ix].label);
        float confidence = lastResult.classification[ix].value;
        
        if (activity == "Walking") walkingConf = confidence;
        else if (activity == "Upstairs") upstairsConf = confidence;
        else if (activity == "Downstairs") downstairsConf = confidence;
        
        if (confidence > maxConfidence) {
            maxConfidence = confidence;
            detectedActivity = activity;
        }
    }

    // Apply strong walking bias correction
    // Case 1: Walking is very close to the winning prediction (within 0.15)
    if (walkingConf > 0.1 && (detectedActivity == "Upstairs" || detectedActivity == "Downstairs")) {
        if (walkingConf > (maxConfidence - 0.15)) {
            Serial.print("BIAS CORRECTION: ");
            Serial.print(detectedActivity);
            Serial.print(" (");
            Serial.print(maxConfidence, 3);
            Serial.print(") -> Walking (");
            Serial.print(walkingConf, 3);
            Serial.println(") - close scores, favoring walking");
            
            detectedActivity = "Walking";
            maxConfidence = walkingConf;
        }
    }
    
    // Case 2: Three-way tie or very close scores - strongly favor walking
    float scoreDiff1 = fabs(walkingConf - upstairsConf);
    float scoreDiff2 = fabs(walkingConf - downstairsConf);
    float scoreDiff3 = fabs(upstairsConf - downstairsConf);
    
    if (scoreDiff1 < 0.05 && scoreDiff2 < 0.05 && scoreDiff3 < 0.05 && walkingConf > 0.25) {
        // All three scores are nearly identical - assume flat walking
        Serial.print("THREE-WAY TIE DETECTED: Walking(");
        Serial.print(walkingConf, 3);
        Serial.print(") Upstairs(");
        Serial.print(upstairsConf, 3);
        Serial.print(") Downstairs(");
        Serial.print(downstairsConf, 3);
        Serial.println(") -> Defaulting to Walking");
        
        detectedActivity = "Walking";
        maxConfidence = walkingConf;
    }

    // Update results
    currentActivity = detectedActivity; // Keep original case from Edge Impulse model
    currentConfidence = maxConfidence;
    hasValidResult = true;

    Serial.print("FINAL: ");
    Serial.print(currentActivity);
    Serial.print(" (confidence: ");
    Serial.print(currentConfidence, 3);
    Serial.println(")");
    
    #if EI_CLASSIFIER_HAS_ANOMALY == 1
    Serial.print("Anomaly score: ");
    Serial.println(lastResult.anomaly, 3);
    #endif
}

/**
 * @brief Create JSON data for BLE transmission - matches Python app format
 */
String createJsonData() {
    // Get current sensor readings for real-time display
    float accelX, accelY, accelZ;
    float gyroX, gyroY, gyroZ;
    
    if (IMU.accelerationAvailable()) {
        IMU.readAcceleration(accelX, accelY, accelZ);
    }
    
    if (IMU.gyroscopeAvailable()) {
        IMU.readGyroscope(gyroX, gyroY, gyroZ);
    }
    
    // Create JSON in the format expected by Python app
    String json = "{";
    json += "\"act\":\"" + currentActivity + "\",";          // Keep original case from Edge Impulse
    json += "\"confidence\":" + String(currentConfidence, 3) + ",";
    json += "\"ax\":" + String(accelX, 3) + ",";             // Accelerometer X
    json += "\"ay\":" + String(accelY, 3) + ",";             // Accelerometer Y  
    json += "\"az\":" + String(accelZ, 3) + ",";             // Accelerometer Z
    json += "\"gx\":" + String(gyroX, 1) + ",";              // Gyroscope X
    json += "\"gy\":" + String(gyroY, 1) + ",";              // Gyroscope Y
    json += "\"gz\":" + String(gyroZ, 1) + ",";              // Gyroscope Z
    json += "\"t\":" + String(millis());                     // Timestamp
    json += "}";
    
    return json;
}

#if !defined(EI_CLASSIFIER_SENSOR) || EI_CLASSIFIER_SENSOR != EI_CLASSIFIER_SENSOR_ACCELEROMETER
#error "Invalid model for current sensor"
#endif