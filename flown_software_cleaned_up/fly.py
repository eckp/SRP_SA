#!/usr/bin/python3

'''
Main program running the idle, armed, in-flight and recovery loop for the rocket
'''

#####################################
# imports

import os
os.chdir('/home/pi/Documents/SRP/flight_software')
import logging
import time
import subprocess
import random
import threading
import csv
import sys
import shutil
import json
import RPi.GPIO as GPIO
import altimu10v5

#####################################
# variable definitions

state = 'SYSTEMS_CHECK'  # initial state
flight_start = 0  # variable to hold start of flight. Prevents premature transit from LAUNCHED into LANDED due to similar sensor measurements

# altitude (smoothed) and vertical velocity calculations
p0 = []
p = [0, 0]  # last two pressure values
alt = [0, 0]  # last two altitude values
vv = [0,0]  # last two vertical velocity values

# get config variables from config.json file into global namespace
with open('config.json') as config_file:
    globals().update(json.load(config_file))

#####################################
# statemachine-related definitions

def battery_full():
    '''Checks battery level'''
    # dummy function for now because RPi has no ADC GPIO...
    if dry_run:
        return int(input('battery level (1/0)'))
    ret = not GPIO.input(battery_level_pin)  # check if low voltage alarm by Zero LiPo shim pulled the battery_level pin to ground
    if ret:  # GPIO indicates whether pin is HIGH or LOW, so if it is HIGH, all is ok
        logging.warning('battery not charged')
    return not ret

def sensors_present():
    '''Checks if all sensors are adressable'''
    if dry_run:
        return int(input('sensors present (1/0)'))
    i2cdetect = subprocess.Popen(['/usr/sbin/i2cdetect', '-y', '1'],stdout=subprocess.PIPE,)
    i2cout = str(i2cdetect.stdout.read())
    addresses = [hex(altimu10v5.constants.LIS3MDL_ADDR)[2:],
                hex(altimu10v5.constants.LPS25H_ADDR)[2:],
                hex(altimu10v5.constants.LSM6DS33_ADDR)[2:]]
    ret = all(map(lambda x: x in i2cout, addresses))
    if not ret:
        logging.warning('sensors not present')
    return ret

def arm_switch_on():
    '''Checks if arm switch is on'''
    if dry_run:
        return int(input('arm switch (1/0)'))
    ret = not GPIO.input(arm_switch_pin)
#    logging.debug('arm switch state: {0}'.format(ret))
    return ret  # GPIO indicates whether pin is HIGH or LOW, so if it is HIGH, the switch is off, not pulling the pin to ground

def liftoff_signal_received():
    '''Checks if liftoff signal was set'''
    if dry_run:
        return int(input('liftoff signal (1/0)'))
    return GPIO.input(liftoff_pin)  # HIGH means that 3.3V (5V via level shifter) is applied to pin

def vote_deploy():
    '''Sends a vote signal to the SRP PCB to deploy the parachute'''
    GPIO.output(deploy_vote_pin, GPIO.LOW)  # pull SRP PCB pin to ground
    logging.info('deploy vote sent')

def on_landing():
    '''Function to be run when landing is detected.
    It waits 2 seconds before stopping the sensor threads and writing the data to a file'''
    logging.info('waiting 2 seconds to record landing data')
    time.sleep(2)

    if dry_run:
        logging.debug("ran the on_landing function")
        return 0
    with threading.Lock():
        logging.info('stopping at {}'.format(time.time()))
        stop.set()
        for thread in threads:
            thread.join()
        for sensor in sensors:
            with open(datafilename+sensor.name+'.csv', 'a') as f:
                csv.writer(f).writerow(['# final save at {}'.format(time.time())])
                csv.writer(f).writerows(sensor.data[sensor.save_end:])
            print('logged data from {0}'.format(sensor.name))
    logging.debug('saved all data')

def cleanup():
    logging.debug('cleaning up GPIO now')
#    status_LED.off()
    GPIO.cleanup()

def update_statemachine():
    '''Updates the state variable according to the current state and any inputs'''
    global state
    logging.info(state)
    if state == 'ERROR':
        # output audio/visual signal of ERROR state
        status_LED.red.blink(blink_half_period)
        if battery_full() and sensors_present():
            # output audio/visual signal of transition into IDLE state
            status_LED.red.off()
            state = 'IDLE'

    elif state == 'SYSTEMS_CHECK':
        if battery_full() and sensors_present():
            # output audio/visual signal of transition into IDLE state
            state = 'IDLE'
        else:
            # output audio/visual signal of transition into ERROR state
            state = 'ERROR'

    elif state == 'IDLE':
        status_LED.green.on()
        if arm_switch_on():
            # output audio/visual signal of transition into ARMED state
            status_LED.green.off()
            status_LED.green.blink(blink_half_period*5)
            state = 'ARMED'

    elif state == 'ARMED':
        if not imu.gyroAccelEnabled:
            if not dry_run:
                logging.debug('Calibrating Gyro and Accelerometer')
                imu.enable()
                logging.debug('Calibrating Barometer')
                time.sleep(0.5)
                # zero alt
                global p0, p
                for i in range(50):  # for more precise calibration increase number of readings (for reference: AltIMU takes 4000 to calibrate)
                    p0.append(imu.lps25h.get_barometer_raw()/40.96)  # converting from raw sensor reading to Pa by dividing by 40.96
                    time.sleep(baro.interval)  # change interval if you want to spread out readings more for instance
                p0 = sum(p0)/len(p0)
                logging.debug('Calibrated barometer to p0={0}'.format(p0))
                p = [p0]*2
                logging.debug('Calibration done, starting threads')
                status_LED.green.off()
                status_LED.green.blink(blink_half_period)
                # start threads to record the data
                print('starting at {}'.format(time.time()))
                for thread in threads:
                    thread.start()
        if not arm_switch_on():
            # output audio/visual signal of transition into IDLE state
            status_LED.green.off()
            state = 'IDLE'
        elif liftoff_signal_received():
            # output audio/visual signal of transition into LAUNCHED state
            status_LED.green.off()
            global flight_start
            flight_start = time.time()
            state = 'LAUNCHED'
            # start the thread to watch the vertical velocity etc

    elif state == 'LAUNCHED':
        status_LED.alternate()
        tm = time.time()
        if (tm > flight_start+min_deploy_time) and (vv[1] < vv_deploy_threshold):
            vote_deploy()
            # output audio/visual signal of transition into DEPLOYED state
            status_LED.off()
            state = 'DEPLOYED'
        elif ((tm > flight_start+min_flight_duration) and (abs(alt[1]) < landing_altitude_range) and (abs(vv[1]) < landing_vertical_velocity_range)) or not arm_switch_on():
            on_landing()
            # output audio/visual signal of transition into LANDED state
            status_LED.off()
            state = 'LANDED'

    elif state == 'DEPLOYED':
        status_LED.red.on()
        tm = time.time()
        if ((tm > flight_start+min_flight_duration) and (abs(alt[1]) < landing_altitude_range) and (abs(vv[1]) < landing_vertical_velocity_range)) or not arm_switch_on():
            on_landing()
            # output audio/visual signal of transition into LANDED state
            status_LED.red.off()
            state = 'LANDED'

    elif state == 'LANDED':
        # on_landing already finished saving before entering 'LANDED'
        status_LED.green.on()
        if not arm_switch_on():  # does not seem to work properly?
            logging.debug('Arm switch switched off, going to exit/power off now')
            time.sleep(1)
            if dry_run:  # remove comment before flight
                sys.exit(0)
            else:
                subprocess.call('sudo shutdown -h now', shell=True)

    else:
        # output audio/visual signal of transition into ERROR state
        state = 'ERROR'

#####################################
# sensor-related definitions

def dummy():
    '''Dummy sensor readout function'''
    return random.randint(0,100)


class LED:
    def __init__(self, pin, half_interval=0.3):
        self.pin = pin
        GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.HIGH)
        self.state = 0
        self.half_interval = half_interval
        self.blinking = threading.Event()

    def on(self):
        self.__stop_blinking()
        self.state = 1
        GPIO.output(self.pin, not self.state)

    def off(self):
        self.__stop_blinking()
        self.state = 0
        GPIO.output(self.pin, not self.state)

    def __blink_thread(self):
        while self.blinking.is_set():
            self.state = not self.state
            GPIO.output(self.pin, not self.state)
            time.sleep(self.half_interval)

    def __stop_blinking(self):
        if self.blinking.is_set():
            self.blinking.clear()
            self.thread.join()

    def blink(self, half_interval=None):
        if half_interval != None:
            self.half_interval = half_interval
        if not self.blinking.is_set():
            self.thread = threading.Thread(target=self.__blink_thread)
            self.blinking.set()
            self.thread.start()

class StatusLED:
    def __init__(self, green, red, half_interval):
        self.green = green
        self.red = red
        self.alternating = False
        self.half_interval = half_interval

    def alternate(self):
        if not self.alternating:
            self.green.blink(self.half_interval)
            time.sleep(self.half_interval)
            self.red.blink(self.half_interval)
            self.alternating = True

    def off(self):
        self.green.off()
        self.red.off()
        self.alternating = False


class Sensor:
    '''Provides functions related to reading out, storing and saving data of the sensors'''
    def __init__(self, name, interval, function):
        self.name = name
        self.interval = interval
        self.function = function
        self.data = []
        self.save_start = 0
        self.save_end = 0

    def read(self):
        '''Function meant to be run as thread, reading data from sensor and storing it in attribute'''
        serial = 0
        next_call = time.time()
        while not stop.is_set():
            serial += 1
            self.data.append([serial, time.time(), self.function()])
            # pressure to altitude conversion for deploy voting
            if self.name == 'baro':
                global p, alt, vv
                p = [p[1], exp_factor_p*(self.data[-1][2]/40.96) + (1-exp_factor_p)*p[0]]  # conversion from raw readings to Pa and smoothing
                alt = [alt[1], T0/a*((p[1]/p0)**(-(R*a)/g0)-1)]  # conversion from p to h, no smoothing
                vv = [vv[1], exp_factor_vv*((alt[1]-alt[0])/baro.interval) + (1-exp_factor_vv)*vv[0]]  # conversion from h to vv
                logging.debug('current pressure, altitude and vertical velocity: '+str(p[1])+' '+str(alt[1])+' '+str(vv[1]))
            next_call += self.interval
            time.sleep(max(0, next_call - time.time())) # sleep only interval - time consumed in current call


def autosave(sensor,interval):
    '''Every interval seconds this function autosaves all sensors to their logfiles'''
    num = 0
    time.sleep(interval)
    next_call = time.time()
    while not stop.is_set():
        sensor.save_start = round(num*interval/sensor.interval)
        num += 1
        sensor.save_end = round(num*interval/sensor.interval)
        with open(datafilename+sensor.name+'.csv', 'a') as f: # opening and closing file every time
            csv.writer(f).writerow(['#### {} autosave nr {}'.format('{:.6f}'.format(next_call)[6:],num)])
            csv.writer(f).writerows(sensor.data[sensor.save_start:sensor.save_end])
            delta = time.time() - next_call
            csv.writer(f).writerow(['# autosave took {:.6f}'.format(delta)])
        next_call += interval
        time.sleep(max(0, interval - delta))


#####################################
# init

datafilename = 'data/'+time.strftime('%d-%m-%y_%H-%M-%S')+'_'

logging.basicConfig(level=logging.DEBUG,  # set to INFO if speed up is necessary to prevent printing a lot
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    filename=datafilename[:-1]+'.log',
                    filemode='a')
console = logging.StreamHandler(sys.stdout)
#console.setLevel(logging.DEBUG)  # set to INFO if you want to speed up the loop
logging.getLogger('').addHandler(console)

# saving configuration from config file:
shutil.copyfile('config.json', datafilename+'config.json')

imu = altimu10v5.IMU()
if dry_run:
    baro = Sensor('baro', 0.1, dummy)
    acc = Sensor('acc', 0.01, dummy)
    gyro = Sensor('gyro', 0.01, dummy)
    mag = Sensor('mag', 0.1, dummy)
else:
    baro = Sensor('baro', intervals['baro'], imu.lps25h.get_barometer_raw)
    acc = Sensor('acc', intervals['acc'], imu.lsm6ds33.get_accelerometer_raw)
    gyro = Sensor('gyro', intervals['gyro'], imu.lsm6ds33.get_gyro_angular_velocity)
    mag = Sensor('mag', intervals['mag'], imu.lis3mdl.get_magnetometer_raw)

# initialise GPIO ins and outs
GPIO.setmode(GPIO.BOARD)
GPIO.setup(battery_level_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(arm_switch_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(liftoff_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(deploy_vote_pin, GPIO.OUT, initial=GPIO.LOW)
green_LED = LED(green_LED_pin, blink_half_period)
red_LED = LED(red_LED_pin, blink_half_period)
status_LED = StatusLED(green_LED, red_LED, blink_half_period)

sensors = [baro, acc, gyro, mag]
threads = [threading.Thread(target=s.read) for s in sensors] \
        + [threading.Thread(target=autosave, args=(s,1,)) for s in sensors]

stop = threading.Event()


#####################################
# main
if __name__ == '__main__':
    try:
        while True:
            start = time.time()
            update_statemachine()
            time.sleep(max(0,(state_intervals[state]-(time.time()-start))))  # slows down the loop to max x Hz
    finally:
        cleanup()
