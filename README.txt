# SRP Separation Anxiety flight data

On 24/5/2019 the SRP rocket of Team Hangover was launched from 't Harde, carrying an egg and several sensors on board.

## Flight description

Unfortunately the parachute did not deploy, despite successful separation of the electronics compartment from the main body. This separation slowed the rocket down to a descent speed around 30m/s, saving the SD card and flight computer but not the egg.

## Recorded data

The main sensor on board of the rocket was the [AltIMU10v5](https://www.pololu.com/product/2739) from Pololu, containing a [barometer](https://www.pololu.com/file/0J761/LPS25H.pdf), [accelerometer, gyro](https://www.pololu.com/file/0J1087/LSM6DS33.pdf) and [magnetometer](https://www.pololu.com/file/0J1089/LIS3MDL.pdf).
Only the raw sensor readings were saved in addition to the configuration and calibration data necessary to reconstruct the flight afterwards.

The .csv files for each sensor contain the timestamps and readings since the arming of the rocket up until landing/crashing. Additionally, the .log file contains the current state of the statemachine with timestamp, as well as some debug logs showing the values of pressure, altitude and vertical velocity which are calculated on the fly but not saved.

### Notes

- The data files ended with null bytes because the flight computer did not shutdown cleanly and might have been writing to the file at that moment (hard impact on the ground). I have removed these from these copies of the data files to make it possible to post-process them.
- For a yet unknown reason the .log file ended before apogee while the data files only end 
