import tensorflow as tf
from learner.regression import *
from simulator.jSim import *
from simulator.jSimUtil import *
import simulator.simParameter as sp
from problemIO.problem import *


def performance_test(sim_parameter, problem_reader, problem_num, model_name='b_64_32_16',
                     nodes_per_layer=[64, 32, 16]):
    graph1 = tf.Graph()
    graph2 = tf.Graph()
    if sim_parameter.DARTDPolicy == 'learner':
        with graph1.as_default():
            sess1 = tf.Session(graph=graph1)
            DA_idleDNN = DNN_test(sess1, model_name, 27, nodes_per_layer, 'idle', 50)
        with graph2.as_default():
            sess2 = tf.Session(graph=graph2)
            DA_waitingDNN = DNN_test(sess2, model_name, 27, nodes_per_layer, 'waiting', 50)
    pi = problem_reader.generateProblem(problem_num, False)
    """ ------------------------------------- """
    if sim_parameter.DARTDPolicy == 'learner':
        jsim = JSim(sp, pi, DA_waitingDNN, DA_idleDNN)
    else:
        jsim = JSim(sp, pi)
    sr = jsim.runSimul()  # rtd data generation
    assert isinstance(sr, SolutionResult)
    print(problem_num, round(sr.avg_WaitingTime, 2), round(sr.idle_time_bottleneck, 2), round(sr.avg_WaitingTime + sr.idle_time_bottleneck, 2),
          round(sr.avg_TAT, 2), round(sr.utilizationPerOperation["WB"], 2), round(sr.makespan / 3600, 2))

def generate_training_data(sim_parameter, problem_reader, data_type):
    sp.DARTDPolicy = 'random'
    sp.rtdTraining = True
    start_num = 0
    num_of_problem = 0
    if data_type == 'training':
        start_num = 1
        num_of_problem = 30
        sp.trainingFileName = sp.trainingFileName + '_training'
    elif data_type == 'validation':
        start_num = 31
        num_of_problem = 20
        sp.trainingFileName = sp.trainingFileName + '_validation'
    for i in range(sim_parameter.iteration):
        for j in range(num_of_problem):
            pi = problem_reader.generateProblem(j + start_num, False)
            jsim = JSim(sp, pi)
            sr = jsim.runSimul()
            assert isinstance(sr, SolutionResult)
            print(j, round(sr.avg_WaitingTime, 2), round(sr.idle_time_bottleneck, 2),
                  round(sr.avg_WaitingTime + sr.idle_time_bottleneck, 2),
                  round(sr.avg_TAT, 2), round(sr.utilizationPerOperation["WB"], 2), round(sr.makespan / 3600, 2))




