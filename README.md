# SRP Separation Anxiety flight data

On 24/5/2019 the SRP rocket of Team Hangover was successfully launched from 't Harde, carrying an egg and several sensors on board.

## Flight description

After a stable ascent, the rocket reached an apogee of around 714m.
Unfortunately the parachute did not deploy, despite successful separation of the electronics compartment from the main body. This separation slowed the rocket down to a descent speed around 30m/s, saving the SD card and Raspberry Pi flight computer at impact but not the egg.

## Recorded data

The main sensor on board of the rocket was the [AltIMU10v5](https://www.pololu.com/product/2739) from Pololu, containing a [barometer](https://www.pololu.com/file/0J761/LPS25H.pdf), [accelerometer, gyro](https://www.pololu.com/file/0J1087/LSM6DS33.pdf) and [magnetometer](https://www.pololu.com/file/0J1089/LIS3MDL.pdf).
Only the raw sensor readings were saved in addition to the configuration and calibration data necessary to reconstruct the flight afterwards.

The .csv files for each sensor contain the timestamps and readings since the arming of the rocket up until landing/crashing. Additionally, the .log file contains the current state of the state machine with timestamp, as well as some debug logs showing the values of pressure, altitude and vertical velocity which are calculated on the fly but not saved.

### Notes

- The data files ended with null bytes because the flight computer did not shut down cleanly and might have been writing to the file at that moment (hard impact on the ground). I have removed these from these copies of the data files to make it possible to post-process them.
- For a yet unknown reason the .log file ended before apogee (at 12s after launch) while the data files only end 32 seconds into the flight, at approx. 220m altitude on the way down.
- I've also included a sample set of files from a test run of the flight computer at EWI for reference of a clean flight (in the elevator) with working log files and clean shutdown (data/13-05-19_18-32-06*).


## post.py

To quickly analyse the flight data I wrote a Python script that plots both the raw sensor data and the reconstructed altitudes and vertical velocities from the sensor data files. It also annotates the state changes which it reads from the .log file to illustrate the functioning of the state machine.

The conversion factors from raw sensor data to usable units are the following (I'm not that sure about the angular rate as it should be around 50 to match the magnetometer heading change):
- pressure [Pa] = x/40.96
- acceleration [g] = x*0.122/1000
- angular rate [dps] = x*35/1000
- magnetic field strength [gauss] = x/6842


>Tip: run the script in PyCharm in an interactive console to be able to access the namespace containing the data after the script finishes.

I have included annotation lines for the deploy vote window of the SRP board, to be able to assess whether the flight computer successfully sent the deploy vote at apogee, which it did!! (if the log had not stopped before apogee we could have cross-checked with that as well)

### Notes

- The accelerometer data appears to have clipped during the propulsive phase
- The gyroscope data appears to have clipped a few times during tumbling after separation
- The magnetometer data looks sensible, as during ascent the rocket rolls about 1.5 revolutions, where the magnetic field in x and y varies sinusoidally with an amplitude of 0.55 gauss, a value that is comparable to the earth magnetic field intensity


## License
[MIT](https://choosealicense.com/licenses/mit/)