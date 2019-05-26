# imports
import time
import sys
import os
import csv
import json
import math
import datetime
import statistics
import re
from matplotlib import pyplot as plt

states = ['ERROR', 'SYSTEMS_CHECK', 'IDLE', 'ARMED', 'LAUNCHED', 'DEPLOYED', 'LANDED']
fullscreen = 1

#####################################
# function and class definitions

### functions for file handling/getting the data in
def read_data(local_path):
    with open(local_path, 'r') as f:
        str_data = list(csv.reader(f))
    data = []
    for dd in str_data:
        dat = []
        if not dd[0].startswith('#'):
            for d in dd:
                try:
                    dat.append(float(d))
                except ValueError:
                    dat.append([float(e) for e in d[1:-1].split(', ')])  # to catch str(list)
            data.append(dat)
    return data

def read_config(config_path):
    with open(config_path) as config_file:
        globals().update(json.load(config_file))

def read_log(log_path):
    with open(log_path) as log_file:
        log = log_file.read()
    globals().update({'p0':float([line for line in log.split('\n') if line.find('p0=')!=-1][0].split('p0=')[-1])})
    return log

### functions for analysing data/postprocessing it
def calculate_odr(data, deduplicate=False):
    '''Prints the average output data rate for a given dataset,
    where timestamp is data[i][1] and the readout is data[i][2].
    Make sure to use on the data set of one sensor at a time only,
    as otherwise it will find the frequency of the smallest common multiple of both frequencies'''
    deduplicated = [d for i,d in enumerate(data[1:]) if not deduplicate or (d[2] != data[i][2])]
    delta = [d[1]-deduplicated[i][1] for i,d in enumerate(deduplicated[1:])]
    avg_delta = sum(delta)/len(delta)
    avg_odr = 1/avg_delta
    print('current output data rate:', avg_odr, 'Hz')
    stdev = statistics.stdev(delta)
    stdev_odr = abs(avg_odr-1/(stdev+avg_delta))
    print('standard deviation odr:', stdev_odr, 'Hz')
    return avg_odr, stdev_odr

def calculate_alt_vv(baro_data):
    pressure_raw = [b[2]/40.96 for b in baro_data]
    pressure_smoothed = [pressure_raw[0]]
    for i, p in enumerate(pressure_raw[1:]):
        pressure_smoothed.append(exp_factor_p*p+(1-exp_factor_p)*pressure_smoothed[i])
    altitude = [T0/a*((p/p0)**(-(R*a)/g0)-1) for p in pressure_smoothed]
    vertical_velocity = [0]+[(alt-altitude[i])/intervals['baro'] for i, alt in enumerate(altitude[1:])]  # conversion from h to vv
    vertical_velocity_smoothed = [vertical_velocity[0]]
    for i, vv in enumerate(vertical_velocity[1:]):
        vertical_velocity_smoothed.append(exp_factor_vv*vv + (1-exp_factor_vv)*vertical_velocity_smoothed[i])
    return roundall(pressure_raw), roundall(pressure_smoothed), roundall(altitude), roundall(vertical_velocity), roundall(vertical_velocity_smoothed)

def calculate_acc_g(acc_data):
    acc_raw = [[aa*0.122/1000 for aa in a[2]] for a in acc_data]  # conversion from LSB to g's
    return acc_raw

def calculate_gyro_dps(gyro_data):
    gyro_raw = [[gg*35/1000 for gg in g[2]] for g in gyro_data]  # conversion from LSB to dps
    return gyro_raw

def calculate_mag_gaus(mag_data):
    mag_raw = [[mm/6842 for mm in m[2]] for m in mag_data]  # conversion from LSB to gauss
    return mag_raw

def calculate_heading(mag):
    launchtime = get_state_transitions(log)[3][0]
    zero_samples = [m[2] for m in mag if m[1]<launchtime-2]
    in_flight_mag = [m[2]for m in mag if m[1]>launchtime]
    in_flight_times = [m[1] for m in mag if m[1]>launchtime]
    heading_0 = math.atan(sum([s[0]/s[1] for s in zero_samples])/len(zero_samples))*180/math.pi
    rel_headings = [math.atan(m[0]/m[1])*180/math.pi-heading_0 for m in in_flight_mag]
    angular_rates = [0]+[(h-rel_headings[i])/(in_flight_times[i+1]-in_flight_times[i]) for i,h in enumerate(rel_headings[1:])]
    return rel_headings, heading_0, angular_rates

def get_state_transitions(log):
    statelines = []
    found_states = []
    loglines = log.splitlines()
    for state in states:
        for line in loglines:
            for word in line.split(' '):
                if word == state:
                    statelines.append(line)
                    found_states.append(state)
                    break
            if state in found_states:
                break
    state_transitions = [[datetime.datetime.strptime(' '.join(line.split(' ')[:2]), '%Y-%m-%d %H:%M:%S,%f').timestamp(), line.split(' ')[-1]] for line in statelines]
    state_transitions += [[state_transitions[3][0]+14, 'SRP board min deploy time'], [state_transitions[3][0]+16.5, 'SRP board max deploy time']]
    return state_transitions

def roundall(ls, digits=3):
    return [round(l, digits) for l in ls]

def plot(timestamps, data, plotter=plt):
    x = timestamps
    y = data
    if type(y[0])==type([]):
        for axi in range(len(y[0])):
            vals = [entry[axi] for entry in y]
            plotter.plot(x, vals)
    else:
        plotter.plot(x, y)

def plot_states(state_transitions, plotter=plt):
    for i, state in enumerate(state_transitions):
        plotter.axvline(state[0], color='r')
        limits = plotter.get_ylim()
        center = sum(limits)/2 + (i%2-0.5)*abs(limits[0]-limits[1])/4
        plotter.text(state[0], center, state[1], rotation=90)

#####################################
# setup

sensors = {'baro':[], 'acc':[], 'gyro':[], 'mag':[]}
data_dir = '../flown_software_cleaned_up/data/'
plt.ioff()

#####################################
# main

if __name__ == '__main__':
    while True:
        try:
            datafilename = sys.argv[1]
        except IndexError:
            # get all log timestamps only once (maybe later filter for only those with data files)
            choices = sorted({re.match(r'(\d+-\d+-\d+_\d+-\d+-\d+).+', date)[1] for date in os.listdir(data_dir)})
            print(choices)
            datafilename = input('Which files? ')
            if not datafilename:
                # datafilename = '13-05-19_18-32-06'
                datafilename = choices[-1]
        if datafilename in ('q', 'quit', 'stop', 'x', 'exit'):
            break
        for n in sensors:
            datafilename = datafilename.strip('_'+n)+'_'
        read_config(data_dir+datafilename+'config.json')
        log = read_log(data_dir+datafilename[:-1]+'.log')
        ## plot raw sensor readings
        launchtime = get_state_transitions(log)[3][0]
        n_plots = len(sensors)
        n_rows = int(math.sqrt(n_plots))
        n_cols = math.ceil(n_plots/n_rows)
        fig, axs = plt.subplots(n_rows, n_cols)
        for i, name in enumerate(sensors):
            sensors[name] = read_data(data_dir+datafilename+name+'.csv')
            ax = axs[i//n_cols, i%n_cols]
            ax.set_title(name)
            plot([d[1] for d in sensors[name]], [d[2] for d in sensors[name]], plotter=ax)
            plot_states(get_state_transitions(log), ax)
        if fullscreen:
            figManager = plt.get_current_fig_manager()
            figManager.window.showMaximized()
        else:
            fig.set_size_inches(2*fig.get_figwidth(), 2*fig.get_figheight())
        plt.show()
        ## plot pressure calculations
        p, ps, h, vv, vvs = calculate_alt_vv(sensors['baro'])
        times = [d[1] for d in sensors['baro']]
        baroplots = {'pressure': [[*d] for d in zip(p, ps)], 'altitude': h, 'vertical velocity': [[*d] for d in zip(vv, vvs)]}
        n_plots = len(baroplots)
        n_rows = int(math.sqrt(n_plots))
        n_cols = math.ceil(n_plots / n_rows)
        fig, axs = plt.subplots(n_rows, n_cols)
        for i, name in enumerate(baroplots):
            if n_rows==1:
                ax = axs[i]
            else:
                ax = axs[i // n_cols, i % n_cols]
            ax.set_title(name)
            plot(times, baroplots[name], plotter=ax)
            plot_states(get_state_transitions(log), ax)
        if fullscreen:
            figManager = plt.get_current_fig_manager()
            figManager.window.showMaximized()
        else:
            fig.set_size_inches(3 * fig.get_figwidth(), fig.get_figheight())
        plt.show()
        ## plot accelerations, angular rates and magnetic fields
        fig, axs = plt.subplots(2, 2)
        axs[0,0].plot([i[1] for i in sensors['acc']], calculate_acc_g(sensors['acc']))
        axs[0,1].plot([i[1] for i in sensors['gyro']], calculate_gyro_dps(sensors['gyro']))
        axs[1,0].plot([i[1] for i in sensors['mag']], calculate_mag_gaus(sensors['mag']))
        axs[1,1].plot([i[1] for i in sensors['mag'] if i[1]>launchtime], calculate_heading(sensors['mag'])[2])
        if fullscreen:
            figManager = plt.get_current_fig_manager()
            figManager.window.showMaximized()
        else:
            fig.set_size_inches(3 * fig.get_figwidth(), fig.get_figheight())
        plt.show()
