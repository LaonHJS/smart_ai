import math
import os
import tensorflow as tf
import numpy as np
from collections import defaultdict


class DNN_training(object):

    def __init__(self, file_name, node_per_hidden_layers):
        x_data = []
        self.y_w_data = []
        self.y_i_data = []
        self.fine_name = file_name
        with open(file_name) as data:
            while True:
                line = data.readline()
                if not line:
                    break
                line = line.strip()
                temp_arr = line.split(',')
                x_data.append(temp_arr[: -3])
                self.y_w_data.append(float(temp_arr[-3]))
                self.y_i_data.append(float(temp_arr[-2]))

        x_data = np.array(x_data)
        self.x_data = x_data
        self.y_w_data = np.array(self.y_w_data)
        self.y_i_data = np.array(self.y_i_data)
        self.input_dim = x_data.shape[1]
        self.output_dim = 1

        self.index_in_epoch = 0
        self.epochs_completed = 0
        self.num_of_examples = len(x_data)
        self.node_per_hidden_layers = node_per_hidden_layers

        self.X = tf.placeholder(dtype=tf.float32, shape=[None, self.input_dim], name='input')
        self.Y = tf.placeholder(dtype=tf.float32, shape=[None, self.output_dim], name='output')
        self.x_v_data = None
        self.y_v_data = None
        self.y_v_w_data = []
        self.y_v_i_data = []
        self.drop_out_prob = tf.placeholder(tf.float32)
        self.performance_dict = defaultdict(list)

    def read_validate_data(self, file_name):
        x_data = []
        with open(file_name) as data:
            while True:
                line = data.readline()
                if not line:
                    break
                line = line.strip()
                temp_arr = line.split(',')
                x_data.append(temp_arr[: -3])
                self.y_v_w_data.append(float(temp_arr[-3]))
                self.y_v_i_data.append(float(temp_arr[-2]))

        x_data = np.array(x_data)
        self.x_v_data = x_data
        self.y_v_w_data = np.array(self.y_v_w_data)
        self.y_v_i_data = np.array(self.y_v_i_data)

    def build_network(self):
        n_out = self.output_dim
        w_out_layer = None
        i_out_layer = None
        with tf.variable_scope('waiting'):
            net = None
            for i in range(len(self.node_per_hidden_layers)):
                if i == 0:
                    net = tf.layers.dense(self.X, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=self.drop_out_prob)
                else:
                    net = tf.layers.dense(net, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=self.drop_out_prob)
            w_out_layer = tf.layers.dense(net, units=n_out, kernel_initializer=tf.contrib.layers.xavier_initializer())
        with tf.variable_scope('idle'):
            net = None
            for i in range(len(self.node_per_hidden_layers)):
                if i == 0:
                    net = tf.layers.dense(self.X, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=self.drop_out_prob)
                else:
                    net = tf.layers.dense(net, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=self.drop_out_prob)
            i_out_layer = tf.layers.dense(net, units=n_out, kernel_initializer=tf.contrib.layers.xavier_initializer())
        return w_out_layer, i_out_layer

    def return_next_batch(self, batch_size, is_random=True):
        start = self.index_in_epoch
        self.index_in_epoch += batch_size
        if self.index_in_epoch > self.num_of_examples:
            # Finished epoch
            self.epochs_completed += 1
            # Shuffle the data
            perm = np.arange(self.num_of_examples)
            if is_random:
                np.random.shuffle(perm)
            self.x_data = self.x_data[perm]
            self.y_w_data = self.y_w_data[perm]
            self.y_i_data = self.y_i_data[perm]

            # Start next epoch
            start = 0
            self.index_in_epoch = batch_size
            assert batch_size <= self.num_of_examples
        end = self.index_in_epoch

        return self.x_data[start:end], self.y_w_data[start:end], self.y_i_data[start:end]

    def conduct_learning(self, learning_rate=0.01, training_epoch=100, batch_size=100, model_name='', use_GPU=False):
        w_predict_value, i_predict_value = self.build_network()
        w_cost = tf.reduce_mean(tf.square(w_predict_value - self.Y))
        i_cost = tf.reduce_mean(tf.square(i_predict_value - self.Y))
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
        w_train_op = optimizer.minimize(w_cost)
        i_train_op = optimizer.minimize(i_cost)

        init = tf.global_variables_initializer()
        saver = tf.train.Saver(max_to_keep=100000)

        # Start training
        tf.logging.set_verbosity(tf.logging.ERROR)
        with tf.Session(config=tf.ConfigProto(log_device_placement=use_GPU)) as sess:
            sess.run(init)
            print('Epoch', 'TrainingError_w', 'TrainingError_i', 'ValidationError_w', 'ValidationError_i')

            for epoch in range(training_epoch):
                dir_name = os.getcwd()
                w_path_ckpt = dir_name + '/rtd_model/' + model_name + '/' + 'waiting'
                i_path_ckpt = dir_name+ '/rtd_model/' + model_name + '/' + 'idle'
                avg_cost = 0
                w_avg_cost = 0
                i_avg_cost = 0
                total_batch = int(self.num_of_examples / batch_size)
                printed_index = 0
                for i in range(total_batch):
                    batch_xs, batch_ys_w, batch_ys_i = self.return_next_batch(batch_size, True)
                    _, w_temp_cost = sess.run([w_train_op, w_cost], feed_dict={self.X: batch_xs, self.Y: np.expand_dims(batch_ys_w, axis=1), self.drop_out_prob: 0.3})
                    _, i_temp_cost = sess.run([i_train_op, i_cost], feed_dict={self.X: batch_xs, self.Y: np.expand_dims(batch_ys_i, axis=1), self.drop_out_prob: 0.3})
                    w_avg_cost += w_temp_cost / total_batch
                    i_avg_cost += i_temp_cost / total_batch

                # Validation Error
                if self.x_v_data is not None:
                    w_val_cost = sess.run(w_cost, feed_dict={self.X: self.x_v_data, self.Y: np.expand_dims(self.y_v_w_data, axis=1), self.drop_out_prob: 0.0})
                    i_val_cost = sess.run(i_cost, feed_dict={self.X: self.x_v_data, self.Y: np.expand_dims(self.y_v_i_data, axis=1), self.drop_out_prob: 0.0})
                    print('%04d' % (epoch + 1), '{:.9f}'.format(w_avg_cost), '{:.9f}'.format(i_avg_cost), '{:.9f}'.format(w_val_cost), '{:.9f}'.format(i_val_cost))
                    if epoch > 4:
                        self.performance_dict['train_w_cost'].append(w_avg_cost)
                        self.performance_dict['train_i_cost'].append(i_avg_cost)
                        self.performance_dict['val_w_cost'].append(w_val_cost)
                        self.performance_dict['val_i_cost'].append(i_val_cost)
                        self.performance_dict['epoch'].append(epoch+1)
                else:
                    print('%04d' % (epoch + 1), '{:.9f}'.format(w_avg_cost), '{:.9f}'.format(i_avg_cost))
                if epoch % 50 == 0:
                    w_path_ckpt += '/' + str(epoch+1)
                    i_path_ckpt += '/' +str(epoch+1)
                    if not os.path.exists(w_path_ckpt):
                        os.makedirs(w_path_ckpt)
                    saver.save(sess, w_path_ckpt + '/model.ckpt')
                    if not os.path.exists(i_path_ckpt):
                        os.makedirs(i_path_ckpt)
                    saver.save(sess, i_path_ckpt + '/model.ckpt')

        return self.performance_dict


class DNN_test(object):

    def __init__(self, sess, file_name, input_dim, node_per_hidden_layers, target, epoch):
        self.sess = sess
        self.file_name = file_name
        self.input_dim = input_dim
        self.node_per_hidden_layers = node_per_hidden_layers
        self.target = target
        self.X = tf.placeholder(dtype=tf.float32, shape=[None, self.input_dim], name='input')
        self.net = None
        self.net = self.build_network()

        saver = tf.train.Saver()
        dir_name = os.getcwd()
        path_ckpt = dir_name + '/rtd_model/' + self.file_name +'/' + self.target + '/' + str(epoch) + '/model.ckpt'
        saver.restore(self.sess, path_ckpt)

    def build_network(self):
        n_out = 1
        with tf.variable_scope(self.target):
            net = None
            for i in range(len(self.node_per_hidden_layers)):
                if i == 0:
                    net = tf.layers.dense(self.X, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=0.0)
                else:
                    net = tf.layers.dense(net, units=self.node_per_hidden_layers[i], activation=tf.nn.relu, kernel_initializer=tf.contrib.layers.xavier_initializer())
                    net = tf.layers.dropout(net, rate=0.0)
            out_layer = tf.layers.dense(net, units=n_out, kernel_initializer=tf.contrib.layers.xavier_initializer())

        return out_layer

    def predict(self, input_vector):
        return self.sess.run(self.net, feed_dict={self.X: input_vector})


