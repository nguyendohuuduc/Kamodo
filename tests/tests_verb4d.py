import unittest
from unittest import TestCase
from unittest.mock import patch

from io import StringIO
import os
import numpy as np
import re
from datetime import datetime, timezone
from math import isnan
from dataclasses import dataclass, field
from typing import List

# LatexFormatter as some point is used to get LaTeX string out of Kamodo object
# We simply apply this formater to check if the LaTeX is returned.
from IPython.core.formatters import LatexFormatter

import rbamlib
import kamodo_ccmc.flythrough.model_wrapper as MW


# Supporting functions
def _latex_wrap(text):
    # This regex pattern matches LaTeX-like variables with underscores
    pattern = r'(\w+)_(\w+)'

    # The replacement string uses backreferences to capture groups and add curly braces around the second part
    replacement = r'\1_{\2}'

    # Use re.sub to replace the pattern with the replacement string
    return re.sub(pattern, replacement, text)


# Supporting class
class FakeDataGenerator:
    """ This class generates fake VERB output """
    output_dir = "output"
    output_path = output_dir + '/'  # because Kamodo cannot work without slash
    teardown = True  # perform teardown at the end. If folder exist - do nothing.
    overwrite = True  # Overwrite created dataset

    @dataclass
    class Node:
        values: List[float] = field(default_factory=list)

        @property
        def min(self):
            return self.values[0]

        @property
        def max(self):
            return self.values[1]

        @property
        def n(self):
            return int(self.values[2])

        def linspace(self):
            return np.linspace(self.values[0], self.values[1], int(self.values[2]))

        def __getitem__(self, index):
            return self.values[index]

    @dataclass
    class Grid:
        L: 'FakeDataGenerator.Node'
        E: 'FakeDataGenerator.Node'
        A: 'FakeDataGenerator.Node'
        T: 'FakeDataGenerator.Node'
        M: 'FakeDataGenerator.Node'
        K: 'FakeDataGenerator.Node'

    grid = Grid(
        T=Node([0., 4., 5]),
        L=Node([1., 4., 3]),
        A=Node([np.rad2deg(0.1), np.rad2deg(np.pi / 2 - 0.1), 5]),
        K=Node([rbamlib.conv.Lal2K(4, np.pi / 2 - 0.1), rbamlib.conv.Lal2K(1, 0.1), 5]),  # K - setup based on A
        E=Node([-2., 2., 4]),
        M=Node([rbamlib.conv.en2mu(10 ** -2, 1, 0.1), rbamlib.conv.en2mu(10 ** 2, 4, np.pi / 2 - 0.1), 4]),
        # Mu - setup based on E
    )

    @staticmethod
    def generate_fake_out1d(file_path):
        header = 'Variables = "time", "Kp", "Boundary_fluxes", "Lpp", "tau", "DCT_Daa WT_CHORUS_DAY_2016", "DCT_Daa WT_CHORUS_NIGHT_2016", "DCT_Dpp WT_CHORUS_DAY_2016", "DCT_Dpp WT_CHORUS_NIGHT_2016", "DCT_Dpa WT_CHORUS_DAY_2016", "DCT_Dpa WT_CHORUS_NIGHT_2016", "DCT_DaaLpp WT_HISS_2016", "DCT_DppLpp WT_HISS_2016", "DCT_DpaLpp WT_HISS_2016"\n'
        zone = 'ZONE T="1d-output"\n'
        grid = FakeDataGenerator.grid
        time_steps = grid.T.linspace()
        data = np.random.random((grid.T.n, 13))

        with open(file_path, 'w') as file:
            file.write(header)
            file.write(zone)
            for i, time in enumerate(time_steps):
                file.write(f'{time}\t' + '\t'.join(map(str, data[i])) + '\n')

    @staticmethod
    def generate_fake_outpsd(file_path):
        header = 'VARIABLES = "Phase_Space_Density"\n'
        grid = FakeDataGenerator.grid
        time_steps = grid.T.linspace()
        data_shape = [grid.L.n, grid.E.n, grid.A.n]

        with open(file_path, 'w') as file:
            file.write(header)
            for t in time_steps:
                file.write(f'ZONE T="{t}" I={data_shape[2]}, J={data_shape[1]}, K={data_shape[0]}\n')
                data = np.random.random(np.prod(data_shape))
                for value in data:
                    file.write(f'{value:e}\n')

    @staticmethod
    def generate_fake_perp_grid(file_path):
        grid = FakeDataGenerator.grid
        header = f'VARIABLES = "L, Earth radius", "Energy, MeV", "Pitch-angle, deg", "pc"\nZONE T="Grid"  I={grid.A.n}, J={grid.E.n}, K={grid.L.n}\n'
        L_values = grid.L.linspace()
        E_values = 10. ** grid.E.linspace()
        A_values = grid.A.linspace()
        pc_values = np.random.random((grid.L.n, grid.E.n, grid.A.n))

        with open(file_path, 'w') as file:
            file.write(header)
            for i, L in enumerate(L_values):
                for j, E in enumerate(E_values):
                    for k, A in enumerate(A_values):
                        pc = pc_values[i, j, k]
                        file.write(f'{L:e}\t{E:e}\t{A:e}\t{pc:e}\n')

    @staticmethod
    def grid_lea_dict():
        g = FakeDataGenerator.grid
        grid = {'time': [g.T[0] * 24, g.T[1] * 24, 'hr'],
                'L': [g.L[0], g.L[1], ''],
                'E_e': [10. ** g.E[0], 10. ** g.E[1], 'MeV'],
                'alpha_e': [g.A[0], g.A[1], 'deg']
                }
        return grid

    @staticmethod
    def grid_lea(idx):
        return [FakeDataGenerator.grid.T[idx],
                FakeDataGenerator.grid.L[idx],
                10 ** FakeDataGenerator.grid.E[idx],
                FakeDataGenerator.grid.A[idx]]

    @staticmethod
    def grid_lmk(idx):
        return [FakeDataGenerator.grid.T[idx],
                FakeDataGenerator.grid.L[idx],
                FakeDataGenerator.grid.M[idx],
                FakeDataGenerator.grid.K[idx]]

    @staticmethod
    def setup_fake_data():
        if os.path.exists(FakeDataGenerator.output_dir) and FakeDataGenerator.teardown:
            raise unittest.SkipTest("Test cannot be done because the folder 'output' already exists.")
        elif not os.path.exists(FakeDataGenerator.output_dir) or FakeDataGenerator.overwrite:
            os.makedirs(FakeDataGenerator.output_dir, exist_ok=FakeDataGenerator.overwrite)
            FakeDataGenerator.generate_fake_out1d(os.path.join(FakeDataGenerator.output_dir, 'out1d.dat'))
            FakeDataGenerator.generate_fake_outpsd(os.path.join(FakeDataGenerator.output_dir, 'OutPSD.dat'))
            FakeDataGenerator.generate_fake_perp_grid(os.path.join(FakeDataGenerator.output_dir, 'perp_grid.plt'))

    @staticmethod
    def teardown_fake_data():
        if FakeDataGenerator.teardown:
            for file_name in os.listdir(FakeDataGenerator.output_dir):
                file_path = os.path.join(FakeDataGenerator.output_dir, file_name)
                os.remove(file_path)
            os.rmdir(FakeDataGenerator.output_dir)


# Tests
class TestVerb01BasicSetup(unittest.TestCase):
    """ This class checks basic setup of the VERB Kamodo model """

    # Static model name
    model = 'VERB-3D'

    @patch('sys.stdout', new_callable=StringIO)
    def test00_Choose_Model_Global(self, mock_stdout):
        """ Test that VERB is present in the global list of models"""
        # List all models
        MW.Choose_Model()
        # Get the entire output
        output = mock_stdout.getvalue()
        self.assertIn("VERB-3D", output, "Model name VERB-3D is missing")

    def test00_Choose_Model(self):
        """ Confirming the model existence """
        model = MW.Choose_Model(self.model)
        self.assertEqual(model.MODEL().modelname, self.model, "Model class does not have correct modelname property")

    def test00_Model_Reader(self):
        """ Confirming the model existence """
        model = MW.Model_Reader(self.model)
        self.assertEqual(model.modelname, self.model, "Model class does not have correct modelname property")

    @patch('sys.stdout', new_callable=StringIO)
    def test01_Variable_Search_Global(self, mock_stdout):
        """ Test that VERB is present in the global list of variables"""
        # List all variables
        MW.Variable_Search('')

        # Get the entire output
        output = mock_stdout.getvalue()

        self.assertIn("VERB-3D", output, "Model name VERB-3D is missing")
        self.assertIn("PSD", output, "Variable PSD is missing")
        self.assertIn("Phase Space Density", "Variable description (Phase Space Density) is missing")

    @patch('sys.stdout', new_callable=StringIO)
    def test03_Variable_Search(self, mock_stdout):
        """ Test for specific variables when model is specified"""
        # List all variables
        MW.Variable_Search('', self.model)

        # Get the entire output
        output = mock_stdout.getvalue()

        self.assertIn("PSD", output, "Variable PSD is missing")
        self.assertIn("Phase Space Density", "Variable description (Phase Space Density) is missing")

    @patch('sys.stdout', new_callable=StringIO)
    def test04_Variable_Search_Local(self, mock_stdout):
        MW.Variable_Search('Phase Space Density', self.model)

        # Get the entire output
        output = mock_stdout.getvalue()

        self.assertIn("PSD", output, "Variable PSD is missing")
        self.assertIn("Phase Space Density", "Variable description (Phase Space Density) is missing")

    def test05_Ver_3D(self):
        """ Test if the model has expected 3D variables description """
        expected_output = [
            'L-shell',
            'Electron energy',
            'Equatorial pitch angle',
            'Momentum times speed of light',
            '1st adiabatic invariant mu',
            '2dn adiabatic invariant K'
        ]

        result = MW.Var_3D(self.model)

        for item in expected_output:
            self.assertIn(item, result, f"{item} is missing in the result")

    def test06_Ver_units(self):
        def test_Var_units(self):
            variables_requested = [
                'PSD_lea', 'flux_lea', 'L', 'E_e', 'alpha_e', 'pc', 'PSD_lmk', 'mu', 'K'
            ]
            expected_output = {
                'PSD_lea': '(c/MeV/cm)**3',
                'flux_lea': '1/(s*cm**2*keV*sr)',
                'L': '',
                'E_e': 'MeV',
                'alpha_e': 'deg',
                'pc': 'MeV',
                'PSD_lmk': '(c/MeV/cm)**3',
                'mu': 'MeV/G',
                'K': '10**-4*T*(m/m)**1/2'
            }

            result = MW.Var_units(self.model, ['Trash', variables_requested])

            for var in expected_output:
                self.assertIn(var, result, f'{var} is missing')
                # For now, we just test that units are present. We do not test the unites themselves yet.
                self.assertIsInstance(result[var], str, f'Error with {var} units')

            # Just test a single unit
            self.assertIsInstance(result['E_e'], expected_output['E_e'], f'Error with E_e units values')

            # Ensure 'Trash' is not in the result
            self.assertNotIn('Trash', result, 'Unexpected variable is returned')


class TestVerb02DatasetGeneration(TestCase):
    output_dir = FakeDataGenerator.output_dir
    output_path = output_dir + '/'  # because Kamodo cannot work without slash
    model = 'VERB-3D'

    @classmethod
    def setUpClass(cls):
        FakeDataGenerator.setup_fake_data()

    @classmethod
    def tearDownClass(cls):
        FakeDataGenerator.teardown_fake_data()

    def setUp(cls):
        """ Cleanup data folder before"""
        files_to_check = [
            os.path.join(cls.output_dir, cls.model + '_list.txt'),
            os.path.join(cls.output_dir, cls.model + '_times.txt')
        ]
        nc_extension = '.nc'

        # Remove specific files
        for file_path in files_to_check:
            if os.path.isfile(file_path):
                os.remove(file_path)

        # Remove .nc files
        for file_name in os.listdir(cls.output_dir):
            if file_name.endswith(nc_extension):
                os.remove(os.path.join(cls.output_dir, file_name))

        # Verify files are removed
        for file_path in files_to_check:
            if os.path.isfile(file_path):
                raise unittest.SkipTest(f"{file_path} was not removed")

    def test01_Generate(self):
        # get times dictionary and datetime filedate object from files
        reader = MW.Model_Reader(self.model)
        ko = reader(self.output_path, filetime=True)  # creates any preprocessed files
        list_file = os.path.join(self.output_dir, self.model + '_list.txt')
        times_file = os.path.join(self.output_dir, self.model + '_times.txt')

        self.assertTrue(os.path.isfile(list_file), 'List file is not created')
        self.assertTrue(os.path.isfile(times_file), 'Times file is not created')

    def test02_File_Times(self):
        # 1970 - is default datetime
        expected_start_time = datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)
        expected_end_time = datetime(1970, 1, 5, 0, 0, tzinfo=timezone.utc)
        result = MW.File_Times(self.model, self.output_path, print_output=False)

        self.assertEqual(result, (expected_start_time, expected_end_time), 'File_Time returns incorrect time interval')

    def test03_File_list(self):
        # Call the function
        result = MW.File_List(self.model, self.output_path, print_output=False)
        file_list = result.split(',')
        file_names = [os.path.basename(file_path) for file_path in file_list]

        # Check if .nc files are present
        nc_files = [file for file in file_names if file.endswith('.nc')]
        self.assertTrue(len(nc_files) > 0, '.nc files are missing from the File list')

        # Check if there are exactly 10 files containing 'OutPSD'
        outpsd_files = [file for file in file_names if 'OutPSD' in file]
        self.assertTrue(len(outpsd_files) > 0, 'OutPSD are missing from the File list')

        # Check if 'perp_grid.nc' is present
        self.assertIn('perp_grid.nc', file_names, 'Grid is missing from the File list')

    def test04_Model_Variables(self):
        results = MW.Model_Variables(self.model, self.output_path, return_dict=True)
        # Check results contains variable 'PSD_lea'
        self.assertIn('PSD_lea', results.keys(), 'Model_Variables does not return PSD_lea')

    def test05_Variable_Search(self):
        results = MW.Variable_Search('Phase Space Density', self.model, self.output_path, return_dict=True)
        # Check results contains variable 'PSD_lea'
        self.assertIn('PSD_lea', results.keys(), 'Variable_Search does not return PSD_lea')


class TestVerb03DatasetCheck(TestCase):
    """ This class is advanced test with fake dataset. """

    model = 'VERB-3D'
    output_dir = FakeDataGenerator.output_dir
    output_path = output_dir + '/'  # because Kamodo cannot work without slash

    xvar_list = ['L', 'E_e', 'alpha_e', 'mu', 'K']
    tvar_list = ['PSD_lea', 'PSD_lmk', 'flux_lea']
    variables_requested = xvar_list + tvar_list

    @classmethod
    def setUpClass(cls):
        FakeDataGenerator.setup_fake_data()
        # Generate model files
        cls.reader = MW.Model_Reader(cls.model)
        cls.reader(cls.output_path, filetime=True)  # creates any preprocessed files

        list_file = os.path.join(cls.output_dir, cls.model + '_list.txt')
        times_file = os.path.join(cls.output_dir, cls.model + '_times.txt')

        if not os.path.isfile(list_file) and not os.path.isfile(times_file):
            raise unittest.SkipTest("Test cannot be done because the dataset was not created successfully.")

        cls.formatter = LatexFormatter()

    @classmethod
    def tearDownClass(cls):
        FakeDataGenerator.teardown_fake_data()

    def test01_known_variable(self):
        # Get Kamodo object
        ko = self.reader(self.output_path, variables_requested=['PSD_lea'])
        data = self.formatter(ko)
        self.assertIn('PSD_{lea}', data, 'The LaTeX output cannot be generated')

    @patch('sys.stdout', new_callable=StringIO)
    def test02_unknown_variable(self, mock_stdout):
        # Get Kamodo object
        ko = self.reader(self.output_path, variables_requested=['Trash'])
        data = self.formatter(ko)
        self.assertEqual('', data, 'The LaTeX output is not empty')

        # Get the entire output
        output = mock_stdout.getvalue()
        self.assertIn("Variable name(s) not recognized: ['Trash']", output, 'Error message is absent')

    @patch('sys.stdout', new_callable=StringIO)
    def test03_all_variable_explicit(self, mock_stdout):
        # Get Kamodo object
        ko = self.reader(self.output_path, variables_requested=self.variables_requested)
        data = self.formatter(ko)
        for var in self.variables_requested:
            self.assertIn(_latex_wrap(var), data, f'The LaTeX output for variable {var} cannot be generated')

        # Get the entire output
        output = mock_stdout.getvalue()
        self.assertEqual('', output, 'The std output is not empty, some variables are likely missing')

    @patch('sys.stdout', new_callable=StringIO)
    def test03_all_variable_implicit(self, mock_stdout):
        # Get Kamodo object
        ko = self.reader(self.output_path)
        data = self.formatter(ko)
        for var in self.variables_requested:
            self.assertIn(_latex_wrap(var), data, f'The LaTeX output for variable {var} cannot be generated')

        # Get the entire output
        output = mock_stdout.getvalue()
        self.assertEqual('', output, 'The std output is not empty, some variables are likely missing')

    def test04_Coord_Grid(self):
        """ Testing Coord_Grid only for regular variables"""
        ko = self.reader(self.output_path)
        expected_grid = FakeDataGenerator.grid_lea_dict()

        # Test individual variables
        for var in self.variables_requested:
            res = MW.Coord_Range(ko, [var], print_output=False, return_dict=True)
            # All variables have 'L' in their grid. Testing only against L
            self.assertEqual(res[var]['L'], expected_grid['L'], f'Grid is incorrect for {var}')

        # Test all variables
        res = MW.Coord_Range(ko, self.variables_requested, print_output=False, return_dict=True)
        # Check the grid
        for r in res:
            self.assertEqual(res[r]['L'], expected_grid['L'], f'Grid is incorrect for {r}')

    def test05_Coord_Grid_ijk(self):
        """ Testing Coord_Grid only for ijk variables"""
        ko = self.reader(self.output_path)
        # TODO: make this list based on the gridded kamodo variables
        ijk_variables = ['PSD_lmk_ijk', 'PSD_lea_ijk', 'flux_lea_ijk']
        expected_grid = FakeDataGenerator.grid_lea_dict()

        # Test all variables
        res = MW.Coord_Range(ko, ijk_variables, print_output=False, return_dict=True)
        # Check the grid
        for r in res:
            self.assertEqual(res[r]['L'], expected_grid['L'], f'Grid is incorrect for {r}')

    def test06_valid_PSD_lea(self):
        # Check that the kamodo object was built properly.
        ko = self.reader(self.output_path, variables_requested='PSD_lea')

        # Grid start
        tvec = FakeDataGenerator.grid_lea(0)
        self.assertFalse(isnan(ko.PSD_lea(tvec)[0]))

        # Grid end
        tvec1 = FakeDataGenerator.grid_lea(1)
        self.assertFalse(isnan(ko.PSD_lea(tvec1)[0]))

    def test07_valid_PSD_lea_ijk(self):

        ko = self.reader(self.output_path, variables_requested='PSD_lea')
        tvec_grid = [FakeDataGenerator.grid_lea(0), FakeDataGenerator.grid_lea(1)]
        tvec = list((np.array(tvec_grid[0]) + (np.array(tvec_grid[1]) - np.array(tvec_grid[0])) / 10))

        val_psd_lea = ko.PSD_lea(tvec)
        self.assertFalse(isnan(val_psd_lea))

        val_psd_lea_int = ko.PSD_lea_ijk(time=tvec[0], L=tvec[1], E_e=tvec[2], alpha_e=tvec[3])
        self.assertFalse(isnan(val_psd_lea_int))

        self.assertAlmostEquals(val_psd_lea, val_psd_lea_int, places=2)

    def test08_valid_interpolator(self):
        # Confirm that the interpolator works for each testing variable and type
        tvec_grid = [FakeDataGenerator.grid_lea(0), FakeDataGenerator.grid_lea(1)]
        tvec = list((np.array(tvec_grid[0]) + (np.array(tvec_grid[1]) - np.array(tvec_grid[0])) / 10))
        xvec = tvec[1::]

        tvec_grid_lmk = [FakeDataGenerator.grid_lmk(0), FakeDataGenerator.grid_lmk(1)]
        tvec_lmk = list((np.array(tvec_grid_lmk[0]) + (np.array(tvec_grid_lmk[1]) - np.array(tvec_grid_lmk[0])) / 10))
        xvec_lmk = tvec_lmk[1::]

        xvar_list = self.xvar_list
        tvar_list = self.tvar_list

        # Full Kamodo object
        ko = self.reader(self.output_path)

        for var in xvar_list:
            ko_var = getattr(ko, var, None)
            self.assertIsNotNone(ko_var, f'Kamodo variable {var} object is invalid')
            if var in ['mu', 'K']:
                self.assertFalse(np.isnan(ko_var(xvec_lmk)).any(), f'{var} is nan')
            else:
                self.assertFalse(np.isnan(ko_var(xvec)).any(), f'{var} is nan')

        for var in tvar_list:
            ko_var = getattr(ko, var, None)
            self.assertIsNotNone(ko_var, 'Kamodo variable object is invalid')
            if '_lmk' in var:
                self.assertFalse(np.isnan(ko_var(tvec_lmk)).any(), f'{var} is nan')
            else:
                self.assertFalse(np.isnan(ko_var(tvec)).any(), f'{var} is nan')

    def test09_valid_ijk_time_slice(self):
        tvec_grid = [FakeDataGenerator.grid_lea(0), FakeDataGenerator.grid_lea(1)]
        tvec = list((np.array(tvec_grid[0]) + (np.array(tvec_grid[1]) - np.array(tvec_grid[0])) / 10))

        ko = self.reader(self.output_path, variables_requested=self.tvar_list)
        for var in self.tvar_list:
            val = ko[var + '_ijk'](time=tvec[0])
            self.assertFalse(np.isnan(val).any())

    def test09_valid_ijk_L_slice(self):
        """ Test only for lea"""
        tvec_grid = [FakeDataGenerator.grid_lea(0), FakeDataGenerator.grid_lea(1)]
        tvec = list((np.array(tvec_grid[0]) + (np.array(tvec_grid[1]) - np.array(tvec_grid[0])) / 10))

        ko = self.reader(self.output_path, variables_requested=['E_e', 'alpha_e', 'mu', 'K'])
        E_e = np.random.choice(ko.E_e())
        alpha_e = np.random.choice(ko.alpha_e())
        mu = np.random.choice(ko.mu())
        K = np.random.choice(ko.K())

        ko = self.reader(self.output_path, variables_requested=self.tvar_list)
        for var in self.tvar_list:
            if '_lea' in var:
                val = ko[var + '_ijk'](time=tvec[0], E_e=E_e, alpha_e=alpha_e)
                self.assertFalse(np.isnan(val).any())
                self.assertTrue(len(val), FakeDataGenerator.grid.L.n)
            if '_lmk' in var:
                val = ko[var + '_ijk'](time=tvec[0], mu=mu, K=K)
                self.assertFalse(np.isnan(val).any())
                self.assertTrue(len(val), FakeDataGenerator.grid.L.n)

    def test10_valid_ijk_time_series(self):

        ko = self.reader(self.output_path)
        L = np.random.choice(ko.L())
        E_e = np.random.choice(ko.E_e())
        alpha_e = np.random.choice(ko.alpha_e())
        mu = np.random.choice(ko.mu())
        K = np.random.choice(ko.K())

        for var in self.tvar_list:
            if '_lea' in var:
                val = ko[var + '_ijk'](L=L, E_e=E_e, alpha_e=alpha_e)
                self.assertFalse(np.isnan(val).any())
                self.assertTrue(len(val), FakeDataGenerator.grid.T.n)
            if '_lmk' in var:
                val = ko[var + '_ijk'](L=L, mu=mu, K=K)
                self.assertFalse(np.isnan(val).any())
                self.assertTrue(len(val), FakeDataGenerator.grid.T.n)

    def test11_valid_filedate(self):
        expected_filedate = datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)
        ko = self.reader(self.output_path, variables_requested='PSD_lea')
        self.assertEqual(ko.filedate, expected_filedate)


# TODO: Make this class checking the output. use plotpy generator to control the output somehow.
# class TestVerb04plot(unittest.TestCase):

if __name__ == '__main__':
    unittest.main()
