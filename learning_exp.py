from learner.regression import *
from matplotlib import pyplot as plt

learning_rate = 0.0001
training_epoch = 200
batch_size = 32
model_name = 'tiny_b3_sample'
print('learning_rate=', learning_rate, 'training_epoch=', training_epoch, 'batch_size=', batch_size, 'model_name=', model_name)
node_per_hidden_layers = [64, 32, 16]
learner = DNN_training('tiny_training_sample_DA.csv', node_per_hidden_layers)
learner.read_validate_data('tiny_validation_sample_DA.csv')
performance_dict = learner.conduct_learning(learning_rate=learning_rate, training_epoch=training_epoch, batch_size=batch_size, model_name=model_name)

fig = plt.figure()
fig.suptitle('Loss (MSE)')
plt.subplot(2, 1, 1)
plt.plot(performance_dict['epoch'], performance_dict['train_w_cost'], 'rx', label='training loss')
plt.plot(performance_dict['epoch'], performance_dict['val_w_cost'], 'b.', label='validation loss')
plt.ylabel('Waiting time')
plt.legend(loc='upper left')

plt.subplot(2, 1, 2)
plt.plot(performance_dict['epoch'], performance_dict['train_i_cost'], 'rx', label='training loss')
plt.plot(performance_dict['epoch'], performance_dict['val_i_cost'], 'b.', label='validation loss')
plt.ylabel('Idle time')
plt.show()

# learning_rate = 0.0001
# training_epoch = 500
# batch_size = 64
# model_name = 'test_waiting'
# print('learning_rate=', learning_rate, 'training_epoch=', training_epoch, 'batch_size=', batch_size, 'model_name=', model_name)
# node_per_hidden_layers = [64, 32, 16]
# learner = DNN_training('data3_B_train_DA.csv', 'both', node_per_hidden_layers)
# learner.read_validate_data('data3_B_val_DA.csv')
# learner.conduct_learning(learning_rate=learning_rate, training_epoch=training_epoch, batch_size=batch_size, model_name=model_name)




