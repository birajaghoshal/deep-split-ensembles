# Why have a Unified Uncertainty? Disentangling it using Deep Split Ensembles (NeurIPS 2020)

The code is shared for easy reproducibility and to encourage future work.

The following readme has simple steps to reproduce the training, evaluation and all the experiments for any of the datasets (also provided as csv files in supplementary material)

## Setup
1. Setup Virtual Environment
```
pip install virtualenv
virtualenv venv
source venv/bin/activate
```
2. Install dependencies
`pip install -r requirements.txt`

3. Run the code

## Run

### Train
```
python main.py train --datasets_dir datasets --dataset boston --model_dir boston_models --verbose 1
```

### Evaluate
```
python main.py evaluate --datasets_dir datasets --dataset boston --model_dir boston_models
```

### Experiments

#### Calibration - Defer Simulation
```
python main.py experiment --exp_name defer_simulation --plot_path plots --datasets_dir datasets --dataset boston --model_dir boston_models
```

#### Calibration - Clusterwise OOD
```
python main.py experiment --exp_name clusterwise_ood --plot_path plots --datasets_dir datasets --dataset boston --model_dir boston_models
```

#### Calibration - KL Divergence vs Mode
```
python main.py experiment --exp_name kl_mode --plot_path plots --datasets_dir datasets --dataset boston --model_dir boston_models
```

#### Toy regression
```
python main.py experiment --exp_name toy_regression --plot_path toy --model_dir toy_models --dataset toy
```

#### Show model parameters
```
python main.py experiment --exp_name show_summary --datasets_dir datasets --dataset boston
```

#### Empirical rule test
```
python main.py experiment --exp_name empirical_rule_test --datasets_dir datasets --dataset boston --model_dir boston_models
```

## Further Notes

### Human experts

Set `--mod_split` flag in all commands to `human`, to access splits created by human experts.
Only available for Power Plant Output and Red Wine Quality

### ADReSS - Compare features extraction

1. Download the [opensmile](https://www.audeering.com/opensmile/) toolkit.
2. `tar -zxvf openSMILE-2.x.x.tar.gz`
3. `cd openSMILE-2.x.x`
4. `bash autogen.sh`
5. `make -j4`
6. `make`
7. `make install`