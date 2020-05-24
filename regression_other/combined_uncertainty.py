import tensorflow as tf
import tensorflow_probability as tfp
from tensorflow.keras.layers import *

from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler

import os
import numpy as np
np.random.seed(0)

import matplotlib.pyplot as plt

import models

tfd = tfp.distributions

def train(X, y, config):
	run_all_folds(X, y, train=True, config=config)

def evaluate(X, y, config):
	run_all_folds(X, y, train=False, config=config)
	
def plot(X, y, config):
	ensemble_mus, ensemble_sigmas, true_values = get_ensemble_predictions(X, y, config)
	for i in range(config.n_feature_sets):
		print('feature set {}'.format(i))
		defered_rmse_list, non_defered_rmse_list = defer_analysis(true_values, ensemble_mus, ensemble_sigmas[...,i])

		# plt.subplot(n_feature_sets, 1, i+1)
		# plt.plot(range(ensemble_mus.shape[0]+1), defered_rmse_list, label='Defered RMSE')
		# plt.plot(range(ensemble_mus.shape[0]+1), non_defered_rmse_list, label='Non Defered RMSE')
		plt.plot(range(ensemble_mus.shape[0]+1), non_defered_rmse_list, label=str(i))
		plt.legend()
		plt.xlabel('No. of datapoints defered')
		plt.xticks(range(0, ensemble_mus.shape[0]+1, (ensemble_mus.shape[0])//25))
		# plt.yticks(range(0,30))
		plt.title('feature set {}'.format(i))
		plt.grid()

	plt.savefig(config.plot_name)
	plt.show()

def run_all_folds(X, y, train, config):
	kf = KFold(n_splits=config.n_folds, shuffle=True, random_state=42)
	fold=1
	all_rmses = []
	all_nlls = []
	n_feature_sets = len(X)
	for train_index, test_index in kf.split(y):
		print('Fold {}'.format(fold))

		if config.dataset=='msd':
			train_index = [x for x in range(463715)]
			test_index = [x for x in range(463715, 515345)]

		y_train, y_val = y[train_index], y[test_index]
		x_train = [i[train_index] for i in X]
		x_val = [i[test_index] for i in X]
		for i in range(n_feature_sets):
			x_train[i], x_val[i] = standard_scale(x_train[i], x_val[i])

		# x_val[0][:,3] = np.random.normal(loc=2, scale=3, size=x_val[0][:,3].shape)
		# x_val[-1][:,0] = np.random.normal(loc=0, scale=1, size=x_val[-1][:,0].shape)

		rmse, nll = train_deep_ensemble(x_train, y_train, x_val, y_val, fold, config, train=train, verbose=config.verbose)
		all_rmses.append(rmse)
		all_nlls.append(nll)
		fold+=1
		# if fold == 3:
		# 	exit()
		print('='*20)

		if config.dataset=='msd':
			break

	print('Final {} fold results'.format(config.n_folds))
	print('val rmse {:.3f}, +/- {:.3f}'.format(np.mean(all_rmses), np.std(all_rmses)))
	[print('feature set {}, val nll {:.3f}, +/- {:.3f}'.format(i, np.mean(all_nlls, axis=0)[i], np.std(all_nlls, axis=0)[i]))
	 for i in range(n_feature_sets)]
	print(['{:.3f} {:.3f}'.format(np.mean(all_nlls, axis=0)[i], np.std(all_nlls, axis=0)[i]) 
		for i in range(n_feature_sets)])

def standard_scale(x_train, x_test):
	scalar = StandardScaler()
	scalar.fit(x_train)
	x_train = scalar.transform(x_train)
	x_test = scalar.transform(x_test)
	return x_train, x_test

def train_a_model(
	model_id, fold,
	x_train, y_train,
	x_val, y_val, config):

	model,_ = models.build_model(config)

	negloglik = lambda y, p_y: -p_y.log_prob(y)
	custom_mse = lambda y, p_y: tf.keras.losses.mean_squared_error(y, p_y.mean())
	# mse_wrapped = utils.MeanMetricWrapper(custom_mse, name='custom_mse')

	checkpoint_filepath = os.path.join(config.model_dir, 'fold_{}_nll_{}.h5'.format(fold, model_id))
	checkpointer = tf.keras.callbacks.ModelCheckpoint(
			checkpoint_filepath, monitor='val_loss', verbose=0, save_best_only=True,
			save_weights_only=True, mode='auto', save_freq='epoch')


	# model.compile(optimizer=tf.optimizers.Adam(learning_rate=config.lr),
	# 			  loss=[negloglik]*len(x_train))

	
				  # metrics=[mse_wrapped, mse_wrapped, mse_wrapped])

	if config.build_model == 'combined_pog':
		model.compile(optimizer=tf.optimizers.Adam(learning_rate=config.lr),
					  loss=[negloglik]*len(x_train))
		hist = model.fit(x_train, [y_train]*len(x_train),
						batch_size=config.batch_size,
						epochs=config.epochs,
						verbose=config.verbose,
						callbacks=[checkpointer],
						validation_data=(x_val, [y_val]*len(x_train)))

	elif config.build_model == 'combined_multivariate':
		model.compile(optimizer=tf.optimizers.Adam(learning_rate=config.lr),
					  loss=[negloglik])
		hist = model.fit(x_train, y_train,
						batch_size=config.batch_size,
						epochs=config.epochs,
						verbose=config.verbose,
						callbacks=[checkpointer],
						validation_data=(x_val, y_val))

	epoch_val_losses = hist.history['val_loss']
	best_epoch_val_loss, best_epoch = np.min(epoch_val_losses), np.argmin(epoch_val_losses)+1
	best_epoch_train_loss = hist.history['loss'][best_epoch-1]

	print('Model id: ', model_id)
	print('Best Epoch: {:d}'.format(best_epoch))
	print('Train NLL: {:.3f}'.format(best_epoch_train_loss)) 
	print('Val NLL: {:.3f}'.format(best_epoch_val_loss)) 

	model.load_weights(os.path.join(config.model_dir, 'fold_{}_nll_{}.h5'.format(fold, model_id)))

	return model, [best_epoch_train_loss, best_epoch_val_loss]

def train_deep_ensemble(x_train, y_train, x_val, y_val, fold, config, train=False, verbose=0):

	n_feature_sets = len(x_train)
	train_nlls, val_nlls = [], []
	mus = []
	featurewise_sigmas = [[] for i in range(n_feature_sets)]
	ensemble_preds = []

	for model_id in range(config.n_models):

		if train:
			model, results = train_a_model(model_id, fold, x_train, y_train, x_val, y_val, config)
			train_nlls.append(results[0])
			val_nlls.append(results[1])
		else:
			model, _ = models.build_model(config)
			model.load_weights(os.path.join(config.model_dir, 'fold_{}_nll_{}.h5'.format(fold, model_id)))

		y_val = y_val.reshape(-1,1)
		preds = model(x_val)
		# print(preds.shape)

		ensemble_preds.append(preds)
		if config.build_model == 'combined_multivariate':
			mus.append(preds.mean().numpy()[:,0])
		elif config.build_model == 'combined_pog':
			mus.append(preds[0].mean().numpy())

		for i in range(n_feature_sets):
			if config.build_model == 'combined_multivariate':
				featurewise_sigmas[i].append(preds.stddev().numpy()[:,i:i+1])
			elif config.build_model == 'combined_pog':
				featurewise_sigmas[i].append(preds[i].stddev().numpy())

		val_rmse = mean_squared_error(y_val,mus[model_id], squared=False)
		print('Val RMSE: {:.3f}'.format(val_rmse))

		n_val_samples = y_val.shape[0]
		if verbose > 1:
			for i in range(n_val_samples):
				stddev_print_string = ''
				for j in range(n_feature_sets):
					stddev_print_string += '\t\tStd Dev set {}: {:.5f}'.format(j, featurewise_sigmas[j][model_id][i][0])
				print('Pred: {:.3f}'.format(mus[model_id][i][0]), '\tTrue: {:.3f}'.format(y_val[i][0]), stddev_print_string)
		print('-'*20)

	ensemble_mus = np.mean(mus, axis=0).reshape(-1,1)
	ensemble_sigmas = []
	for i in range(n_feature_sets):
		ensemble_sigma = np.sqrt(np.mean(np.square(featurewise_sigmas[i]) + np.square(ensemble_mus), axis=0).reshape(-1,1) - np.square(ensemble_mus))
		ensemble_sigmas.append(ensemble_sigma)
	
	ensemble_val_rmse = mean_squared_error(y_val, ensemble_mus, squared=False)

	print('Deep Ensemble val rmse {:.3f}'.format(ensemble_val_rmse))
	if verbose > 0:
		print('Deep Ensemble Results')
		for i in range(n_val_samples):
			stddev_print_string = ''
			for j in range(n_feature_sets):
				stddev_print_string += '\t\tStd Dev set {}: {:.5f}'.format(j, ensemble_sigmas[j][i][0])
			print('Pred: {:.3f}'.format(ensemble_mus[i][0]), '\tTrue: {:.3f}'.format(y_val[i][0]), stddev_print_string)

	ensemble_val_nll = []
	for i in range(n_feature_sets):
		distributions = tfd.Normal(loc=ensemble_mus, scale=ensemble_sigmas[i])
		ensemble_val_nll.append(-1*np.mean(distributions.log_prob(y_val)))
	return ensemble_val_rmse, ensemble_val_nll

def get_ensemble_predictions(X, y, config):
	kf = KFold(n_splits=config.n_folds, shuffle=True, random_state=42)
	fold = 1
	all_mus, all_sigmas, true_values = [], [], []
	n_feature_sets = len(X)
	for train_index, test_index in kf.split(y):
		# if fold == fold_to_use:
		print('Fold ', fold)
		y_train, y_val = y[train_index], y[test_index]
		x_train = [i[train_index] for i in X]
		x_val = [i[test_index] for i in X]
		for i in range(n_feature_sets):
			x_train[i], x_val[i] = standard_scale(x_train[i], x_val[i])
		mus = []
		featurewise_sigmas = [[] for i in range(n_feature_sets)]
		for model_id in range(config.n_models):
			model, _ = models.build_model(config)
			model.load_weights(os.path.join(config.model_dir, 'fold_{}_nll_{}.h5'.format(fold, model_id)))

			y_val = y_val.reshape(-1,1)
			preds = model(x_val)

			mus.append(preds[0].mean().numpy())
			for i in range(n_feature_sets):
				featurewise_sigmas[i].append(preds[i].stddev().numpy())

		ensemble_mus = np.mean(mus, axis=0).reshape(-1,1)
		ensemble_sigmas = []
		for i in range(n_feature_sets):
			ensemble_sigma = np.sqrt(np.mean(np.square(featurewise_sigmas[i]) + np.square(mus), axis=0).reshape(-1,1) - np.square(ensemble_mus))
			ensemble_sigmas.append(ensemble_sigma)

		for i in range(y_val.shape[0]):
			all_mus.append(ensemble_mus[i])
			all_sigmas.append([ensemble_sigmas[j][i] for j in range(n_feature_sets)])
			true_values.append(y_val[i])
		fold+=1
		val_rmse = mean_squared_error(y_val, ensemble_mus, squared=False)
		print('Val RMSE: {:.3f}'.format(val_rmse))
	all_mus = np.reshape(all_mus, (-1,1))
	all_sigmas = np.reshape(all_sigmas, (-1, n_feature_sets))
	true_values = np.reshape(true_values, (-1, 1))
	return all_mus, all_sigmas, true_values

def defer_analysis(true_values, predictions, defer_based_on):

	defered_rmse_list, non_defered_rmse_list = [], []
	for i in range(predictions.shape[0]+1):
		if i==predictions.shape[0]:
			defered_rmse = mean_squared_error(true_values, predictions, squared=False)
		elif i==0:
			defered_rmse = 0
		else:
			defered_rmse = mean_squared_error(
				true_values[np.argsort(defer_based_on)][-i:], 
				predictions[np.argsort(defer_based_on)][-i:], squared=False)
		defered_rmse_list.append(defered_rmse)

		if i==0:
			non_defered_rmse = mean_squared_error(true_values, predictions, squared=False)
		elif i==predictions.shape[0]:
			non_defered_rmse = 0
		else:
			non_defered_rmse = mean_squared_error(
				true_values[np.argsort(defer_based_on)][:-i], 
				predictions[np.argsort(defer_based_on)][:-i], squared=False)

		non_defered_rmse_list.append(non_defered_rmse)
		# print('\n{} datapoints deferred'.format(i))

		# print('Defered RMSE : {:.3f}'.format(defered_rmse))
		# print('Not Defered RMSE : {:.3f}'.format(non_defered_rmse))
	return defered_rmse_list, non_defered_rmse_list


