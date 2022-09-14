# -*- coding: utf-8 -*-
"""
Convert files with uniform grid to netcdf4
@author: rringuet, 2022

Date:  2020-05-05 00:00
Model: TS18
Bin:   Esw    1.1 mV/m, Bang   178 deg., tilt  13.1 deg.
Grid:  Uniform (lat_step: 1.00, lon_step: 2.00 [deg])

MLAT [deg]   MLT [hr]   Pot [kV] Vazm [deg] Vmag [m/s]
---------- ---------- ---------- ---------- ----------

"""
from glob import glob
import numpy as np
from time import perf_counter
from datetime import datetime, timezone
#from astropy.constants import R_earth
from netCDF4 import Dataset
import re
import os.path

model_varnames={"Pot": ['V', 'kV'], "Vazm": ['theta_v', 'deg'],
                "Vmag": ['v', 'm/s'],
                # remaining variables are time series
                "tilt": ['theta_Btilt', "deg"], 'Esw': ['E_sw', 'mV/m'],
                'Bang': ['theta_B', 'deg'],
                # these are the coordinate variables
                'MLAT': ['MLAT', 'deg'], 'MLT': ['MLT', 'hr']}


def dts_to_hrs(datetime_string, filedate):
    '''Get hours since midnight from datetime string'''
    return (datetime.strptime(datetime_string,
                              '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc) -
            filedate).total_seconds()/3600.


def grid_type(filename):
    '''Determine grid type of data file.
    True if uniform, False if equal-area.'''

    read_obj = open(filename, 'r')
    line = read_obj.readline().strip()  # Date:  2020-05-05 00:00
    line = read_obj.readline().strip()  # Model: TS18
    # Bin:   Esw    1.1 mV/m, Bang   178 deg., tilt  13.1 deg.
    line = read_obj.readline().strip()
    # Grid:  Uniform (lat_step: 1.00, lon_step: 2.00 [deg])
    line = read_obj.readline().strip()
    read_obj.close()
    return 'Uniform' in line


# 'C:/Users/rringuet/Kamodo_WinDev1/SuperDARN/fullday/model20200505-0000.txt'
def ascii_reader(filename):
    '''Loads the data from a superdarn txt file into a nested dict. All data
    arrays are returned as 1D arrays.'''

    # open file
    read_obj = open(filename, 'r')
    # extract header
    # Date:  2020-05-05 00:00
    date_string = read_obj.readline().strip()
    # Model: TS18
    model_string = read_obj.readline().strip()
    # Bin:   Esw    1.1 mV/m, Bang   178 deg., tilt  13.1 deg.
    bin_string = read_obj.readline().strip()
    # Grid:  Uniform (lat_step: 1.00, lon_step: 2.00 [deg])
    grid_string = read_obj.readline().strip()
    # empty line
    trash = read_obj.readline().strip()
    # MLAT [deg]   MLT [hr]   Pot [kV] Vazm [deg] Vmag [m/s]
    variable_keys = read_obj.readline().strip()
    # line with only dashes
    trash = read_obj.readline().strip()

    # extract info from header strings
    # '2020-05-05 00:00' = date_string[2]+' '+date_string[3]
    time_str = date_string[6:].strip()
    filedate = datetime.strptime(time_str[:10],
                                 '%Y-%m-%d').replace(tzinfo=timezone.utc)
    hrs = dts_to_hrs(time_str, filedate)
    bin_list = bin_string[4:].split(',')
    Esw = float(bin_list[0].strip()[3:].strip().split(' ')[0])
    Bang = float(bin_list[1].strip()[4:].strip().split(' ')[0])
    tilt = float(bin_list[2].strip()[4:].strip().split(' ')[0])
    var_list = re.split(' +',variable_keys)
    header_keys = ['tilt', 'Esw', 'Bang']
    variable_keys = [item for item in var_list if '[' not in item]

    # create dictionary to store data in
    variables = {model_varnames[var][0]: {'units': model_varnames[var][-1],
                                          'data': []} for var in
                 variable_keys + header_keys}

    # store time series values
    variables[model_varnames['tilt'][0]]['data'] = tilt
    variables[model_varnames['Esw'][0]]['data'] = Esw
    variables[model_varnames['Bang'][0]]['data'] = Bang
    variables['time'] = {'units': 'hr', 'data': hrs}

    # store array data into dictionary
    for line in read_obj:
        vals = re.split(' +', line.strip())
        for i in range(len(variable_keys)):  # skip empty block(s) at the end
            variables[model_varnames[variable_keys[i]][0]]['data'].append(
                vals[i])
    read_obj.close()

    # convert to numpy float arrays
    for key in variables.keys():
        if isinstance(variables[key]['data'], (list)):
            variables[key]['data'] = np.array(variables[key]['data'],
                                              dtype=float)

    # add metadata
    variables['metadata'] = {'grid': grid_string[0][5:].strip(),
                             'model': model_string[0][6:].strip(),
                             'filedate': time_str[:10]}
    return variables


def df_data(df_files):
    '''Read in data from one hemisphere and perform latitude wrapping only.
    Logic for default grid files.'''

    # get data from first file, set lat/lon arrays
    file_data = ascii_reader(df_files[0])
    lat = np.unique(file_data['MLAT']['data'])
    diff = min(abs(np.diff(lat)))
    if min(lat) > 0:
          # N hemisphere data
        lat = np.append(lat, 90.)
        lat = np.insert(lat, 0, [min(lat)-diff, min(lat)-diff/10.])
        # add a spot for a copy before a new NaN row
    else:
        lat = np.insert(lat, 0, -90.)
        lat = np.append(lat, [max(lat)+diff/10., max(lat)+diff])
        # add a spot for a copy before a new NaN row
    lon = np.unique(file_data['MLT']['data']) * 15.
    # The interpolator later assigned makes the last numerical row also NaN,
    # so adding a buffer row with a slightly different coordinate.

    # set up net variables dictionary and time coordinate lists
    time = [file_data['time']['data']]
    coords = {'time': time, 'lon': lon, 'lat': lat}
    var1D_list = ['theta_Btilt', 'E_sw', 'theta_B']
    var3D_list = ['V', 'theta_v', 'v']
    variables = {var: [np.reshape(file_data[var]['data'],
                                  (lat.size-3, lon.size)).T]
                 for var in var3D_list}  # reshape into lon/lat array
    for var in var1D_list:
        variables[var] = [file_data[var]['data']]

    # loop through files and add data to variables dict
    for file in df_files[1:]:
        data = ascii_reader(file)
        time.append(data['time']['data'])
        for var in var1D_list:
            variables[var].append(data[var]['data'])
        for var in var3D_list:
            variables[var].append(np.reshape(data[var]['data'],
                                             (lat.size-3, lon.size)).T)
    for var in var1D_list+var3D_list:
        variables[var] = np.array(variables[var])

    # perform lat wrapping in variable data
    for var in var3D_list:
        # perform scalar averaging for pole values (latitude wrapping)
        # addind NaN on equator-side assuming the data never reaches it.
        data_shape = variables[var].shape
        total_shape = (data_shape[0], data_shape[1], data_shape[2]+3)
        tmp = np.zeros(total_shape, dtype=float)
        if min(lat) > 0:  # north pole at end of array
            tmp[:, :, 2:-1] = variables[var]  # copy data into grid
            top = np.mean(tmp[:, :, -2], axis=1)  # same shape as time axis
            tmp[:, :, -1] = np.broadcast_to(top,
                                            (total_shape[1], total_shape[0])).T
            tmp[:, :, 1] = variables[var][:, :, 0]
            tmp[:, :, 0] = np.NaN  # add NaNs on equator side
        else:  # south pole at beginning of array
            tmp[:, :, 1:-2] = variables[var]  # copy data into grid
            top = np.mean(tmp[:, :, 1], axis=1)  # same shape as time axis
            tmp[:, :, 0] = np.broadcast_to(top,
                                           (total_shape[1], total_shape[0])).T
            tmp[:, :, -2] = variables[var][:, :, 0]
            tmp[:, :, -1] = np.NaN  # add NaNs on equator side
        variables[var] = tmp
    
    # hemisphere spcific data wrangling complete. return data.
    return variables, coords, var3D_list, var1D_list


def _toCDF(files, file_prefix):
    '''Reads in data from all files, writes to a netcdf4 file. Used for uniform
    grid data files for faster data access.'''

    # Get data from both hemispheres
    files_N = [file for file in files if file[-8:] == '_Ndf.txt']
    if len(files_N) > 0:
        variables_N, coords_N, var3D_list, var1D_list = df_data(files_N)
    else:
        print('No files found for the northern hemisphere.')
    files_S = [file for file in files if file[-8:] == '_Sdf.txt']
    if len(files_S) > 0:
        variables_S, coords_S, var3D_list, var1D_list = df_data(files_S)
    else:
        print('No files found for the southern hemisphere.')
    if len(files_N) > 0 and len(files_S) > 0 and len(files_N) != len(files_S):
        print('The number of files for the northern and southern hemispheres' +
              ' are not equal. Please add the missing files and try again.')
        return False

    # Combine coordinate arrays, assuming time and lon the same
    if len(files_N) > 0:
        coords = coords_N
        variables = {var: variables_N[var] for var in var1D_list}
    else:
        coords = coords_S
        variables = {var: variables_S[var] for var in var1D_list}
    # Combine data and lat arrays or pick based on availability
    if len(files_N) > 0 and len(files_S) > 0:
        coords['lat'] = np.append(coords_S['lat'], coords_N['lat'])
        new_shape = [len(coords['time']), len(coords['lon']),
                     len(coords['lat'])]
        for var in var3D_list:  # south pole at beginning of array
            tmp = np.zeros(new_shape)  # north pole at end of array
            tmp[:, :, :len(coords_S['lat'])] = variables_S[var]
            tmp[:, :, len(coords_S['lat']):] = variables_N[var]
            variables[var] = tmp
    else:  # only data for one hemisphere was found, copy over data
        if len(files_N) > 0:
            for var in var3D_list:
                variables[var] = variables_N[var]
        else:
            for var in var3D_list:
                variables[var] = variables_S[var]        

    # perform longitude wrapping in coordinate grid
    lon = coords['lon']
    lon_le180 = np.where(lon <= 180)[0]
    lon_ge180 = np.where(lon >= 180)[0]  # repeat 180 for -180 values
    # add a cushion value for proper interpolation range (-180 to 180)
    if not 180. in lon:
        lon_le180 = np.append(lon_le180, lon_le180.max()+1)
        lon_ge180 = np.insert(lon_ge180, 0, lon_ge180.min()-1)
    lon_size = len(lon_le180) + len(lon_ge180)
    tmp = np.zeros(lon_size)
    tmp[:len(lon_ge180)] = lon[lon_ge180] - 360.
    tmp[len(lon_ge180):] = lon[lon_le180]
    coords['lon'] = tmp
    new_shape = [len(coords['time']), len(coords['lon']), len(coords['lat'])]

    # perform lon wrapping in variable data
    for var in var3D_list:
        # swap longitudes, repeat 180 values for -180 position
        tmp = np.zeros(new_shape, dtype=float)
        tmp[:, :len(lon_ge180), :] = variables[var][:, lon_ge180, :]
        tmp[:, len(lon_ge180):, :] = variables[var][:, lon_le180, :]
        variables[var] = tmp

    # Data wrangling complete. Start new output file
    cdf_filename = file_prefix+'_df.nc'
    data_out = Dataset(cdf_filename, 'w', format='NETCDF4')
    data_out.file = ''.join([f+',' for f in files]).strip(',')
    data_out.model = 'SuperDARN'
    data_out.filedate = os.path.basename(files[0])[5:].split('-')[0]
    data_out.grid = 'Default grid'

    # establish coordinates (lon, lat, then time open)
    # lon: create dimension and variable
    new_dim = data_out.createDimension('lon', coords['lon'].size)
    new_var = data_out.createVariable('lon', np.float32, 'lon')
    new_var[:] = coords['lon']  # store data for dimension in variable
    new_var.units = 'deg'
    # lat: create dimension and variable
    new_dim = data_out.createDimension('lat', coords['lat'].size)
    new_var = data_out.createVariable('lat', np.float32, 'lat')
    new_var[:] = coords['lat']  # store data for dimension in variable
    new_var.units = 'deg'
    # time: create dimension and variable
    new_dim = data_out.createDimension('time', len(files))  # create dimension
    new_var = data_out.createVariable('time', np.float32, 'time')  # variable
    new_var[:] = coords['time']
    new_var.units = 'hr'

    # copy over variables to file
    for variable_name in variables.keys():
        if variable_name in var3D_list:
            new_var = data_out.createVariable(variable_name, np.float32,
                                              ('time', 'lon', 'lat'))
            new_data = variables[variable_name]
        elif variable_name in var1D_list:
            new_var = data_out.createVariable(variable_name, np.float32,
                                              ('time'))
            new_data = variables[variable_name]
        else:
            continue
        new_var[:] = new_data  # store data in variable
        units = [value[-1] for key, value in model_varnames.items()
                 if value[0] == variable_name][0]
        new_var.units = units

    # close file
    data_out.close()
    return cdf_filename


def ea_data(ea_files):
    '''Read in data from one hemisphere and perform latitude wrapping only.
    Logic for equal area grid files.'''

    # get data from first file
    file_data = ascii_reader(ea_files[0])
    lat = np.unique(file_data['MLAT']['data'])
    print(ea_files[0], lat)

    # Longitude array is different for each latitude value. Storing in dict
    lon = {}
    for lat_val in lat:
        idx = np.where(file_data['MLAT']['data'] == lat_val)[0]
        lon[lat_val] = np.array(file_data['MLT']['data'][idx]) * 15.

    # set up net variables dictionary and time coordinate lists
    time = [file_data['time']['data']]
    var1D_list = ['theta_Btilt', 'E_sw', 'theta_B']
    var3D_list = ['V', 'theta_v', 'v']
    variables = {var: [file_data[var]['data']] for var in var1D_list}
    for var in var3D_list:
        variables[var] = {}
        for lat_val in lat:
            idx = np.where(file_data['MLAT']['data'] == lat_val)[0]
            variables[var][lat_val] = [file_data[var]['data'][idx].T]

    # loop through files and add data to variables dict
    for file in ea_files[1:]:
        data = ascii_reader(file)
        time.append(data['time']['data'])
        for var in var1D_list:
            variables[var].append(data[var]['data'])
        for var in var3D_list:
            for lat_val in lat:
                idx = np.where(data['MLAT']['data'] == lat_val)[0]
                variables[var][lat_val].append(data[var]['data'][idx].T)

    # convert to arrays and store
    for var in var3D_list:
        for lat_val in lat:
            variables[var][lat_val] = np.array(variables[var][lat_val])
            #print(var, lat_val, variables[var][lat_val].shape)  # should be (time, lon)
    for var in var1D_list:
        variables[var] = np.array(variables[var])
    coords = {'time': np.array(time), 'lon': lon, 'lat': lat}

    # The interpolator later assigned makes the last numerical row also NaN,
    # so adding a buffer row with a slightly different latitude value.
    # Also adding a spot for the averaging at the pole.
    diff = min(abs(np.diff(lat)))
    if min(lat) > 0:
        # N hemisphere data
        lat_equator, lat_pole = lat[0], lat[-1]
        lat = np.append(lat, 90.)
        new_vals = [min(lat)-diff, min(lat)-diff/10.]
        lat = np.insert(lat, 0, new_vals)
        # added a spot for a copy before a new NaN row
        new_vals.append(90)
    else:
        lat_equator, lat_pole = lat[-1], lat[0]
        lat = np.insert(lat, 0, -90.)
        new_vals = [max(lat)+diff/10., max(lat)+diff]
        lat = np.append(lat, new_vals)
        new_vals.reverse()  # want diff/10 value second in list
        # added a spot for a copy before a new NaN row
        new_vals.append(-90)
    coords['lat'] = lat  # update lat values in dictionary

    # adding coordinates to lon dictionary for new latitude values
    lon[new_vals[0]] = lon[lat_equator]  # same grid as equator-most lat value
    lon[new_vals[1]] = lon[lat_equator]  # for two buffer rows
    lon[new_vals[2]] = np.array([-180., 0., 180.])  # range for interpolations
    coords['lon'] = lon  # update lon values in dictionary

    # perform lat wrapping in variable data
    for var in var3D_list:
        # perform scalar averaging for pole values (latitude wrapping)
        top = np.mean(variables[var][lat_pole], axis=1)  # same shape as time
        variables[var][new_vals[2]] = np.broadcast_to(top, (3, len(time))).T
        
        # addind NaN on equator-side assuming the data never reaches it.
        variables[var][new_vals[1]] = variables[var][lat_equator]  # buffer row
        variables[var][new_vals[0]] = np.NaN * \
            np.ones(shape=variables[var][lat_equator].shape)
        
    # hemisphere spcific data wrangling complete. return data.
    return variables, coords, var3D_list, var1D_list


def _toCDFGroup(files, file_prefix):
    '''Reads in data from all files, writes to h5 files. Used for equal-area
    data files so that lon grids from different lat vals can be stored in
    groups.'''

    # Get data from both hemispheres
    files_N = [file for file in files if file[-8:] == '_Nea.txt']
    if len(files_N) > 0:
        variables_N, coords_N, var3D_list, var1D_list = ea_data(files_N)
    else:
        print('No files found for the northern hemisphere.')
    files_S = [file for file in files if file[-8:] == '_Sea.txt']
    if len(files_S) > 0:
        variables_S, coords_S, var3D_list, var1D_list = ea_data(files_S)
    else:
        print('No files found for the southern hemisphere.')
    if len(files_N) > 0 and len(files_S) > 0 and len(files_N) != len(files_S):
        print('The number of files for the northern and southern hemispheres' +
              ' are not equal. Please add the missing files and try again.')
        return False

    # Combine coordinate arrays, assuming times are the same
    if len(files_N) > 0:
        coords = coords_N
        variables = {var: variables_N[var] for var in var1D_list}
    else:
        coords = coords_S
        variables = {var: variables_S[var] for var in var1D_list}
    # Combine data and lat/lon arrays or pick based on availability
    if len(files_N) > 0 and len(files_S) > 0:
        coords['lat'] = np.append(coords_S['lat'], coords_N['lat'])
        coords['lon'] = coords_N['lon']  # nested dictionary with keys=lat_vals
        for lat_val in coords_S['lat']:
            coords['lon'][lat_val] = coords_S['lon'][lat_val]
        for var in var3D_list:  # south pole at beginning of array
            variables[var] = variables_N[var]
            for lat_val in coords_S['lat']:
                variables[var][lat_val] = variables_S[var][lat_val]
    else:  # only data for one hemisphere was found, copy over data
        if len(files_N) > 0:
            for var in var3D_list:
                variables[var] = variables_N[var]
        else:
            for var in var3D_list:
                variables[var] = variables_S[var]

    # perform longitude wrapping in coordinate grid and variable data
    for lat_val in coords['lat'][1:-1]:  # skip poles because already correct
        # Deal with lat_val specific coordinate grid first
        lon = coords['lon'][lat_val]
        lon_le180 = np.where(lon <= 180)[0]
        lon_ge180 = np.where(lon >= 180)[0]  # repeat 180 for -180 values
        # add a cushion value for proper interpolation range (-180 to 180)
        if not 180. in lon:
            lon_le180 = np.append(lon_le180, lon_le180.max()+1)
            lon_ge180 = np.insert(lon_ge180, 0, lon_ge180.min()-1)
        lon_size = len(lon_le180) + len(lon_ge180)
        tmp = np.zeros(lon_size)
        tmp[:len(lon_ge180)] = lon[lon_ge180] - 360.
        tmp[len(lon_ge180):] = lon[lon_le180]
        coords['lon'][lat_val] = tmp
        new_shape = (len(coords['time']), len(coords['lon'][lat_val]))
    
        # perform lon wrapping in variable data
        for var in var3D_list:
            # swap longitudes, repeat 180 values for -180 position
            tmp = np.zeros(new_shape, dtype=float)
            tmp[:, :len(lon_ge180)] = variables[var][lat_val][:, lon_ge180]
            tmp[:, len(lon_ge180):] = variables[var][lat_val][:, lon_le180]
            variables[var][lat_val] = tmp

    # Data wrangling complete. Start new output file
    cdf_filename = file_prefix+'_ea.nc'
    data_out = Dataset(cdf_filename, 'w', format='NETCDF4')
    data_out.file = ''.join([f+',' for f in files]).strip(',')
    data_out.model = 'SuperDARN'
    data_out.filedate = os.path.basename(files[0])[5:].split('-')[0]
    data_out.grid = 'Equal area grid'

    # establish coordinates (lat, then time open)
    # lat: create dimension and variable
    new_dim = data_out.createDimension('lat', coords['lat'].size)
    new_var = data_out.createVariable('lat', np.float32, 'lat')
    new_var[:] = coords['lat']  # store data for dimension in variable
    new_var.units = 'deg'
    # time: create dimension and variable
    new_dim = data_out.createDimension('time', coords['time'].size)  # create dimension
    new_var = data_out.createVariable('time', np.float32, 'time')  # variable
    new_var[:] = coords['time']
    new_var.units = 'hr'

    # copy over 1D variables to file
    for variable_name in var1D_list:
        new_var = data_out.createVariable(variable_name, np.float32,
                                          ('time'))
        new_data = variables[variable_name]
        new_var[:] = new_data  # store data in variable
        units = [value[-1] for key, value in model_varnames.items()
                 if value[0] == variable_name][0]
        new_var.units = units

    # Group lon and 3D data by lat values
    for lat_val in coords['lat']:
        if lat_val < 0:
            lat_name = str(lat_val).replace('.', '_').replace('-', 'n')
        else:
            lat_name = 'p'+str(lat_val).replace('.', '_')
        new_group = data_out.createGroup(lat_name)
        # lon: create dimension and variable
        new_dim = new_group.createDimension('lon', coords['lon'][lat_val].size)
        new_var = new_group.createVariable('lon', np.float32, 'lon')
        new_var[:] = coords['lon'][lat_val]  # store data for dimension in variable
        new_var.units = 'deg'
        # time: create dimension and variable
        #new_dim = new_group.createDimension('time', coords['time'].size)  # create dimension
        #new_var = new_group.createVariable('time', np.float32, 'time')  # variable
        #new_var[:] = coords['time']
        #new_var.units = 'hr'

        # copy over 3D variables to file
        for variable_name in var3D_list:
            new_var = new_group.createVariable(variable_name, np.float32,
                                              ('time', 'lon'))
            new_data = variables[variable_name][lat_val]
            new_var[:] = new_data  # store data in variable
            units = [value[-1] for key, value in model_varnames.items()
                     if value[0] == variable_name][0]
            new_var.units = units

    # close file
    data_out.close()
    return cdf_filename 


def convert_files(file_prefix):
    '''Convert files of given pattern into one netCDF4 or h5 file'''
    
    print('Converted data file not found. Converting files with ' +
          f'{file_prefix} prefix to a netCDF4 file.', end="")
    ftic = perf_counter()
    files = sorted(glob(file_prefix+'*.txt'))
    if grid_type(files[0]):  # If grid is uniform, write to netCDF4
        print(' Uniform grid detected. ', end="")
        out_file = _toCDF(files, file_prefix)
    else:  # if grid is equal-area, write to a grouped netCDF4
        print(' Equal-area grid detected. ', end="")
        out_file = _toCDFGroup(files, file_prefix)
    print(out_file)
    print(f'{len(files)} files with prefix {file_prefix} now combined into ' +
          f'{out_file} in {perf_counter()-ftic:.6f}s.')
    return True