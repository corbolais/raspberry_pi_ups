#!/usr/bin/python

import time
import os, sys
import logging
import socket
import json
import signal
from powerpi import Powerpi

logging.basicConfig(level=logging.INFO)
GPIO4_AVAILABLE = True

try:
    import RPi.GPIO as GPIO   
except :
    GPIO4_AVAILABLE = False
    logging.error("Error importing GPIO library, UPS will work without interrupt")

ENABLE_UDP = True
UDP_PORT = 40001
serverAddressPort   = ("127.0.0.1", UDP_PORT)
UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
disconnectflag = False
ppi = Powerpi()
reportRound = 0
client = None

if ppi.MQTT_ENABLED:
    import paho.mqtt.client as mqtt
    def on_MQTTconnect(client, userdata, flags, rc):
        reasoning(rc, "connected")

    def on_MQTTdisconnect(client, userdata, rc):
        reasoning(rc, "disconnected")

    def reasoning(rc, action="unknown action"):
        if rc == 0:
            logging.info("MQTT Connection successful")
        elif rc == 1:
            logging.info("MQTT Connection refused - incorrect protocol version")
        elif rc == 2: 
            logging.info("MQTT Connection refused - invalid client identifier")
        elif rc == 3: 
            logging.info("MQTT Connection refused - server unavailable")
        elif rc == 4: 
            logging.info("MQTT Connection refused - bad username or password")
        elif rc == 5:
            logging.info("MQTT Connection refused - not authorized")
        else:
            logging.info("MQTT " + action + " with unknown result code " + str(rc))
    
    client = mqtt.Client(ppi.MQTT_CLIENTID, clean_session=True)

    client.username_pw_set(username=ppi.MQTT_USERNAME, password=ppi.MQTT_PASSWORD)
    client.on_connect = on_MQTTconnect
    client.on_MQTTdisconnect = on_MQTTdisconnect
    client.reconnect_delay_set(1, 120)
    client.connect_async(ppi.MQTT_HOSTNAME, ppi.MQTT_PORT, 60)
    client.loop_start()

    import atexit
    atexit.register(client.loop_stop)

def read_status(clear_fault=False):
        global disconnectflag, ENABLE_UDP, reportRound
        err, status = ppi.read_status(clear_fault)

        if err:
            time.sleep(1)
            return

        reportRound += 1

        if status["PowerInputStatus"] == "Not Connected" and disconnectflag == False :
            disconnectflag = True
            message = "echo Power Disconnected, system will shutdown in %d minutes! | wall -n " % (status['TimeRemaining'])
            os.system(message)
        
        if status["PowerInputStatus"] == "Connected" and disconnectflag == True :
            disconnectflag = False
            message = "echo Power Restored, battery at %d percent | wall -n " % (status['BatteryPercentage'])
            os.system(message)
        
        if ENABLE_UDP:
            try:
                UDPClientSocket.sendto(json.dumps(status,indent=4,sort_keys=True), serverAddressPort)
            except Exception as ex:
                logging.error(ex)

        if client != None:
            if (reportRound % ppi.MQTT_INTERVAL == 0):
                try:
                    client.publish(ppi.MQTT_BASETOPIC + "/status", payload=json.dumps(status,indent=4,sort_keys=True), qos=0, retain=False)
                    for key, value in status.items():
                        client.publish(ppi.MQTT_BASETOPIC + "/status/" + key, payload=value, qos=0, retain=False)
                except Exception as ex:
                    logging.error(ex)

        logging.debug(status)

        if(status['BatteryVoltage'] < ppi.VBAT_LOW):
                ppi.bat_disconnect()
                os.system('sudo shutdown now')

def interrupt_handler(channel):
    read_status(True) 

def main():
    if ppi.initialize():
        sys.exit(1)

    if GPIO4_AVAILABLE:
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(4, GPIO.FALLING, callback=interrupt_handler, bouncetime=200)
        except Exception as ex:
            logging.error("Error attaching interrupt to GPIO4, UPS will work without interrupt.")
        
    while (True):
        read_status()

if __name__=="__main__":
    main()
                
