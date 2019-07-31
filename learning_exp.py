from learner.regression import *
from matplotlib import pyplot as plt

learning_rate = 0.0001
training_epoch = 200
batch_size = 32
model_name = 'small_test'
node_per_hidden_layers = [64, 32, 16]
training_data_name = 'test_sample_normal_training.csv'
validation_data_name = 'test_sample_normal_validation.csv'
learner = DNN_training(training_data_name, node_per_hidden_layers)
learner.read_validate_data(validation_data_name)
print('learning_rate=', learning_rate, 'training_epoch=', training_epoch, 'batch_size=', batch_size, 'model_name=', model_name)
performance_dict = learner.conduct_learning(learning_rate=learning_rate, training_epoch=training_epoch, batch_size=batch_size, model_name=model_name)

fig = plt.figure()
fig.suptitle('Loss (MSE)')
plt.subplot(2, 1, 1)
plt.plot(performance_dict['epoch'], performance_dict['train_w_cost'], 'rx', label='training loss')
plt.plot(performance_dict['epoch'], performance_dict['val_w_cost'], 'b.', label='validation loss')
plt.ylabel('Waiting time')
plt.legend(loc='upper right')

plt.subplot(2, 1, 2)
plt.plot(performance_dict['epoch'], performance_dict['train_i_cost'], 'rx', label='training loss')
plt.plot(performance_dict['epoch'], performance_dict['val_i_cost'], 'b.', label='validation loss')
plt.ylabel('Idle time')
plt.show()




