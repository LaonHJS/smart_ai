from problemIO.problem import *
import simulator.simParameter as sp
from execution_function import *

'''====== Parameters ======'''
# Dataset Setting
Table_name = 'dataSet3_B'
pr = ProblemReaderDB(Table_name)

# Simulation Setting
sp.DARTDPolicy = 'learner'
sp.viewerFileWrite = True

# Data Generation Setting
sp.iteration = 1
sp.trainingFileName = 'test_sample'
data_type = 'validation'
sp.normalization = True


'''====== Functions ======'''
# Performance Test
performance_test(sp, pr, 100, 'small_test')

# Training Data Generation
# generate_training_data(sp, pr, data_type)

