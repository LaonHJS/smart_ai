from problemIO.problem import *
import simulator.simParameter as sp
from execution_function import *

'''====== Parameters ======'''
# Dataset Setting
Table_name = 'dataSet3_B'
pr = ProblemReaderDB(Table_name)

# Simulation Setting
sp.DARTDPolicy = 'learner'
sp.viewerFileWrite = False

# Data Generation Setting
sp.iteration = 3
sp.trainingFileName = 'test_sample_not_normal'
data_type = 'training'
sp.normalization = True
'''====== Functions ======'''
# Performance Test
# performance_test(sp.DARTDPolicy, pr, 1)

# Training Data Generation
generate_training_data(sp, pr, data_type)

