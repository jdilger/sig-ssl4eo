#!/usr/bin/env bash

# slurm job configuration
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=4
#SBATCH --output=srun_outputs/B13_train_dino_vits16_%j.out
#SBATCH --error=srun_outputs/B13_train_dino_vits16_%j.err
#SBATCH --time=06:00:00
#SBATCH --job-name=pretrain_dino_vits16
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=10
#SBATCH --partition=booster

master_node=${SLURM_NODELIST:0:9}${SLURM_NODELIST:10:4}
dist_url="tcp://"
dist_url+=$master_node
dist_url+=:40000


# load required modules
module load Stages/2022
module load GCCcore/.11.2.0
module load Python

# activate virtual environment
source /p/project/hai_dm4eo/wang_yi/env2/bin/activate

# define available gpus
export CUDA_VISIBLE_DEVICES=0,1,2,3

# run script as slurm job
srun python -u pretrain_dino_s2c.py \
--is_slurm_job \
--data /p/scratch/hai_ssl4eo/data/ssl4eo_s12/ssl4eo_250k_s2c_uint8.lmdb \
--checkpoints_dir /p/project/hai_ssl4eo/wang_yi/ssl4eo-s12-dataset/src/benchmark/fullset_temp/checkpoints/dino/B13_vits16_224 \
--bands B13 \
--lmdb \
--arch vit_small \
--patch_size 16 \
--num_workers 10 \
--batch_size_per_gpu 64 \
--epochs 100 \
--warmup_epochs 10 \
--lr 1.5e-4 \
--optimizer adamw \
--dist_url $dist_url \
--seed 42 \
--mode s2c \
--dtype uint8 \
--season augment \
--in_size 224 \
--resume \