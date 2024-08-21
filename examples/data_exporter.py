import bme680
import time
import datetime
#from datetime import date, timedelta
import logging
from flask import Flask, Response
from prometheus_client import Counter, Gauge, start_http_server, generate_latest
FORMAT = '%(message)s'
CURRENT_TIMESTAMP=datetime.date.today()

content_type = str('text/plain; version=0.0.4; charset=utf-8')

#########################################################
def bme680_init():
    global sensor, gas_baseline, hum_baseline, hum_weighting
    start_time = time.time()
    localStartTime = time.localtime(start_time)
    logging.debug("Starting bme680_init: %s",time.strftime("%Y-%m-%d %H:%M:%S",localStartTime))

    try:
        sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    except (RuntimeError, IOError):
        logging.debug("bme680_init IOError exception on I2C_ADDR_PRIMARY using SECONDARY")
        sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)

# These oversampling settings can be tweaked to
# change the balance between accuracy and noise in
# the data.

    sensor.set_humidity_oversample(bme680.OS_2X)
    sensor.set_pressure_oversample(bme680.OS_4X)
    sensor.set_temperature_oversample(bme680.OS_8X)
    sensor.set_filter(bme680.FILTER_SIZE_3)
    sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)

    sensor.set_gas_heater_temperature(320)
    sensor.set_gas_heater_duration(150)
    sensor.select_gas_heater_profile(0)

# start_time and curr_time ensure that the
# burn_in_time (in seconds) is kept track of.

    start_time = time.time()
    curr_time = time.time()
    burn_in_time = 300
    burn_in_data = []

    try:
        # Collect gas resistance burn-in values, then use the average
        # of the last 50 values to set the upper limit for calculating
        # gas_baseline.
        logging.info('Collecting gas resistance burn-in data for 5 mins\n')
        while curr_time - start_time < burn_in_time:
            curr_time = time.time()
            if sensor.get_sensor_data() and sensor.data.heat_stable:
                gas = sensor.data.gas_resistance
                burn_in_data.append(gas)
                logging.info('Gas: {0} Ohms'.format(gas))
                time.sleep(1)

        gas_baseline = sum(burn_in_data[-50:]) / 50.0

        # Set the humidity baseline to 40%, an optimal indoor humidity.
        hum_baseline = 40.0

        # This sets the balance between humidity and gas reading in the
        # calculation of air_quality_score (25:75, humidity:gas)
        hum_weighting = 0.25

        logging.info('Gas baseline: {0} Ohms, humidity baseline: {1:.2f} %RH\n'.format(
            gas_baseline,
            hum_baseline))
    except Exception as e:
        logging.info('Exception in bme680_init, get_sensor_data: %s',e, exc_info=True)

######################################################################
def get_bme680_readings():
#    humidity, temperature, pressure, iaq

    if sensor.get_sensor_data() and sensor.data.heat_stable:
        gas = sensor.data.gas_resistance
        gas_offset = gas_baseline - gas
        logging.debug('gas: {0} gas_baseline: {1} gas_offset: {2}'.format(gas,gas_baseline,gas_offset))
        hum = sensor.data.humidity
        hum_offset = hum - hum_baseline
        logging.debug('hum: {0} hum_baseline: {1} hum_offset: {2}'.format(hum,hum_baseline,hum_offset))
        # Calculate hum_score as the distance from the hum_baseline.
        if hum_offset > 0:
            hum_score = (100 - hum_baseline - hum_offset)
            hum_score /= (100 - hum_baseline)
            hum_score *= (hum_weighting * 100)

        else:
            hum_score = (hum_baseline + hum_offset)
            hum_score /= hum_baseline
            hum_score *= (hum_weighting * 100)
        logging.debug('hum_score: {0} hum_weighting: {1}'.format(hum_score,hum_weighting))
        # Calculate gas_score as the distance from the gas_baseline.
        if gas_offset > 0:
            gas_score = (gas / gas_baseline)
            gas_score *= (100 - (hum_weighting * 100))

        else:
            gas_score = 100 - (hum_weighting * 100)
        logging.debug('gas_score: {0} hum_score: {1}'.format(gas_score,hum_score))
        # Calculate air_quality_score.
        air_quality_score = hum_score + gas_score
        logging.debug('air_quality_score: {0}'.format(air_quality_score))
        
        logging.info("Gas baseline: {0} Ohms, Pressure: {1:.2f} ,Temperature: {2:.2f} ,Humidity baseline: {3:.2f} %RH IAQ: {4:.2f}".format(
            gas,sensor.data.pressure,sensor.data.temperature,hum,air_quality_score))

        response = {"temperature": sensor.data.temperature,
                    "humidity": hum,
                    "pressure": sensor.data.pressure,
                    "iaq": air_quality_score}
        return response
    
# response = {"temperature": temperature, "humidity": humidity, "pressure": pressure, "iaq": iaq}
# return response
#            time.sleep(1)

app = Flask(__name__)

current_humidity = Gauge(
        'current_humidity',
        'the current humidity percentage, this is a gauge as the value can increase or decrease',
        ['room']
)

current_temperature = Gauge(
        'current_temperature',
        'the current temperature in celsius, this is a gauge as the value can increase or decrease',
        ['room']
)

current_pressure = Gauge(
        'current_pressure',
        'the current pressure, this is a gauge as the value can increase or decrease',
        ['room']
)

current_iaq = Gauge(
        'current_iaq',
        'the current indoor air quality, this is a gauge as the value can increase or decrease',
        ['room']
)

@app.route('/metrics')
def metrics():
    metrics = get_bme680_readings()
    current_humidity.labels('basement').set(metrics['humidity'])
    current_temperature.labels('basement').set(metrics['temperature'])
    current_pressure.labels('basement').set(metrics['pressure'])
    current_iaq.labels('basement').set(metrics['iaq'])
    return Response(generate_latest(), mimetype=content_type)

if __name__ == '__main__':
    logging.basicConfig(format=FORMAT,filename='/home/traleigh/logs/'+str(CURRENT_TIMESTAMP)+'-bme680-exporter.log', 
                        encoding='utf-8', level=logging.DEBUG) 
    bme680_init()
    app.run(host='0.0.0.0', port=5000)