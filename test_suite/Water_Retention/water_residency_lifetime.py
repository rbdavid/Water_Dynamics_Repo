#!/Library/Frameworks/Python.framework/Versions/2.7/bin/python
##!/mnt/lustre_fs/users/mjmcc/apps/python2.7/bin/python
# ----------------------------------------
# USAGE:

# ----------------------------------------
# PREAMBLE:

import sys
import numpy as np
from numpy.linalg import *
import MDAnalysis
from MDAnalysis.analysis.align import *
from distance_functions import *

zeros = np.zeros
dot_prod = np.dot
sqrt = np.sqrt
flush = sys.stdout.flush

# ----------------------------------------
# VARIABLE DECLARATION

config_file = sys.argv[1]

necessary_parameters = ['pdb_file','traj_loc','start','end','pocket_selection','pocket_radius','wat_resname']

all_parameters = ['pdb_file','prmtop_file','traj_loc','pocket_selection','wat_resname','pocket_radius','number_of_wats_filename','wat_res_nums_filename','center_of_geometry_filename','COG_delta_write','water_retention_filename','Wrapped','summary_bool','summary_filename']

# ----------------------------------------
# SUBROUTINES:

def ffprint(string):
	print '%s' %(string)
	flush()

def config_parser(config_file):	# Function to take config file and create/fill the parameter dictionary 
	for i in range(len(necessary_parameters)):
		parameters[necessary_parameters[i]] = ''

	# SETTING DEFAULT PARAMETERS FOR OPTIONAL PARAMETERS:
	parameters['wat_resname'] = 'WAT'
	parameters['pocket_radius'] = 6.0
	parameters['number_of_wats_filename'] = 'num_wats_pocket.dat'
	parameters['wat_res_nums_filename'] = 'res_nums_wats.dat'
	parameters['center_of_geometry_filename'] = 'COG_pocket.xyz'
	parameters['COG_delta_write'] = 1000
	parameters['water_retention_filename'] = 'water_retention_analysis.dat'
	parameters['Wrapped'] = True
	parameters['summary_bool'] = True
	parameters['summary_filename'] = 'water_retention_analysis.summary'

	# GRABBING PARAMETER VALUES FROM THE CONFIG FILE:
	execfile(config_file,parameters)
	for key, value in parameters.iteritems():
		if value == '':
			print '%s has not been assigned a value. This variable is necessary for the script to run. Please declare this variable within the config file.' %(key)
			sys.exit()

def summary(filename):
	with open(filename,'w') as W:
		W.write('Using MDAnalysis version: %s\n' %(MDAnalysis.version.__version__))
		W.write('To recreate this analysis, run this line:\n')
		for i in range(len(sys.argv)):
			W.write('%s ' %(sys.argv[i]))
		W.write('\n\nParameters used:\n')
		for i in all_parameters:
			W.write('%s = %s \n' %(i,parameters[i]))
		W.write('\n\n')

# ----------------------------------------
# MAIN:
# CREATING PARAMETER DICTIONARY
parameters = {}
config_parser(config_file)

# ----------------------------------------
# LOADING IN ANALYSIS UNIVERSE AND CREATING THE NECESSARY ATOM SELECTIONS
ffprint('Loading Analysis Universe.')
u = MDAnalysis.Universe(parameters['prmtop_file'],parameters['pdb_file'])
u_all = u.select_atoms('all')
wat = u.select_atoms('resname %s' %(parameters['wat_resname']))
u_pocket = u.select_atoms(parameters['pocket_selection'])

ffprint('Grabbing the Positions of the Binding Pocket to use as reference.')
u_all.translate(-u_pocket.center_of_geometry())
pocket_ref = u_pocket.positions

nWats = wat.n_residues			# number of water residues
nRes0 = wat.residues[0].resid		# residue index is 0 indexed 

if nWats*3 != wat.n_atoms:
	ffprint('nWats*3 != wat.n_atoms. Unexpected number of water atoms. Possible selection error with water residue name.')
	sys.exit()

# ----------------------------------------
# MEMORY DECLARATION

# ----------------------------------------
# TRAJECTORY ANALYSIS 
start = int(parameters['start'])
end = int(parameters['end'])
res_nums = []
nSteps = 0
with open(parameters['number_of_wats_filename'],'w') as X, open(parameters['wat_res_nums_filename'],'w') as Y, open(parameters['center_of_geometry_filename'],'w') as Z:
	ffprint('Beginning trajectory analysis')
	while start <= end:
		ffprint('Loading trajectory %s' %(start))
#		u.load_new('%sproduction.%s/production.%s.dcd' %(parameters['traj_loc'],start,start))
		u.load_new(parameters['traj_loc'])
		nSteps += len(u.trajectory)
		# Loop through trajectory
		for ts in u.trajectory:
			t = u_pocket.center_of_geometry()
			
			if ts.frame%parameters['COG_delta_write'] == 0:
				Z.write('1\n  generated by MDAnalysis and RBD; traj %d frame %d\n X         %10.4f         %10.4f         %10.4f\n' %(start,ts.frame+1,t[0], t[1], t[2]))	#Writing an xyz trajectory of the center of geometry of the binding pocket; the COG particle is labeled as a dummy atom X
			
			u_all.translate(-t)	# Align to reference (moves COG of the pocket to origin)
	
			if not parameters['Wrapped']:
				dims = u.dimensions[:3]	# obtain dimension values to be used for wrapping atoms
				dims2 = dims/2.0
				for i in range(nWats):
					temp = wat.residues[i].atoms[0].position
					t = wrapping(temp,dims,dims2)
					wat.residues[i].translate(t)
	
			R, rmsd = rotation_matrix(u_pocket.positions,pocket_ref)	# Calculate the rotational matrix to align u to the ref, using the pocket selection as the reference selection
			u_all.rotate(R)
		
			pocket_waters = wat.select_atoms('byres point 0 0 0 %d' %(parameters['pocket_radius'])) # Atom selection for the waters within radius angstroms of the COG of the pocket; Assumes that the COG of the pocket is at 0,0,0 xyz coordinates (which it should be bc the translational motion of the pocket is removed...)
			
			nRes = pocket_waters.n_residues		# Calculate the number of waters within the pocket volume
			X.write('%d\n' %(nRes))		# Outputting the number of water residues at timestep ts

			res_nums.append(list(set(pocket_waters.resids)))

			for i in range(nRes):
				res = pocket_waters.residues[i]	
				Y.write('%d   ' %(res.resid))	
			Y.write('\n')
		start += 1

ffprint('Done with saving residue numbers of binding pocket waters.\nBeginning retention lifetime calculations.')

# ------------------------------------------
# 

if nSteps != len(res_nums):
	print 'Number of steps does not equal the number of elements within the res_nums, indicating a timestep where no waters are found in the binding pocket. At the moment, this is assumed to be a bad result.'
	sys.exit()

retention_matrix = np.zeros((nSteps,nSteps),dtype=np.float64)
for initial_ts in range(nSteps-1):
	initial_num_wats = len(res_nums[initial_ts])
	initial_wats = res_nums[initial_ts]
	wat_weight = 1./initial_num_wats
	for j in range(initial_num_wats):
		dt = 1
		while (initial_ts+dt)<nSteps and initial_wats[j] in res_nums[initial_ts+dt]:
			retention_matrix[initial_ts][initial_ts+dt] += wat_weight
			dt += 1
	
	if initial_ts%10 == 0:
		ffprint('Finished analyzing the retention time of waters in timestep %d'%(initial_ts))

# ----------------------------------------
# FINISHING THE AVERAGES
retention_data = np.zeros((nSteps,3),dtype=np.float64)
for i in range(nSteps-1):
	for j in range(i+1,nSteps):
		delta_t = j - i
		retention_data[delta_t][0] +=1
		retention_data[delta_t][1] += retention_matrix[i][j]
		retention_data[delta_t][2] += retention_matrix[i][j]**2

# ----------------------------------------
# OUTPUTTING DATA TO FILE
with open(parameters['water_retention_filename'],'w') as W:
	for i in range(1,nSteps):
		retention_data[i][1] /= retention_data[i][0]
		retention_data[i][2] /= retention_data[i][0]
		retention_data[i][2] -= retention_data[i][1]**2
		retention_data[i][2] = sqrt(retention_data[i][2])
	np.savetxt(W,retention_data)

# ----------------------------------------
# OUTPUTTING SUMMARY OF THE ANALYSIS
if parameters['summary_bool']:
	summary(parameters['summary_filename'])

