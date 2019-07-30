import random

""" Experiment parameters """
# Simulation property
normFileWrite = False
viewerFileWrite = True
rtdTraining = False
trainingFileName = 'check.csv'  # if name contains 'check', print file for checking training data values.
iteration = 1
normalization = True

""" Simulation parameters """
# Simulator 동작 시에 변하지 않는 Parameter 값들
UTILCUTTIME = 86400
# Simulator 동작 시에 변하지 않지만 DB에서 받아오는 Parameter 값들
moveTime = 900  # Move는 DB에서 말고 그냥 여기서 정의하게 하는건 어떨지?
datCutDay = 1

# 일단 problem reader에서 이 쪽의 값을 변경하지 않으므로 주석 처리
# DASTRatio = 0.7
# WBSTRatio = 1.3

""" Network parameters """

""" Learner Option Parameter """
# For Options
reservePolicy = "EmptyBuffer"
DA_waiting_weight = 0.33
waiting_weight = 0.33
idle_weight = 0.33

""" DA/WB RTS/RTD Options"""
# DARTDPolicy = "learner"
DARTDPolicy = "random"
rule_list = ['FIFO', 'LOR', 'MOR', 'large', 'small', 'SPT', 'LPT', 'LNQ', 'FLNQ', 'SNQ', 'STOCK']
idle_rule_list = ['MOR', 'LNQ', 'STOCK' ]
waiting_rule_list = ['FIFO', 'LOR', 'large', 'small', 'SPT', 'LPT',  'FLNQ', 'SNQ']
"""--------------------------------"""
WBRTDPolicy = "large"
"""--------------------------------"""
randomDecisionCriteria = random.random #  simulator 돌릴 때 초기화 하는게 더 나을 수도..


