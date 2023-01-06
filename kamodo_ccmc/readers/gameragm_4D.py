# -*- coding: utf-8 -*-
"""
Created on Wed Jan  4 15:37:59 2023

@author: rringuet
"""
from numpy import vectorize
from datetime import datetime, timezone

model_varnames = {'Bx': ['B_x', 'Magnetic field (x component)',
                           0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nT'],
                  'By': ['B_y', 'Magnetic field (y component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nT'],
                  'Bz': ['B_z', 'Magnetic field (z component)',
                           0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nT'],
                  'Cs': ['c_s', 'sound speed of plasma', 0, 'SM', 'car',
                         ['time', 'X', 'Y', 'Z'], 'km/s'],
                  'D': ['N_plasma', 'Plasma number density (M/mp)', 0, 'SM', 'car',
                         ['time', 'X', 'Y', 'Z'], '1/cm**3'],  # always 'D'?
                  'Jx': ['J_x', 'current density (x component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nA/m**2'],
                  'Jy': ['J_y', 'current density (y component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nA/m**2'],
                  'Jz': ['J_z', 'current density (z component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'nA/m**2'],
                  'P': ['P', 'Pressure', 0, 'SM', 'car', 
                        ['time', 'X', 'Y', 'Z'], 'nPa'],
                  'Pb': ['P_M', 'Magnetic pressure', 0, 'SM', 'car', 
                          ['time', 'X', 'Y', 'Z'], 'nPa'],
                  'SrcD': ['N_src', 'number density of ???', 0, 'SM', 'car',
                           ['time', 'X', 'Y', 'Z'], '1/cm**3'],  # HIDE?
                  'SrcDT': ['t_src', 'time scale of ???', 0, 'SM', 'car',
                            ['time', 'X', 'Y', 'Z'], 's'],  # HIDE?
                  'SrcP': ['P_src', 'pressure of ???', 0, 'SM', 'car',
                           ['time', 'X', 'Y', 'Z'], 'nPa'],  # HIDE?
                  'SrcX1': ['theta_X1', 'scattering angle of ???, X-Y plane',
                            0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'deg'],  # HIDE?
                  'SrcX2': ['theta_X2', 'scattering angle of ???, X-Z plane', 
                            0, 'SM', 'car',['time', 'X', 'Y', 'Z'], 'deg'],  # HIDE?
                  'Vx': ['v_x', 'particle speed (x component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'km/s'],
                  'Vy': ['v_y', 'particle speed (y component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'km/s'],
                  'Vz': ['v_z', 'particle speed (z component)',
                          0, 'SM', 'car', ['time', 'X', 'Y', 'Z'], 'km/s'],
                  'Bx0': ['B_0x', 'Solar wind ??? Background magnetic field (x component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'By0': ['B_0y', 'Initial ??? Background magnetic field (y component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'Bz0': ['B_0z', '??? Background magnetic field (z component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'BxD': ['B_Dx', 'Dipole ??? Magnetic field (x component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'ByD': ['B_Dy', '??? Magnetic field (y component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'BzD': ['B_Dz', '??? Magnetic field (z component)',
                         0, 'SM', 'car', ['X', 'Y', 'Z'], 'nT'],
                  'dV': ['dV', 'Simulation cell volume', 0, 'SM', 'car',
                         ['X', 'Y', 'Z'], 'R_E**3']  # UNIT?
    }

constants = ['X', 'Y', 'Z', 'Bx0', 'By0', 'Bz0', 'BxD', 'ByD', 'BzD', 'dV']

@vectorize
def timestr_timestamp(time_str):
    '''Converts time string from data file into an UTC timestamp. Cuts off
    millisecond portion of times to prevent errors later.'''
    dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
    return dt.timestamp()


def MODEL():
    from kamodo import Kamodo
    from glob import glob
    import h5py
    from netCDF4 import Dataset
    from os.path import isfile, basename
    from astropy.time import Time
    from datetime import datetime, timezone
    from numpy import array, NaN, ndarray, zeros, linspace, repeat
    from time import perf_counter
    import kamodo_ccmc.readers.reader_utilities as RU
    import kamodo_ccmc.readers.gameragm_grids as G

    class MODEL(Kamodo):
        '''GAMERA GM model data reader.

        Inputs:
            file_dir: a string representing the file directory of the
                model output data.
                Note: This reader 'walks' the entire dataset in the directory.
            variables_requested = a list of variable name strings chosen from
                the model_varnames dictionary in this script, specifically the
                first item in the list associated with a given key.
                - If empty, the reader functionalizes all possible variables
                    (default)
                - If 'all', the reader returns the model_varnames dictionary
                    above for only the variables present in the given files.
            filetime = boolean (default = False)
                - If False, the script fully executes.
                - If True, the script only executes far enough to determine the
                    time values associated with the chosen data.
            printfiles = boolean (default = False)
                - If False, the filenames associated with the data retrieved
                    ARE NOT printed.
                - If True, the filenames associated with the data retrieved ARE
                    printed.
            gridded_int = boolean (default = True)
                - If True, the variables chosen are functionalized in both the
                    standard method and a gridded method.
                - If False, the variables chosen are functionalized in only the
                    standard method.
            verbose = boolean (False)
                - If False, script execution and the underlying Kamodo
                    execution is quiet except for specified messages.
                - If True, be prepared for a plethora of messages.
        All inputs are described in further detail in
            KamodoOnboardingInstructions.pdf.

        Returns: a kamodo object (see Kamodo core documentation) containing all
            requested variables in functionalized form.
        '''
        def __init__(self, file_dir, variables_requested=[],
                     printfiles=False, filetime=False, gridded_int=True,
                     verbose=False, **kwargs):
            super(MODEL, self).__init__(**kwargs)
            self.modelname = 'GAMERA_GM'
            t0 = perf_counter()

            # first, check for file list, create if DNE
            list_file = file_dir + self.modelname + '_list.txt'
            time_file = file_dir + self.modelname + '_times.txt'
            self.times, self.pattern_files = {}, {}
            if not isfile(list_file) or not isfile(time_file):
                # collect filenames
                files = sorted(glob(file_dir+'*.h5'))
                data_files = [f for f in files if 'Res' not in f]
                self.filename = ''.join([f+',' for f in data_files])[:-1]
                # one pattern per run: abcd_00nx_00ny_00nz
                # abcd part might not always be four characters
                p = ''.join([b+'_' for b in basename(
                    data_files[0]).split('.')[0].split('_')[:-3]])[:-1]

                # establish time attributes
                # get list of files to loop through later
                self.pattern_files[p] = data_files
                self.times[p] = {'start': [], 'end': [], 'all': []}

                # all times are in each file, so just use first file
                h5_data = h5py.File(data_files[0])
                timestep_keys = [key for key in h5_data.keys()
                                 if 'Step' in key]
                mjd_list = [h5_data[key].attrs['MJD'] for key in
                            timestep_keys]
                h5_data.close()

                # convert from modified julian date to UTC time
                # output format is 'YYYY-MM-DD HH:MM:SS.mms
                t = sorted(Time(mjd_list, format='mjd').iso)
                self.filedate = datetime.fromisoformat(t[0][:10]).replace(
                    tzinfo=timezone.utc)  # date only
                # convert to hrs since midnight
                utc_ts = timestr_timestamp(t)
                hrs = (utc_ts - self.filedate.timestamp()) / 3600.
                # store in self.times dictionary
                self.times[p]['start'] = repeat([hrs[0]], len(data_files))
                self.times[p]['end'] = repeat([hrs[-1]], len(data_files))
                self.times[p]['all'] = array(hrs)

                # need to figure out if millisecond accuracy is needed
                test = (len(utc_ts) - 1)/(utc_ts[-1] - utc_ts[0])  # #steps/s
                if test >= 1.5:  # need ms timing if >= 1.5 timesteps/second
                    ms_timing = True
                else:
                    ms_timing = False

                # If the cell centers need to be calculated, then this is
                # where that should be done.
                if not isfile(file_dir + 'gridcenters.nc'):  # REMOVE WHEN DONE TESTING
                    print('Computing grid cell centers...', end="")  # ****************************
                    self._Xc, self._Yc, self._Zc = G.ComputeCellCenters(data_files)
                    print('done.')

                # create time list file if DNE
                RU.create_timelist(list_file, time_file, self.modelname,
                                   self.times, self.pattern_files,
                                   self.filedate, ms_timing=ms_timing)
            else:  # read in data and time grids from file list
                self.times, self.pattern_files, self.filedate, self.filename =\
                    RU.read_timelist(time_file, list_file)
            if filetime:
                return  # return times only

            # perform initial check on variables_requested list
            if len(variables_requested) > 0 and variables_requested != 'all':
                test_list = [value[0] for key, value in model_varnames.items()]
                err_list = [item for item in variables_requested if item
                            not in test_list]
                if len(err_list) > 0:
                    print('Variable name(s) not recognized:', err_list)
                for item in err_list:
                    variables_requested.remove(item)
                if len(variables_requested) == 0:
                    return

            # collect variable list (in attributes of datasets)
            p = list(self.pattern_files.keys())[0]  # only one pattern
            h5_data = h5py.File(self.pattern_files[p][0])
            key_list = [key for key in h5_data.keys() if 'Step' not in key and
                        key not in ['X', 'Y', 'Z']]  # skip coordinates
            key_list.extend(list(h5_data['Step#0'].keys()))
            h5_data.close()

            if len(variables_requested) > 0 and variables_requested != 'all':
                gvar_list = [key for key, value in model_varnames.items()
                             if value[0] in variables_requested and
                             key in key_list]  # file variable names
            
                # check for variables requested but not available
                if len(gvar_list) != len(variables_requested):
                    err_list = [value[0] for key, value in
                                model_varnames.items() if value[0] in
                                variables_requested and key not in gvar_list]
                    if len(err_list) > 0:
                        print('Some requested variables are not available:',
                              err_list)
            else:  # only input variables on the avoid_list if requested
                gvar_list = [key for key in key_list if key in
                             model_varnames.keys()]
                # return list of variables included in data files
                if variables_requested == 'all':
                    self.var_dict = {value[0]: value[1:] for key, value in
                                     model_varnames.items()
                                     if key in gvar_list}
                    return
            
            # initialize data mapping for each variable desired
            self.variables = {model_varnames[var][0]:
                              {'units': model_varnames[var][-1],
                               'data': p} for var in gvar_list}

            # read in coordinate grid for cell-centers (is this needed?)*********************
            if not hasattr(self, '_Xc'):
                center_file = file_dir + 'gridcenters.nc'
                center_data = Dataset(center_file)
                self._Xc = array(center_data['X_center'])
                self._Yc = array(center_data['Y_center'])
                self._Zc = array(center_data['Z_center'])
                center_data.close()
            self._X = linspace(self._Xc.min(), self._Xc.max(),
                               endpoint=True, num=self._Xc.shape[0])
            self._Y = linspace(self._Yc.min(), self._Yc.max(),
                               endpoint=True, num=self._Yc.shape[1])
            self._Z = linspace(self._Zc.min(), self._Zc.max(),
                               endpoint=True, num=self._Zc.shape[2])

            # IF data needs to be assembled, create the index mapping here ****************
            # once per variable type (constant vs variable) instead of once per
            # variable to save on execution time
            if len(self.pattern_files[p]) > 1:
                const_variables = [var for var in gvar_list if var in
                                   constants]
                time_variables = [var for var in gvar_list if var not in
                                   constants]
                if len(const_variables) > 0:
                    self.constant_map = G.GridMapping(
                        self.pattern_files[p], True, const_variables[0])
                    print('Index map created for constants.')
                if len(time_variables) > 0:
                    self.variable_map = G.GridMapping(self.pattern_files[p],
                                                      False, time_variables[0])
                    print('Index map created for variables.')

            # store a few items
            self.missing_value = NaN
            if verbose:
                print(f'Took {perf_counter()-t0:.6f}s to read in data')
            if printfiles:
                print(self.filename)

            # GAMERA data has all the timestamps in all the files.
            # This will confuse the lazy interpolation, so stripping down the
            # times dict to one file entry (only start and end fields needed).
            # For ms_timing, 'all' has ms resolution, start and end do not.
            self.singletimes = {'start': self.times[p]['all'][0],
                                'end': self.times[p]['all'][-1]}

            # register interpolators for each requested variable
            t_reg = perf_counter()
            # store original list b/c gridded interpolators change key list
            varname_list = [key for key in self.variables.keys()]
            for varname in varname_list:
                self.register_variables(varname, gridded_int)
            if verbose:
                print(f'Took {perf_counter()-t_reg:.5f}s to register ' +
                      f'{len(varname_list)} variables.')
            if verbose:
                print(f'Took a total of {perf_counter()-t0:.5f}s to kamodofy' +
                      f' {len(varname_list)} variables.')

        # define and register the variable
        def register_variables(self, varname, gridded_int):
            '''Functionalizes the indicated dataset.'''

            # determine coordinate variables and xvec by coord list
            key = self.variables[varname]['data']
            coord_list = [value[5] for key, value in model_varnames.items()
                          if value[0] == varname][0]
            gvar = [key for key, value in model_varnames.items() if
                    value[0] == varname][0]
            coord_str = [value[3]+value[4] for key, value in
                         model_varnames.items() if value[0] == varname][0]
            if 'time' in coord_list:
                coord_dict = {'time': {'units': 'hr',
                                       'data': self.times[key]['all']},
                              'X': {'units': 'R_E', 'data': self._X},
                              'Y': {'units': 'R_E', 'data': self._Y},
                              'Z': {'units': 'R_E', 'data': self._Z}}

                def func(i, fi):  # i = file# (always 0), fi = slice# (= Step#)
                    # Do the data need to be assembled for the interpolator,
                    # or left in blocks?
                    # If it needs to be assembled, do that here per time step *************
                    if len(self.pattern_files[key]) > 1:
                        data = G.AssembleGrid(self.pattern_files[key],
                                              self.variable_map,
                                              False, gvar, step=fi)
                    else:
                        h5_data = h5py.File(self.pattern_files[key][0])
                        data = array(h5_data['Step#'+str(fi)][gvar])
                        h5_data.close()
    
                    # define custom interpolator here  ********************************
                    def interp(xvec):
                        tic = perf_counter()
                        X, Y, Z = xvec.T  # xvec can be used like this
                        # call custom interpolator here
                        print('variable', i, fi, data.shape)
                        # dummy code for now
                        if not isinstance(X, ndarray):
                            return NaN
                        else:
                            return zeros(len(X)) * NaN
                    return interp
    
                # functionalize the variable dataset
                tmp = self.variables[varname]
                tmp['data'] = zeros((2, 2, 2, 2))  # saves execution time
                self = RU.Functionalize_Dataset(
                    self, coord_dict, varname, tmp, gridded_int, coord_str,
                    interp_flag=3, func=func, times_dict=self.singletimes,
                    func_default='custom')
                # choosing large chunked format, same as WACCMX.
            else:  # functionalize the constants
                coord_dict = {'X': {'units': 'R_E', 'data': self._X},
                              'Y': {'units': 'R_E', 'data': self._Y},
                              'Z': {'units': 'R_E', 'data': self._Z}}
                
                def func():
                    # Do the data need to be assembled for the interpolator,
                    # or left in blocks?
                    # If it needs to be assembled, do that here         *************
                    if len(self.pattern_files[key]) > 1:
                        data = G.AssembleGrid(self.pattern_files[key],
                                              self.constant_map, True, gvar)
                    else:
                        h5_data = h5py.File(self.pattern_files[key][0])
                        data = array(h5_data[gvar])
                        h5_data.close()
    
                    # define custom interpolator here  ***********************************
                    def interp(xvec):
                        tic = perf_counter()
                        X, Y, Z = array(xvec).T  # xvec can be used like this
                        # call custom interpolator here
                        print('constant', data.shape)
                        # dummy code for now
                        if not isinstance(X, ndarray):
                            return NaN
                        else:
                            return zeros(len(X)) * NaN
                    return interp
                
                # functionalize the variable dataset
                tmp = self.variables[varname]
                tmp['data'] = zeros((2, 2, 2))  # saves execution time
                
                self = RU.Functionalize_Dataset(
                    self, coord_dict, varname, tmp, gridded_int, coord_str,
                    interp_flag=0, func=func, func_default='custom')

            return
    return MODEL
