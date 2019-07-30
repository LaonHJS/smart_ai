import numpy as np
import copy
from collections import defaultdict
import mysql.connector as mysql


class NormalForState(object):
    def __init__(self, config, key, mean=[], std=[], max_vector=[], min_vector=[]):
        self.savedVector = []  # static variable for multiple-simulation
        self.config = config
        assert isinstance(key, str)
        self.filepath = str(config) + '_' + key + '.txt'
        # For normalization when generating state
        self.mean = mean
        self.std = std
        self.max_vector = max_vector
        self.min_vector = min_vector
        """
        if for_normalization is not True:
            f = open(self.filepath, 'r')
            for line in f.readlines():
                row = line.rstrip('\n').split(',')
                # row is the list of numbers strings for this row, such as ['1', '0', '4', ...]
                cols = [float(x) for x in row]
                # cols is the list of numbers for this row, such as [1, 0, 4, ...]
                self.mean.append(cols[0])
                self.var.append(cols[1])
            f.close()
        """

    def append_state(self, vector):
        # Normalization.savedVector.append(vector)
        self.savedVector.append(vector)

    def normalize(self, vector, method='MinMax'):
        result = np.zeros(len(self.mean))
        if method == 'Gaussian':
            meanVector = np.array(self.mean)
            stdevVector = np.array(self.std)
            result = np.nan_to_num((vector - meanVector) / stdevVector)
            # for i in range(len(result)):
            #     if result[i] > 100000000:
            #         result[i] = 0
            # for idx, value in vector:
            #     normalizedValue = (value - self.mean[idx]) / self.var[idx]
            #     result.append(normalizedValue)
        elif method == 'MinMax':
            np_min = np.array(self.min_vector)
            np_max = np.array(self.max_vector)
            result = np.nan_to_num((vector - np_min) / (np_max - np_min))
        return result


class NormalForScore(object):
    def __init__(self, config, median=[], mean=[], std=[], max_vector=[], min_vector=[]):
        # For Score
        self.score_vectors = []
        self.config = config

        # For normalization when generating training data
        self.mean = mean
        self.median = median
        self.std = std
        self.max_vector = max_vector
        self.min_vector = min_vector

    def append_score(self, score_vector):
        self.score_vectors.append(score_vector)

    def normalize(self, vector, method='MeanMax', score_range=None):
        result = np.zeros(len(self.mean))
        if method == 'MinMax':
            np_median = np.array(self.median) * 2 + 1  # *2는 중간값의 두 배, +1 은 smoothing
            np_min = np.array(self.min_vector)
            # np_max = np.array(self.max_vector)
            temp_value = ((vector - np_min) * (score_range[0] - score_range[1]) / (np_median - np_min)) + score_range[1]
            criteria_vec = [score_range[0]]*temp_value.size
            result = np.maximum(temp_value, criteria_vec)
        elif method == 'MeanMax':
            np_max = np.array(self.mean) + 1  #  +1 은 smoothing
            np_min = np.array(self.min_vector)
            # np_max = np.array(self.max_vector)
            temp_value = ((vector - np_min) * (score_range[0] - score_range[1]) / (np_max - np_min)) + score_range[1]
            criteria_vec = [score_range[0]] * temp_value.size
            result = np.maximum(temp_value, criteria_vec)
        elif method == 'MeanStdMax':
            np_max = np.array(self.mean) + np.array(self.std) + 1  # +1 은 smoothing
            np_min = np.array(self.min_vector)
            temp_value = ((vector - np_min) * (score_range[0] - score_range[1]) / (np_max - np_min)) + score_range[1]
            criteria_vec = [score_range[0]] * temp_value.size
            result = np.maximum(temp_value, criteria_vec)
        return result

class NormalDAWaitingScore(object):
    def __init__(self, config, median=[], mean=[], std=[], max_vector=[], min_vector=[]):
        # For Score
        self.score_vectors = []
        self.config = config

        # For normalization when generating training data
        self.mean = mean
        self.median = median
        self.std = std
        self.max_vector = max_vector
        self.min_vector = min_vector

    def append_score(self, score_vector):
        self.score_vectors.append(score_vector)

    def normalize(self, vector, method='MeanMax', score_range=None):
        if score_range is None:
            score_range = [0, 1]
        result = np.zeros(len(self.mean))
        if method == 'MinMax':
            np_median = np.array(self.median) * 2 + 1  # *2는 중간값의 두 배, +1 은 smoothing
            np_min = np.array(self.min_vector)
            # np_max = np.array(self.max_vector)
            temp_value = ((vector - np_min) * (score_range[0] - score_range[1]) / (np_median - np_min)) + score_range[1]
            criteria_vec = [score_range[0]]*temp_value.size
            result = np.maximum(temp_value, criteria_vec)
        elif method == 'MeanMax':
            np_max = np.array(self.mean) + 1  #  +1 은 smoothing
            np_min = np.array(self.min_vector)
            # np_max = np.array(self.max_vector)
            temp_value = ((vector - np_min) * (score_range[1] - score_range[0]) / (np_max - np_min)) + score_range[0]
            criteria_vec = [score_range[1]] * temp_value.size
            result = np.minimum(temp_value, criteria_vec)
        elif method == 'MeanStdMax':
            np_max = np.array(self.mean) + np.array(self.std) + 1  # +1 은 smoothing
            np_min = np.array(self.min_vector)
            temp_value = ((vector - np_min) * (score_range[0] - score_range[1]) / (np_max - np_min)) + score_range[1]
            criteria_vec = [score_range[0]] * temp_value.size
            result = np.maximum(temp_value, criteria_vec)
        return result
