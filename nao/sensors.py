"""ALMemory keys that are polled for the live telemetry panel."""

D = "Device/SubDeviceList/"

TOUCH_KEYS = {
    "head_front":   D + "Head/Touch/Front/Sensor/Value",
    "head_middle":  D + "Head/Touch/Middle/Sensor/Value",
    "head_rear":    D + "Head/Touch/Rear/Sensor/Value",
    "lhand_back":   D + "LHand/Touch/Back/Sensor/Value",
    "lhand_left":   D + "LHand/Touch/Left/Sensor/Value",
    "lhand_right":  D + "LHand/Touch/Right/Sensor/Value",
    "rhand_back":   D + "RHand/Touch/Back/Sensor/Value",
    "rhand_left":   D + "RHand/Touch/Left/Sensor/Value",
    "rhand_right":  D + "RHand/Touch/Right/Sensor/Value",
    "lfoot_bumper_left":  D + "LFoot/Bumper/Left/Sensor/Value",
    "lfoot_bumper_right": D + "LFoot/Bumper/Right/Sensor/Value",
    "rfoot_bumper_left":  D + "RFoot/Bumper/Left/Sensor/Value",
    "rfoot_bumper_right": D + "RFoot/Bumper/Right/Sensor/Value",
    "chest_button": D + "ChestBoard/Button/Sensor/Value",
}

SONAR_KEYS = {
    "sonar_left":  D + "US/Left/Sensor/Value",
    "sonar_right": D + "US/Right/Sensor/Value",
}

IMU_KEYS = {
    "angle_x": D + "InertialSensor/AngleX/Sensor/Value",
    "angle_y": D + "InertialSensor/AngleY/Sensor/Value",
    "acc_x":   D + "InertialSensor/AccelerometerX/Sensor/Value",
    "acc_y":   D + "InertialSensor/AccelerometerY/Sensor/Value",
    "acc_z":   D + "InertialSensor/AccelerometerZ/Sensor/Value",
    "gyro_x":  D + "InertialSensor/GyroscopeX/Sensor/Value",
    "gyro_y":  D + "InertialSensor/GyroscopeY/Sensor/Value",
    "gyro_z":  D + "InertialSensor/GyroscopeZ/Sensor/Value",
}

FSR_KEYS = {
    "lfoot_weight": D + "LFoot/FSR/TotalWeight/Sensor/Value",
    "rfoot_weight": D + "RFoot/FSR/TotalWeight/Sensor/Value",
    "lfoot_cop_x":  D + "LFoot/FSR/CenterOfPressure/X/Sensor/Value",
    "lfoot_cop_y":  D + "LFoot/FSR/CenterOfPressure/Y/Sensor/Value",
    "rfoot_cop_x":  D + "RFoot/FSR/CenterOfPressure/X/Sensor/Value",
    "rfoot_cop_y":  D + "RFoot/FSR/CenterOfPressure/Y/Sensor/Value",
}

BATTERY_KEYS = {
    "battery_charge":  D + "Battery/Charge/Sensor/Value",
    "battery_current": D + "Battery/Current/Sensor/Value",
    "battery_temp":    D + "Battery/Temperature/Sensor/Value",
}

JOINT_NAMES = [
    "HeadYaw", "HeadPitch",
    "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw", "LHand",
    "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw", "RHand",
    "LHipYawPitch", "LHipRoll", "LHipPitch", "LKneePitch", "LAnklePitch", "LAnkleRoll",
    "RHipRoll", "RHipPitch", "RKneePitch", "RAnklePitch", "RAnkleRoll",
]

# Rough joint limits in degrees (NAO v6) used for the UI sliders.
JOINT_LIMITS_DEG = {
    "HeadYaw": (-119.5, 119.5), "HeadPitch": (-38.5, 29.5),
    "LShoulderPitch": (-119.5, 119.5), "LShoulderRoll": (-18, 76),
    "LElbowYaw": (-119.5, 119.5), "LElbowRoll": (-88.5, -2), "LWristYaw": (-104.5, 104.5), "LHand": (0, 57.3),
    "RShoulderPitch": (-119.5, 119.5), "RShoulderRoll": (-76, 18),
    "RElbowYaw": (-119.5, 119.5), "RElbowRoll": (2, 88.5), "RWristYaw": (-104.5, 104.5), "RHand": (0, 57.3),
    "LHipYawPitch": (-65.6, 42.4), "LHipRoll": (-21.7, 45.3), "LHipPitch": (-88, 27.7),
    "LKneePitch": (-5.3, 121), "LAnklePitch": (-68.2, 52.9), "LAnkleRoll": (-22.8, 44.1),
    "RHipRoll": (-45.3, 21.7), "RHipPitch": (-88, 27.7),
    "RKneePitch": (-5.3, 121), "RAnklePitch": (-68.2, 52.9), "RAnkleRoll": (-44.1, 22.8),
}

JOINT_TEMP_KEYS = {j: D + j + "/Temperature/Sensor/Value" for j in JOINT_NAMES}

ALL_KEYS = {}
for group in (TOUCH_KEYS, SONAR_KEYS, IMU_KEYS, FSR_KEYS, BATTERY_KEYS):
    ALL_KEYS.update(group)
ALL_KEYS.update({"temp_" + j: k for j, k in JOINT_TEMP_KEYS.items()})

POSTURES = ["Stand", "StandInit", "StandZero", "Crouch", "Sit", "SitRelax", "LyingBelly", "LyingBack"]

LED_GROUPS = {
    "FaceLeds": "Eyes",
    "LeftFaceLeds": "Left eye",
    "RightFaceLeds": "Right eye",
    "EarLeds": "Ears",
    "ChestLeds": "Chest",
    "BrainLeds": "Head (brain)",
    "LeftFootLeds": "Left foot",
    "RightFootLeds": "Right foot",
    "AllLeds": "All",
}

STIFFNESS_CHAINS = ["Body", "Head", "LArm", "RArm", "LLeg", "RLeg"]
BREATH_CHAINS = ["Body", "Head", "Arms", "Legs", "LArm", "RArm"]
